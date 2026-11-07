import json
import copy
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from b2_speaking import (attach_cards, pronunciation, reading_cards, reading_pages, resolve_episode,
                         resolve_production, shared_head_fits, timing_checks)
from long_speaking import FORMATS, compile_script, compose, load_episode, panels
from long_speaking_preview import caption_pages, native_plan, output_sizes, overlay
from prepare_audio import content_hash, sha256_file
from preview_frame_reuse import audio_spec, frame_mapping, opening_bake_timeline, reuse_alignment, reuse_frames

ROOT = Path(__file__).resolve().parent


class B2SpeakingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        Image.new("RGB", (200, 300), "#bb8b55").save(self.root / "image.png")
        (self.root / "scene.blend").write_bytes(b"fixture")
        raw = json.loads((ROOT / "episodes" / "oeif_b2_speaking_long.json").read_text(encoding="utf-8"))
        raw["source"].update(book="book.md", manifest="manifest.jsonl")
        raw["source"].pop("combined_edition")
        raw["scene"].update(base_scene="scene.blend", wall_logo="image.png")
        raw["promotion"].update(cover="image.png", pointing_emoji="image.png")
        book = "\n".join(t["text"] for t in raw["parts"][0]["follow_up"])
        self.reading = " ".join(f"Lesewort{i}" for i in range(130))
        book += "\n## Soll die Sommerzeit abgeschafft werden?\n### Impulstext\n"
        book += self.reading + "\n### Gestufter Diskussionsauftrag\n"
        (self.root / "book.md").write_text(book, encoding="utf-8")
        tracks = []
        for part in raw["parts"]:
            selection = part["tracks"][0]
            segments = [{"segment_id": f"{selection['id']}_seg_{index:03d}",
                         "speaker_label": label, "voice_id": "original_voice",
                         "text_original": "Original Satz " + ("eins." if index == 1 else "zwei."),
                         "text_tts": f"Source TTS {index}."}
                        for index, label in enumerate(selection["roles"], 1)]
            tracks.append({"track_id": selection["id"], "source_line": 20,
                           "section": f"Kapitel {part['number']}: Fixture", "segments": segments})
        (self.root / "manifest.jsonl").write_text(
            "\n".join(json.dumps(t) for t in tracks), encoding="utf-8")
        self.path = self.root / "storyboard.json"
        self.path.write_text(json.dumps(raw), encoding="utf-8")
        self.storyboard = load_episode(self.path)

    def test_book_models_and_partner_questions_are_not_replaced_by_second_presentation(self):
        script = compile_script(self.storyboard)
        originals = [t for t in script["turns"] if "source_track" in t]
        self.assertEqual(5, len(originals))
        self.assertEqual(["Original Satz eins.", "Original Satz eins.", "Original Satz zwei.",
                          "Original Satz eins.", "Original Satz zwei."], [t["text"] for t in originals])
        first = [t for t in originals if t["part"] == 1]
        self.assertEqual(["candidate_a"], [t["speaker"] for t in first])
        questions = [t for t in script["turns"] if t["kind"] == "question"]
        self.assertEqual(["candidate_b"] * 3, [t["speaker"] for t in questions])
        self.assertFalse(any("start" in t or "words" in t for t in script["turns"]))
        self.storyboard["parts"][2]["tracks"][0]["id"] = "oeif_b2_v2_046_planung"
        with self.assertRaisesRegex(ValueError, "first actual"):
            compile_script(self.storyboard)

    def test_reading_pages_preserve_every_word_and_do_not_use_picture_task(self):
        self.assertEqual(self.reading.split(), " ".join(reading_pages(self.storyboard)).split())
        self.assertTrue(all(20 < len(p.split()) <= 60 for p in reading_pages(self.storyboard)))
        self.storyboard["parts"][1]["picture"] = str(self.root / "image.png")
        self.path.write_text(json.dumps(self.storyboard), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "reading stimulus"):
            load_episode(self.path)

    def test_summary_is_one_labelled_voiced_card_with_book_reference(self):
        review = panels(self.storyboard, compile_script(self.storyboard))
        reading = [p for p in review if p["id"].startswith("reading_")]
        self.assertEqual(["reading_summary"], [p["id"] for p in reading])
        self.assertEqual("Teil 2: Kurzfassung des Lesetexts", reading[0]["heading"])
        self.assertIn("Den vollständigen Lesetext findest du im Buch.", reading[0]["body"])
        self.assertNotIn(self.reading, reading[0]["card_text"])
        raw = json.loads((ROOT / "episodes" / "oeif_b2_speaking_full_preview.json").read_text(encoding="utf-8"))
        raw["storyboard"] = str(self.path)
        episode = resolve_episode(raw, self.root / "preview.json")
        narration = [t for t in episode["turns"] if t["kind"] == "preparation_card"]
        self.assertEqual(["prepare_teil1", "reading_summary", "prepare_teil3"],
                         [t["id"] for t in narration])
        self.assertTrue(all(t["speaker"] == "examiner" for t in narration))
        for number, turn in enumerate(narration, 1):
            self.assertTrue(turn["display_text"].startswith(f"Teil {number}: "))
            self.assertTrue(turn["text"].startswith(f"Teil {('eins', 'zwei', 'drei')[number - 1]}: "))
            panel = next(p for p in review if p["id"] == turn["panel_id"])
            self.assertTrue(panel["heading"].startswith(f"Teil {number}: "))
        self.assertTrue(all(t["pause_after"] == 1.5 for t in narration))
        self.assertIn("Den vollständigen Lesetext findest du im Buch.", narration[1]["display_text"])
        self.assertEqual(["teil1_skip"], episode["review_cards"][0]["panels"])
        self.assertNotIn("vollständigen Lesetext lesen", episode["turns"][1]["display_text"])
        self.storyboard["parts"][1]["reading_summary"] = ""
        with self.assertRaisesRegex(ValueError, "nonempty"):
            reading_cards(self.storyboard)
        self.storyboard["parts"][1].pop("reading_summary")
        self.assertEqual(self.reading.split(), " ".join(c[3] for c in reading_cards(self.storyboard)).split())

    def test_voiced_card_keeps_one_screen_and_highlights_heading_text_and_book_cue(self):
        raw = json.loads((ROOT / "episodes" / "oeif_b2_speaking_full_preview.json").read_text(encoding="utf-8"))
        raw["storyboard"] = str(self.path)
        episode = resolve_episode(raw, self.root / "preview.json")
        card = next(t for t in episode["turns"] if t["id"] == "reading_summary")
        words = card["text"].split()
        card.update(start=0, start_frame=0, wav_duration=len(words) * .5,
                    words=[{"word": word, "start": i * .5, "end": i * .5 + .4, "score": .9}
                           for i, word in enumerate(words)])
        self.assertEqual([(0, len(words))], caption_pages(card))
        timeline = {"fps": 24, "total_frames": len(words) * 12 + 36, "turns": [card]}
        self.assertEqual([], native_plan(episode, self.storyboard, timeline))
        panel = next(p for p in panels(self.storyboard, compile_script(self.storyboard))
                     if p["id"] == "reading_summary")
        indices = [0, len(panel["heading"].split()),
                   len(panel["heading"].split()) + len(panel["card_text"].split())]
        for mode in FORMATS:
            for index in indices:
                _, check = overlay(episode, self.storyboard, timeline, mode, index * 12 + 3)
                highlighted = [t for t in check["text"] if "highlighted_word" in t]
                self.assertEqual([words[index]], [t["highlighted_word"] for t in highlighted])
                self.assertEqual(["forced_alignment"], [t["highlight_kind"] for t in highlighted])
                shown = " ".join(line for t in check["text"] for line in t["lines"])
                self.assertIn(panel["card_text"], shown)
                self.assertIn("Den vollständigen Lesetext findest du im Buch.", shown)

    def test_b2_brand_reading_and_omission_fit_both_layouts(self):
        review = panels(self.storyboard, compile_script(self.storyboard))
        for mode, layout in FORMATS.items():
            box = layout["scene"]
            native = Image.new("RGB", (box[2] - box[0], box[3] - box[1]))
            for panel in review:
                image, check = compose(self.storyboard, panel, mode, native)
                self.assertEqual(layout["size"], image.size)
                drawn = " ".join(line for text in check["text"] for line in text["lines"])
                self.assertIn("ÖIF B2", drawn)
                self.assertNotIn("ÖIF B1", drawn)
                self.assertEqual(1, check["cover_count"])
                if panel["id"] == "teil1_skip":
                    self.assertIn("Samirs Präsentation", drawn)

    def test_expanded_display_numbers_only_map_to_real_spoken_tokens(self):
        text, groups = pronunciation("ÖIF B2: 32 Personen, 1.696 Euro, WCs.")
        self.assertEqual("Ö I F B zwei: zweiunddreißig Personen, "
                         "eintausendsechshundertsechsundneunzig Euro, Toiletten.", text)
        self.assertEqual(list(range(len(text.split()))), [i for group in groups for i in group])
        self.assertEqual(7, len(groups))
        with self.assertRaisesRegex(ValueError, "Unmapped B2"):
            pronunciation("Noch 17 Euro.")

    def test_shared_camera_checks_portrait_crop_not_only_youtube_head_bounds(self):
        head = {"in_front": True, "bounds": [.1, .1, .9, .9]}
        self.assertFalse(shared_head_fits(head))
        head["bounds"] = [.15, .1, .85, .9]
        self.assertTrue(shared_head_fits(head))
        head["in_front"] = False
        self.assertFalse(shared_head_fits(head))

    def test_partial_frames_rebase_by_turn_without_reusing_changed_opening(self):
        pcm = self.root / "speech.wav"
        pcm.write_bytes(b"identical speech fixture")
        before = {"fps": 24, "total_frames": 20, "turns": [
            {"id": "opening", "start_frame": 0},
            {"id": "contact_01", "start_frame": 7, "audio": str(pcm),
             "text": "Guten Tag", "mouth_cues": [{"start": 0, "end": 1, "value": "A"}]},
        ]}
        after = copy.deepcopy(before)
        after["turns"][1]["start_frame"] = 11
        after["total_frames"] = 24
        old_plan = [{"format": "youtube", "frame": f, "file": f"native/youtube_{f:05d}.png",
                     "camera": "wide", "size": [304, 145]} for f in (0, 3, 6, 7, 10, 13, 16, 19)]
        plan = [{**p, "frame": p["frame"] + 4,
                 "file": f"native/youtube_{p['frame'] + 4:05d}.png"} for p in old_plan[3:]]
        plan.insert(0, old_plan[0])
        mappings = frame_mapping({}, after, plan, before, old_plan)
        self.assertEqual([7, 10, 13, 16, 19], [m["source_frame"] for m in mappings])
        self.assertEqual([11, 14, 17, 20, 23], [m["target"]["frame"] for m in mappings])
        self.assertEqual({"contact_01"}, {m["turn_id"] for m in mappings})
        after["turns"][1]["mouth_cues"][0]["value"] = "B"
        with self.assertRaisesRegex(ValueError, "mouth_cues"):
            frame_mapping({}, after, plan, before, old_plan)
        after["turns"][1]["mouth_cues"][0]["value"] = "A"
        after["turns"][1]["text"] = "Changed speech"
        with self.assertRaisesRegex(ValueError, "text"):
            frame_mapping({}, after, plan, before, old_plan)

    def test_partial_bake_limits_animation_to_opening_and_rejects_missing_dialogue(self):
        timeline = {"fps": 24, "duration": 12, "total_frames": 288, "turns": [
            {"id": "opening", "start_frame": 0}, {"id": "contact_01", "start_frame": 84}],
            "silent_notices": [{"id": "later"}]}
        plan = [{"file": "opening.png", "frame": 0}, {"file": "contact.png", "frame": 84}]
        shortened, missing = opening_bake_timeline(timeline, plan, [{"file": "contact.png"}])
        self.assertEqual(["opening"], [t["id"] for t in shortened["turns"]])
        self.assertEqual(84, shortened["total_frames"])
        self.assertEqual(3.5, shortened["duration"])
        self.assertEqual([], shortened["silent_notices"])
        self.assertEqual([plan[0]], missing)
        self.assertEqual(288, timeline["total_frames"])
        with self.assertRaisesRegex(ValueError, "only opening"):
            opening_bake_timeline(timeline, plan, [])

    def test_exact_preview_audio_checkpoint_rejects_changed_settings_or_outputs(self):
        source, target = self.root / "source", self.root / "destination"
        source.mkdir()
        episode = {"title": "Exact preview fixture"}
        (source / "episode.json").write_text(json.dumps(episode), encoding="utf-8")
        (source / "timeline.json").write_text('{"turns":[]}', encoding="utf-8")
        for name in ("dialogue.wav", "word_alignment.json", "speech_asr_check.json"):
            (source / name).write_bytes(b"fixture")
        (source / "speech_asr_check.json").write_text(json.dumps({
            "turns": [], "episode_sha256": sha256_file(source / "episode.json"),
            "timeline_sha256": sha256_file(source / "timeline.json")}), encoding="utf-8")
        state = {"spec": {"episode": episode, "code_sha256": {
            name: sha256_file(ROOT / name) for name in ("prepare_audio.py", "align_words.py",
                                                       "check_speech.py", "episode_config.py", "episode_profiles.py")}},
            "stages": {
                "audio": {name: sha256_file(source / name) for name in ("episode.json", "dialogue.wav")},
                "alignment": {name: sha256_file(source / name) for name in ("timeline.json", "word_alignment.json")},
                "speech_check": {"speech_asr_check.json": sha256_file(source / "speech_asr_check.json")}}}
        (source / "preview_state.json").write_text(json.dumps(state), encoding="utf-8")
        self.assertEqual(str(source), audio_spec(source, target, episode)["source"])
        with self.assertRaisesRegex(ValueError, "exact resolved"):
            audio_spec(source, target, {"title": "Different"})
        (source / "dialogue.wav").write_bytes(b"corrupted")
        with self.assertRaisesRegex(ValueError, "output changed"):
            audio_spec(source, target, episode)

    def test_partial_frame_copy_checks_hash_and_preserves_receipt_crop_bounds(self):
        from unittest.mock import patch
        source, target = self.root / "source", self.root / "destination"
        (source / "native").mkdir(parents=True)
        target.mkdir()
        original = source / "native" / "youtube_00007.png"
        Image.new("RGB", (4, 4), "blue").save(original)
        receipt = {"file": "native/youtube_00007.png", "sha256": sha256_file(original),
                   "head_bounds": [{"in_front": True, "bounds": [.2, .2, .8, .8]}]}
        for name, value in (("timeline.json", {}), ("native_plan.json", []),
                            ("native_checks.json", [receipt])):
            (source / name).write_text(json.dumps(value), encoding="utf-8")
        item = {"file": "native/youtube_00011.png", "frame": 11, "format": "youtube"}
        mapping = {"source_file": receipt["file"], "source_frame": 7,
                   "target": item, "turn_id": "contact_01"}
        with patch("preview_frame_reuse.frame_mapping", return_value=[mapping]):
            result = reuse_frames(target, {}, {}, [item], {"source": str(source)})
            self.assertEqual(receipt["sha256"], sha256_file(target / item["file"]))
            self.assertEqual(receipt["head_bounds"], result[0]["head_bounds"])
            self.assertEqual(7, result[0]["reused_from"]["frame"])
            original.write_bytes(b"corrupted")
            with self.assertRaisesRegex(ValueError, "PNG changed"):
                reuse_frames(target, {}, {}, [item], {"source": str(source)})

    def test_partial_alignment_reuses_measured_words_and_rejects_changed_cache(self):
        source, target = self.root / "source", self.root / "destination"
        (source / "alignment").mkdir(parents=True)
        target.mkdir()
        pcm = self.root / "speech.wav"
        pcm.write_bytes(b"identical speech fixture")
        payload = {"text": "Guten Tag", "wav_sha256": sha256_file(pcm), "model": "fixture"}
        key = content_hash(payload)
        words = [{"word": word, "start": i * .5, "end": i * .5 + .4, "score": .9}
                 for i, word in enumerate(payload["text"].split())]
        turn = {"id": "contact_01", "text": payload["text"], "audio": str(pcm),
                "alignment_key": key, "words": words, "wav_duration": 1,
                "mouth_cues": [{"start": 0, "end": 1, "value": "A"}]}
        for build in (source, target):
            (build / "timeline.json").write_text(json.dumps({"turns": [turn]}), encoding="utf-8")
        generated = copy.deepcopy(turn)
        generated["mouth_cues"][0]["value"] = "B"
        (target / "timeline.json").write_text(json.dumps({"turns": [generated]}), encoding="utf-8")
        name = f"contact_01-{key[:20]}.words.json"
        saved = {"cache_key": key, "payload": payload, "words": words}
        (source / "alignment" / name).write_text(json.dumps(saved), encoding="utf-8")
        reuse_alignment(target, {"source": str(source)})
        self.assertEqual(saved, json.loads((target / "alignment" / name).read_text(encoding="utf-8")))
        reused_timeline = json.loads((target / "timeline.json").read_text(encoding="utf-8"))
        self.assertEqual(turn["mouth_cues"], reused_timeline["turns"][0]["mouth_cues"])
        self.assertEqual(["contact_01"], reused_timeline["mouth_cue_reuse"]["turn_ids"])
        saved["words"][0]["word"] = "Invented"
        (source / "alignment" / name).write_text(json.dumps(saved), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "cache differs"):
            reuse_alignment(target, {"source": str(source)})

    def test_youtube_first_and_cards_fit_reserved_silence_on_both_sampling_grids(self):
        legacy = json.loads(self.path.read_text(encoding="utf-8"))
        legacy["narrate_preparation_cards"] = False
        self.path.write_text(json.dumps(legacy), encoding="utf-8")
        raw = json.loads((ROOT / "episodes" / "oeif_b2_speaking_full_preview.json").read_text(encoding="utf-8"))
        raw["storyboard"] = str(self.path)
        episode = resolve_episode(raw, self.root / "preview.json")
        self.assertEqual({"youtube": (960, 540)}, output_sizes(episode))
        timeline = {"fps": 24, "total_frames": 1000, "turns": [
            {"id": "preparation", "start_frame": 7, "end_frame": 22,
             "pause_after_frames": round(episode["turns"][1]["pause_after"] * 24)},
            {"id": "teil1_followup_06", "start_frame": 600, "end_frame": 611,
             "pause_after_frames": 132},
        ]}
        (self.root / "timeline.json").write_text(json.dumps(timeline), encoding="utf-8")
        attach_cards(self.root, episode)
        result = json.loads((self.root / "timeline.json").read_text(encoding="utf-8"))
        for notice in result["silent_notices"]:
            anchor = 600 if notice["id"] == "teil1_skip" else 7
            self.assertEqual(0, (notice["start_frame"] - anchor) % 6)
            self.assertEqual(0, (notice["end_frame"] - anchor) % 6)
        timeline["turns"][0]["pause_after_frames"] = 0
        (self.root / "timeline.json").write_text(json.dumps(timeline), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "overlap"):
            attach_cards(self.root, episode)
        plan = native_plan(episode, self.storyboard, {"total_frames": 6, "turns": [
            {"start_frame": 0, "panel_id": "01_opening", "camera": "wide"}]})
        self.assertEqual({"youtube"}, {p["format"] for p in plan})
        episode["output_formats"] = ["youtube", "youtube"]
        with self.assertRaisesRegex(ValueError, "unique"):
            output_sizes(episode)

    def test_speaking_and_short_cut_limits_are_checked_before_rendering(self):
        raw = json.loads((ROOT / "episodes" / "oeif_b2_speaking_full_preview.json").read_text(encoding="utf-8"))
        raw["storyboard"] = str(self.path)
        episode = resolve_episode(raw, self.root / "preview.json")
        turns, cursor = [], 0
        for source in episode["turns"]:
            turns.append({**source, "start_frame": cursor, "end_frame": cursor + 24,
                          "start": cursor / 24, "end": (cursor + 24) / 24,
                          "pause_after_frames": 12, "wav_duration": 1})
            cursor += 36
        timeline = {"fps": 24, "total_frames": cursor, "turns": turns}
        report = timing_checks(episode, self.storyboard, timeline)
        self.assertTrue(report["short_complete_turn_selection_fits"])
        presentation = next(t for t in turns if t.get("source_track") == "oeif_b2_v2_001_praesentation")
        presentation["wav_duration"] = 91
        with self.assertRaisesRegex(ValueError, "speaking limit"):
            timing_checks(episode, self.storyboard, timeline)
        presentation["wav_duration"] = 1
        presentation["end_frame"] += 180 * 24
        with self.assertRaisesRegex(ValueError, "short selection"):
            timing_checks(episode, self.storyboard, timeline)
        with self.assertRaisesRegex(ValueError, "explicit user preview approval"):
            resolve_production(raw, self.root / "production.json")

    def test_production_requires_the_exact_pinned_preview_and_unchanged_sources(self):
        from long_speaking_preview import SOURCES

        raw = json.loads((ROOT / "episodes" / "oeif_b2_speaking_full_preview.json").read_text(encoding="utf-8"))
        raw["storyboard"] = str(self.path)
        resolved = resolve_episode(raw, self.root / "preview.json")
        source = self.root / "approved"
        source.mkdir()
        names = ("preview_youtube.mp4", "episode.json", "dialogue.wav", "timeline.json",
                 "word_alignment.json", "subtitles.srt", "delivery_checks.json",
                 "speech_asr_check.json", "b2_timing_checks.json")
        for name in names:
            (source / name).write_bytes(b"fixture")
        (source / "episode.json").write_text(json.dumps(resolved), encoding="utf-8")
        (source / "delivery_checks.json").write_text(json.dumps({
            "status": "preview_only", "exports": {"youtube": {}},
            "source_sha256": {"asset_sha256": {str(self.path): sha256_file(self.path)}},
        }), encoding="utf-8")
        (source / "export_manifest.json").write_text(json.dumps({
            "files_sha256": {name: sha256_file(source / name) for name in names},
            "generation_source_sha256": {name: sha256_file(ROOT / name) for name in SOURCES},
        }), encoding="utf-8")
        raw.update(template="long_speaking_production", approved_preview=str(source),
                   approved_preview_manifest_sha256=sha256_file(source / "export_manifest.json"),
                   preview_approval={"approved_by": "user", "approved_on": "fixture"})
        self.assertEqual(str(source), resolve_production(raw, self.root / "production.json")["approved_preview"])
        (source / "dialogue.wav").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "Unverified B2 preview file"):
            resolve_production(raw, self.root / "production.json")
        (source / "dialogue.wav").write_bytes(b"fixture")
        self.path.write_text(self.path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Approved B2 input changed"):
            resolve_production(raw, self.root / "production.json")


if __name__ == "__main__":
    unittest.main()
