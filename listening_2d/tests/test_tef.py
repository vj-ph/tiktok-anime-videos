import copy
from pathlib import Path
import tempfile
import unittest
import wave

from listening_2d.rendering.compose_tef import load_visual_assets, question_markup, scene_body, word_mapping
from listening_2d.rendering.deliver_tef import validate
from listening_2d.hyperframes_local import cli_path
from listening_2d.preparation.prepare_tef import TIMINGS, atomic_json, chime_enabled, schedule, sha256_file
from listening_2d.preparation.prepare_sample import mix_events, write_wav


class TefSequenceTests(unittest.TestCase):
    def fixture(self):
        episode = {"duration_limit_seconds": 900, "outro_seconds": 3}
        measured = {}

        def speech(ident, seconds=1):
            measured[ident] = {"audio": f"{ident}.wav", "sha256": ident, "frames": round(seconds * 48000),
                              "wav_duration": seconds, "text": ident}

        for ident in ("title", "setup", "solutions_intro", "cta"):
            speech(ident)
        groups, question = [], 1
        for family, (_, _, count) in TIMINGS.items():
            speech("instruction_" + family)
            ident = "source_" + family
            speech(ident, 2.013)
            numbers = list(range(question, question + count))
            groups.append({"family": family, "recordings": [{"id": ident, "numbers": numbers}]})
            question += count
        for n in range(1, question):
            speech(f"solution_{n}")
        return episode, groups, measured

    def test_instruction_then_full_silent_windows_and_one_shared_playback(self):
        episode, groups, measured = self.fixture()
        timeline = schedule(episode, groups, measured)
        events = timeline["events"]
        for group in groups:
            family = group["family"]
            start = next(n for n, e in enumerate(events) if e["id"] == "instruction_" + family)
            instruction, reading, recording, response = events[start:start + 4]
            self.assertTrue(instruction["visible"])
            self.assertEqual((reading["kind"], recording["kind"], response["kind"]),
                             ("silence", "recording", "silence"))
            self.assertEqual((reading["duration"], response["duration"]), TIMINGS[family][:2])
            self.assertEqual(reading["numbers"], recording["numbers"])
            self.assertEqual(reading["numbers"], response["numbers"])
            self.assertNotIn("audio", reading)
            self.assertNotIn("audio", response)
            self.assertEqual(reading["start_frame"], instruction["end_frame"])
            self.assertEqual(recording["start_frame"], reading["end_frame"])
            self.assertEqual(response["start_frame"], recording["end_frame"])
            self.assertEqual(len([e for e in events if e.get("audio_id") == recording["audio_id"]]), 1)
            self.assertEqual(len(recording["numbers"]), TIMINGS[family][2])
            self.assertGreaterEqual(recording["duration"], 2.013)
        last_answer = max(e["end_frame"] for e in events if e["id"].startswith("answer_"))
        first_solution = next(e["start_frame"] for e in events if e["id"] == "solutions_intro")
        self.assertEqual(first_solution, last_answer)

    def test_exact_fifteen_minutes_is_rejected_including_outro(self):
        episode, groups, measured = self.fixture()
        initial = schedule(episode, groups, measured)
        episode["outro_seconds"] += 900 - initial["duration"]
        with self.assertRaisesRegex(ValueError, "strictly below"):
            schedule(episode, groups, measured)
        episode["outro_seconds"] -= 1 / 24
        self.assertEqual(schedule(episode, groups, measured)["total_frames"], 21599)

    def test_immediate_reveals_wait_for_full_pause_and_keep_both_shared_answers_together(self):
        episode, groups, measured = self.fixture()
        episode["answer_reveal"] = "after_exercise"
        measured.pop("solutions_intro")
        timeline = schedule(episode, groups, measured)
        events = timeline["events"]
        self.assertNotIn("solutions_intro", [e["id"] for e in events])
        for group in groups:
            recording = group["recordings"][0]
            start = next(i for i, e in enumerate(events) if e["id"] == "read_" + recording["id"])
            read, listen, answer = events[start:start + 3]
            reveals = events[start + 3:start + 3 + len(recording["numbers"])]
            self.assertEqual((read["duration"], answer["duration"]), TIMINGS[group["family"]][:2])
            self.assertEqual([e["number"] for e in reveals], recording["numbers"])
            self.assertEqual(reveals[0]["start_frame"], answer["end_frame"])
            for reveal in reveals:
                self.assertEqual(reveal["reveal_numbers"], recording["numbers"])
                self.assertEqual(reveal["recording_id"], listen["recording_id"])
            self.assertEqual(events[start + 3 + len(reveals)]["start_frame"], reveals[-1]["end_frame"])

    def test_paired_reveal_shows_both_answers_during_either_explanation(self):
        cards = {str(n): {"number": n, "question": f"Question {n} ?", "answer": answer,
                         "options": {answer: f"Bonne réponse {n}"}, "visual_set_id": None}
                 for n, answer in ((11, "A"), (12, "C"))}
        content = {"episode": {}, "cards": cards}
        first = scene_body({"id": "solution_11", "number": 11, "reveal_numbers": [11, 12]}, content, {})
        second = scene_body({"id": "solution_12", "number": 12, "reveal_numbers": [11, 12]}, content, {})
        self.assertEqual(first, second)
        cue = scene_body({"id": "chime_pair", "kind": "sfx", "number": 11,
                          "reveal_numbers": [11, 12]}, content, {})
        self.assertEqual(first, cue)
        self.assertEqual(first.count('class="solution-answer"'), 2)
        for n in (11, 12):
            self.assertIn(f'data-reveal-question="{n}"', first)
            self.assertEqual(first.count(f"Bonne réponse {n}"), 1)

    def test_chime_reveals_once_after_each_full_pause_then_waits_for_tts(self):
        episode, groups, measured = self.fixture()
        episode.update(answer_reveal="after_exercise", reveal_chime=True)
        measured["reveal_chime"] = {**measured["title"], "frames": 103471, "text": ""}
        timeline = schedule(episode, groups, measured)
        self.assertTrue(timeline["chime_enabled"])
        self.assertFalse(any(t["kind"] == "sfx" for t in timeline["turns"]))
        cues = [e for e in timeline["events"] if e["kind"] == "sfx"]
        self.assertEqual(len(cues), len(groups))
        for cue in cues:
            i = timeline["events"].index(cue)
            answer, following = timeline["events"][i - 1], timeline["events"][i + 1]
            self.assertEqual(answer["duration"], TIMINGS[answer["family"]][1])
            self.assertEqual(cue["start_frame"], answer["end_frame"])
            self.assertEqual(cue["end_frame"] - cue["start_frame"], 52)
            self.assertEqual(following["start_frame"], cue["end_frame"])
            self.assertEqual(cue["reveal_numbers"], answer["numbers"])
            self.assertEqual(following["reveal_numbers"], answer["numbers"])

    def test_chime_requires_explicit_boolean_and_immediate_practice(self):
        for episode in ({"reveal_chime": True}, {"answer_reveal": "after_exercise", "reveal_chime": "yes"}):
            with self.assertRaisesRegex(ValueError, "requires after_exercise"):
                chime_enabled(episode)

    def test_question_card_does_not_expose_correct_choice(self):
        item = {"number": 1, "question": "Que fait-elle ?", "options": dict(zip("ABCD", ("Un", "Deux", "Trois", "Quatre"))),
                "answer": "C", "visual_set_id": None}
        markup = question_markup(item)
        self.assertNotIn("correct", markup)
        self.assertNotIn("data-answer", markup)
        item["answer"] = "D"
        self.assertEqual(markup, question_markup(item))

    def test_measured_highlights_and_silent_outro_card(self):
        turn = {"id": "title", "text": "Bonjour Canada.", "start": 2, "wav_duration": 1,
                "words": [{"word": "Bonjour", "start": .1, "end": .4, "score": .9},
                          {"word": "Canada.", "start": .5, "end": .9, "score": .8}]}
        mapping = word_mapping(turn)
        self.assertEqual((mapping[1]["start"], mapping[1]["end"]), (2.5, 2.9))
        invalid = copy.deepcopy(turn)
        invalid["words"][1].pop("start")
        with self.assertRaises(ValueError):
            word_mapping(invalid)
        self.assertIn("French Compass", scene_body({"id": "outro"}, {"episode": {}, "cards": {}}, {}))

    def test_platform_local_cli_resolution(self):
        self.assertEqual(cli_path("win32").name, "hyperframes.cmd")
        self.assertEqual(cli_path("linux").name, "hyperframes")
        self.assertEqual(cli_path("darwin").name, "hyperframes")

    def test_book_panels_replace_svg_on_attempt_and_correct_answer_without_relabelling(self):
        item = {"number": 1, "question": "Que fait-elle ?", "visual_set_id": "P19",
                "answer": "B", "picture_assets": {c: f"P19-{c}.png" for c in "ABCD"},
                "picture_labels_embedded": True}
        attempt = question_markup(item)
        for choice in "ABCD":
            self.assertIn(f'assets/P19-{choice}.png', attempt)
        self.assertNotIn(".svg", attempt)
        self.assertNotIn('class="letter"', attempt)
        solution = scene_body({"id": "solution_1", "number": 1},
                              {"episode": {}, "cards": {"1": item}}, {})
        self.assertIn('assets/P19-B.png', solution)
        self.assertNotIn("P19-A", solution)
        item.pop("picture_assets")
        item.pop("picture_labels_embedded")
        self.assertIn("assets/P19-A.svg", question_markup(item))

    def test_visual_assets_are_pinned_and_invalid_purchase_links_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            build = Path(temporary)
            panel = build / "panel.png"
            panel.write_bytes(b"book panel")
            visual = {"files": {str(panel): sha256_file(panel)},
                      "amazon_url": "https://a.co/d/example", "picture_sets": {
                          "P19": {"panels": {c: str(panel) for c in "ABCD"}, "labels_embedded": True}}}
            atomic_json(build / "visual_assets.json", visual)
            content = {"cards": {"1": {"visual_set_id": "P19"}}}
            load_visual_assets(build, content)
            self.assertEqual(content["cards"]["1"]["picture_assets"]["A"], "panel.png")
            visual["amazon_url"] = "javascript:alert(1)"
            atomic_json(build / "visual_assets.json", visual)
            with self.assertRaisesRegex(ValueError, "HTTPS"):
                load_visual_assets(build, content)
            visual["amazon_url"] = "https://a.co/d/example"
            atomic_json(build / "visual_assets.json", visual)
            panel.write_bytes(b"changed book panel")
            with self.assertRaises(ValueError):
                load_visual_assets(build, content)


