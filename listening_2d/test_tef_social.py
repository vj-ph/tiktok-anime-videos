import copy
import json
from pathlib import Path
import tempfile
import unittest
import wave

from derive_tef_social import edit_timeline, speech_event, validate_short
from prepare_tef import FPS, TIMINGS, atomic_json, mix_events, schedule, sha256_file, write_wav
import test_tef


class TefSocialTests(unittest.TestCase):
    def fixture(self):
        episode, groups, measured = test_tef.TefSequenceTests().fixture()
        episode.update(answer_reveal="after_exercise", reveal_chime=True)
        measured["reveal_chime"] = {"audio": "cue.wav", "sha256": "cue", "frames": 103472,
                                   "wav_duration": 103472 / 48000, "text": "", "kind": "sfx"}
        for item in measured.values():
            item["words"] = [{"word": item["text"], "start": .1, "end": .8, "score": .9}]
        original = schedule(episode, groups, measured)
        return original, measured["title"], measured["cta"]

    def test_six_whole_family_edits_preserve_every_source_event_once(self):
        original, title, cta = self.fixture()
        before = copy.deepcopy(original)
        families = list(TIMINGS)
        plans = [families[:2], families[2:3], families[3:4], families[4:6], families[6:7], families[7:]]
        selected = []
        previous_end = None
        for plan in plans:
            result, mapping = edit_timeline(original, plan, title, cta)
            body = result["events"][1:-2]
            ids = mapping["source_event_ids"]
            selected.extend(ids)
            expected = [e for e in original["events"] if e["id"] in ids]
            if previous_end is not None:
                self.assertEqual(mapping["source_start_frame"], previous_end)
            previous_end = mapping["source_end_frame"]
            for new, old in zip(body, expected):
                ignored = {"start_frame", "end_frame", "start", "end"}
                self.assertEqual({k: v for k, v in new.items() if k not in ignored},
                                 {k: v for k, v in old.items() if k not in ignored})
                self.assertEqual(new["end_frame"] - new["start_frame"], old["end_frame"] - old["start_frame"])
            self.assertLess(result["total_frames"], 180 * FPS)
        expected_ids = [e["id"] for e in original["events"] if e["id"] not in ("title", "setup", "cta", "outro")]
        self.assertEqual(selected, expected_ids)
        self.assertEqual(original, before)

    def test_paired_recording_silence_chime_and_both_answers_remain_intact(self):
        original, title, cta = self.fixture()
        result, _ = edit_timeline(original, ["interview"], title, cta)
        events = result["events"]
        playback = next(e for e in events if e["kind"] == "recording")
        self.assertEqual(len([e for e in events if e["kind"] == "recording"]), 1)
        self.assertEqual(len(playback["numbers"]), 2)
        response = next(e for e in events if e["id"].startswith("answer_"))
        self.assertEqual(response["duration"], 30)
        cue = next(e for e in events if e["kind"] == "sfx")
        reveals = [e for e in events if e["id"].startswith("solution_")]
        self.assertEqual(cue["start_frame"], response["end_frame"])
        self.assertEqual(reveals[0]["start_frame"], cue["end_frame"])
        self.assertEqual([e["number"] for e in reveals], playback["numbers"])
        self.assertTrue(all(e["reveal_numbers"] == playback["numbers"] for e in reveals))

    def test_exact_three_minutes_fails_but_one_frame_below_passes(self):
        original, title, cta = self.fixture()
        result, _ = edit_timeline(original, ["voicemail"], title, cta)
        hold = 180 * FPS - (result["total_frames"] - 24)
        with self.assertRaisesRegex(ValueError, "strictly below"):
            edit_timeline(original, ["voicemail"], title, cta, hold)
        result, _ = edit_timeline(original, ["voicemail"], title, cta, hold - 1)
        self.assertEqual(result["total_frames"], 4319)

    def test_rejects_nonconsecutive_or_partial_families_and_missing_pair_answer(self):
        original, title, cta = self.fixture()
        for families in ([], ["missing"], ["picture_dialogue", "voicemail"], ["interview", "interview"]):
            with self.subTest(families=families), self.assertRaises(ValueError):
                edit_timeline(original, families, title, cta)
        broken = copy.deepcopy(original)
        last = next(e for e in reversed(broken["events"])
                    if e["id"].startswith("solution_") and len(e.get("reveal_numbers", [])) == 2)
        broken["events"].remove(last)
        with self.assertRaisesRegex(ValueError, "both complete"):
            edit_timeline(broken, ["reportage"], title, cta)

    def test_wrapper_rounds_up_without_clipping_or_speed_change(self):
        _, title, _ = self.fixture()
        title["frames"] = 48001
        event = speech_event("title", title, 13)
        self.assertEqual((event["start_frame"], event["end_frame"]), (13, 38))
        self.assertEqual(event["audio_samples"], 48001)
        self.assertEqual(event["duration"], 25 / FPS)

    def test_delivery_validator_rejects_audio_in_silence_and_changed_source_samples(self):
        original, _, _ = self.fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, build = root / "source", root / "part"
            source.mkdir()
            build.mkdir()
            manifest = {}
            for event in original["events"]:
                if "audio_id" not in event:
                    continue
                ident = event["audio_id"]
                path = source / f"{ident}.wav"
                if not path.exists():
                    with wave.open(str(path), "wb") as audio:
                        audio.setnchannels(1)
                        audio.setsampwidth(2)
                        audio.setframerate(48000)
                        audio.writeframes(b"\xe8\x03" * event["audio_samples"])
                event.update(audio=str(path), sha256=sha256_file(path))
                manifest[ident] = {"audio": str(path), "sha256": event["sha256"]}
            lookup = {e["id"]: e for e in original["events"]}
            for turn in original["turns"]:
                event = lookup[turn["id"]]
                turn.update(audio=event["audio"], sha256=event["sha256"])
            atomic_json(source / "timeline.json", original)
            atomic_json(source / "delivery_manifest.json", {})
            write_wav(source / "dialogue.wav", mix_events(original["events"]))
            turns = {t["id"]: t for t in original["turns"]}
            timeline, mapping = edit_timeline(original, ["voicemail"], turns["title"], turns["cta"])
            mapping.update(source=str(source), source_manifest_sha256=sha256_file(source / "delivery_manifest.json"),
                           numbers=next(e["numbers"] for e in timeline["events"] if e["kind"] == "recording"))
            for name, value in (("timeline.json", timeline), ("edit_decisions.json", mapping),
                                ("input_pin.json", {"files": {}}), ("audio_manifest.json", manifest)):
                atomic_json(build / name, value)
            pcm = mix_events(timeline["events"])
            write_wav(build / "dialogue.wav", pcm)
            self.assertTrue(validate_short(build)["source_pcm_byte_identical"])
            for prefix in ("read_", "listen_"):
                event = next(e for e in timeline["events"] if e["id"].startswith(prefix))
                damaged = bytearray(pcm)
                offset = event["start_frame"] * 2000 * 2 + 20
                damaged[offset] ^= 1
                write_wav(build / "dialogue.wav", damaged)
                with self.subTest(prefix=prefix), self.assertRaises(ValueError):
                    validate_short(build)
            self.assertEqual(original, json.loads((source / "timeline.json").read_text()))


if __name__ == "__main__":
    unittest.main()