class TefDeliveryTests(unittest.TestCase):
    def fixture(self, mode="after_attempt", chime=False):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        build = Path(temporary.name)
        clip = build / "clip.wav"
        with wave.open(str(clip), "wb") as w:
            w.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
            w.writeframes(b"\xe8\x03" * 48000)
        audio = {"audio": str(clip), "sha256": sha256_file(clip), "frames": 48000,
                 "wav_duration": 1, "source_audio": str(clip), "source_sha256": sha256_file(clip)}
        measured, groups = {}, []
        number = 1
        counts = (2, 2, 2, 3, 1, 1, 1, 2)
        for (family, timing), count in zip(TIMINGS.items(), counts):
            instruction = {"tts_text": family + " instruction"}
            measured["instruction_" + family] = {**audio, "text": instruction["tts_text"]}
            recordings = []
            for n in range(count):
                ident = family + str(n)
                numbers = list(range(number, number + timing[2]))
                number += timing[2]
                recordings.append({"id": ident, "numbers": numbers})
                measured[ident] = {**audio, "text": "Book recording"}
            groups.append({"family": family, "instruction": instruction, "recordings": recordings})
        for ident in ("title", "setup", "solutions_intro", "cta", *(f"solution_{n}" for n in range(1, 17))):
            measured[ident] = {**audio, "text": ident}
        episode = {"duration_limit_seconds": 900, "outro_seconds": 3,
                   "answer_reveal": mode, "reveal_chime": chime}
        if chime:
            measured["reveal_chime"] = {**audio, "text": "", "kind": "sfx"}
        timeline = schedule(episode, groups, measured)
        atomic_json(build / "input_pin.json", {"files": {}})
        atomic_json(build / "content.json", {"episode": episode, "groups": groups,
                                           "cards": {str(n): {} for n in range(1, 17)}})
        atomic_json(build / "audio_manifest.json", measured)
        atomic_json(build / "timeline.json", timeline)
        write_wav(build / "dialogue.wav", mix_events(timeline["events"]))
        return build, timeline

    def test_lossless_mix_has_full_official_silences_and_single_playbacks(self):
        build, _ = self.fixture()
        report = validate(build)
        self.assertEqual(report["unique_recordings"], 14)
        self.assertEqual(report["reading_silence_seconds"] + report["response_silence_seconds"], 320)

    def test_any_audio_inside_a_protected_silence_fails(self):
        build, timeline = self.fixture()
        pause = next(e for e in timeline["events"] if e["kind"] == "silence")
        with (build / "dialogue.wav").open("r+b") as w:
            w.seek(44 + pause["start_frame"] * 2000 * 2 + 200)
            w.write(b"\x01\x00")
        with self.assertRaisesRegex(ValueError, "not digitally silent"):
            validate(build)

    def test_inline_delivery_preserves_all_silences_and_reveals_once(self):
        build, _ = self.fixture("after_exercise")
        report = validate(build)
        self.assertEqual(report["answer_reveal"], "after_exercise")
        self.assertEqual(report["response_silence_seconds"], 195)

    def test_inline_delivery_rejects_revealing_another_question_or_only_half_a_pair(self):
        build, timeline = self.fixture("after_exercise")
        paired = next(e for e in timeline["events"] if len(e.get("reveal_numbers", [])) == 2)
        paired["reveal_numbers"] = paired["reveal_numbers"][:1]
        atomic_json(build / "timeline.json", timeline)
        with self.assertRaisesRegex(ValueError, "Reveal every exercise/pair"):
            validate(build)

    def test_chime_delivery_preserves_silences_and_has_fourteen_cues(self):
        build, _ = self.fixture("after_exercise", chime=True)
        report = validate(build)
        self.assertEqual(report["reveal_chime_count"], 14)
        self.assertEqual(report["reading_silence_seconds"] + report["response_silence_seconds"], 320)

    def test_tts_cannot_start_before_chime_finishes(self):
        build, timeline = self.fixture("after_exercise", chime=True)
        solution = next(e for e in timeline["events"] if e["id"] == "solution_1")
        solution["start_frame"] -= 1
        atomic_json(build / "timeline.json", timeline)
        with self.assertRaisesRegex(ValueError, "gap, overlap"):
            validate(build)


if __name__ == "__main__":
    unittest.main()
