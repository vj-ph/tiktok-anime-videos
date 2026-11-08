import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

from a2_speaking_contacts import review_panels
from a2_speaking_preview import compile_turns, load_preview, native_plan, overlay, pronunciation
from episode_config import check_timeline
from long_speaking_preview import caption_words, display_state
from prepare_audio import sha256_file
import test_a2_speaking_contacts as contact_fixtures
from a2_speaking_production import prepare_production_audio, production_reuse_spec, resolve_production


class A2PreviewTests(unittest.TestCase):
    def setUp(self):
        fixture = contact_fixtures.A2SpeakingContactTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.review = copy.deepcopy(fixture.turns)
        for number, turn in self.review.items():
            if number not in (9, 13):
                turn["text"] = "Ein Beispielsatz."
        self.review[1]["text"] = "ÖIF A2 Sprechen mit Lea."
        for number, turn in self.review.items():
            turn["label"] = "Prüfer" if number % 2 == 0 or number in (1, 55) else "Lea"
        self.review[34]["text"] = "Heute um 15 Uhr oder morgen um 9 Uhr."
        self.review[36]["text"] = "Muss ich meine E-Card mitbringen?"
        self.turns = compile_turns(self.review)

    def measured(self, number, start_frame=0):
        turn = copy.deepcopy(self.turns[number - 1])
        turn.update(start_frame=start_frame, start=start_frame / 24,
                    wav_duration=len(turn["text"].split()) * .4 + .1)
        turn["words"] = [{"word": token, "start": i * .4 + .05,
                          "end": i * .4 + .3, "score": .9}
                         for i, token in enumerate(turn["text"].split())]
        return turn

    def test_complete_individual_exam_preserves_review_text_and_phase_order(self):
        self.assertEqual(55, len(self.turns))
        self.assertEqual([t["text"] for t in self.review.values()],
                         [t["reviewed_text"] for t in self.turns])
        self.assertEqual({0, 1, 2, 3}, {t["part"] for t in self.turns})
        self.assertEqual("opening", self.turns[0]["kind"])
        self.assertEqual("cta", self.turns[-1]["kind"])
        self.assertNotIn("candidate_b", {t["speaker"] for t in self.turns})
        self.assertEqual("picture_choice", self.turns[23]["panel_id"])
        self.assertEqual(["05_teil2_picture"] * 2, [t["panel_id"] for t in self.turns[24:26]])
        self.assertEqual("picture_description", self.turns[26]["panel_id"])
        self.assertEqual("personal_card", self.turns[39]["panel_id"])

    def test_numbers_and_book_abbreviations_map_only_actual_spoken_tokens(self):
        text, groups = pronunciation("ÖIF A2 um 15 Uhr. E-Card.")
        self.assertEqual("Ö I F A zwei um fünfzehn Uhr. E Card.", text)
        self.assertEqual([[0, 1, 2], [3, 4], [5], [6], [7], [8, 9]], groups)
        turn = self.measured(34)
        self.assertEqual("15", caption_words(turn)[2]["word"])
        with self.assertRaisesRegex(ValueError, "Unmapped"):
            pronunciation("Um 17:30.")
        opening = self.measured(1)
        episode = {"turns": self.turns}
        timeline = {"fps": 24, "turns": [opening]}
        self.assertIsNone(display_state(episode, timeline, 0)[3])
        self.assertEqual(0, display_state(episode, timeline, 2)[3])
        self.assertEqual(1, display_state(episode, timeline, 31)[3])
        opening["words"][0]["word"] = "invented"
        with self.assertRaises(ValueError):
            display_state(episode, timeline, 2)

    def test_native_plan_skips_all_cards_and_restarts_on_camera_cuts(self):
        timeline = {"total_frames": 24, "turns": [
            {"start_frame": 0, "panel_id": "01_opening", "camera": "wide"},
            {"start_frame": 7, "panel_id": "picture_choice", "camera": "examiner"},
            {"start_frame": 12, "panel_id": "contact_model", "camera": "candidate_a"},
            {"start_frame": 20, "panel_id": "12_final_cta", "camera": "wide"},
        ]}
        plan = native_plan({"render": {"motion_step": 3, "native_scale": .25}}, timeline)
        self.assertEqual([0, 3, 6, 12, 15, 18], [p["frame"] for p in plan])
        self.assertEqual({"youtube"}, {p["format"] for p in plan})
        self.assertEqual([304, 145], plan[0]["size"])

    def test_a2_overlay_uses_measured_subtitles_on_the_neutral_choice_card(self):
        from PIL import Image
        from runtime_config import font_path
        if not font_path().is_file():
            self.skipTest("Project fonts not installed.")
        with tempfile.TemporaryDirectory() as temp:
            picture = Path(temp) / "image.png"
            Image.new("RGB", (1408, 768), "#507060").save(picture)
            visual = {
                "exam": {"family": "oeif", "level": "A2"}, "branding": "DEUTSCHKOMPASS",
                "parts": [{}, {"picture": str(picture)}, {}],
                "promotion": {
                    "cover": str(picture), "pointing_emoji": str(picture),
                    "book_title": "ÖIF A2 Sprechen + Schreiben",
                    "youtube": "Amazon: Link in der Beschreibung", "social": "Amazon: Link in der Bio",
                    "cta": ["Jetzt selbst sprechen!", "Mehr Aufgaben und Modelldialoge",
                            "im ÖIF-A2-Buch Sprechen + Schreiben."],
                },
                "panels": review_panels(self.review), "picture_paths": [str(picture)] * 3,
            }
            turn = self.measured(24)
            timeline = {"fps": 24, "turns": [turn]}
            _, check = overlay({"turns": self.turns}, visual, timeline, "youtube", 2)
            marked = [t for t in check["text"] if "highlighted_word" in t]
            self.assertEqual(1, len(marked))
            self.assertEqual(turn["display_text"].split()[0], marked[0]["highlighted_word"])
            self.assertEqual("forced_alignment", marked[0]["highlight_kind"])
            self.assertFalse(check["picture_choice_topics_revealed"])

    def test_pipeline_routes_a2_and_does_not_use_pair_or_short_profile(self):
        import pipeline
        episode = {"id": "fixture", "turns": self.turns}
        with patch("sys.argv", ["pipeline.py", "build", "--episode", "a2.json",
                                "--build", "review", "--qwen-python", sys.executable]), \
                patch("pathlib.Path.read_text", return_value='{"template":"a2_speaking_full_preview"}'), \
                patch("a2_speaking_preview.load_preview", return_value=(episode, {})), \
                patch("a2_speaking_preview.build_preview") as build, \
                patch("pipeline.build_episode", side_effect=AssertionError("wrong template")):
            pipeline.main()
        build.assert_called_once()

    def test_tempo_and_long_duration_remain_enforced(self):
        episode = {"fps": 24, "speech_tempo": .8, "source": {"duration_limit_seconds": 900},
                   "scene": {"layout": "interview", "entrance": False}, "turns": [self.turns[0]]}
        turn = {**episode["turns"][0], "tempo_processing": {"tempo": .8}}
        timeline = {"fps": 24, "total_frames": 900 * 24, "turns": [turn]}
        with self.assertRaisesRegex(ValueError, "strictly below"):
            check_timeline(episode, timeline)
        timeline["total_frames"] = 100
        turn["tempo_processing"]["tempo"] = 1
        with self.assertRaisesRegex(ValueError, "Speech tempo"):
            check_timeline(episode, timeline)

    def test_loader_rejects_changed_transcript_and_wrong_preview_settings(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            transcript = root / "review.md"
            transcript.write_text("\n\n".join(
                f"**{n:02d} · {t['label']}**\n\n{t['text']}" for n, t in self.review.items()),
                encoding="utf-8")
            contact = root / "contacts"
            contact.mkdir()
            (contact / "request.json").write_text(json.dumps({
                "visual": {"scene": {}, "promotion": {}}, "panels": []}), encoding="utf-8")
            (contact / "export_manifest.json").write_text(json.dumps({
                "request.json": sha256_file(contact / "request.json")}), encoding="utf-8")
            audio = root / "reference.wav"
            with wave.open(str(audio), "wb") as wav:
                wav.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
                wav.writeframes(b"\xe8\x03\x18\xfc" * 24000)
            (root / "reference.txt").write_text("Reference text.", encoding="utf-8")
            episode = {
                "schema_version": 1, "id": "fixture", "template": "a2_speaking_full_preview",
                "exam": {"family": "oeif", "level": "A2", "skill": "speaking", "section": "all"},
                "title": "ÖIF A2 Sprechen mit Lea", "fps": 24, "speech_tempo": .8,
                "intro_seconds": 0, "outro_seconds": 2,
                "render": {"motion_step": 3, "native_scale": .25, "samples": 2},
                "output_formats": ["youtube"],
                "source": {"duration_limit_seconds": 900, "duration_exception": "Authorized full preview."},
                "contact_build": "contacts",
                "contact_manifest_sha256": sha256_file(contact / "export_manifest.json"),
                "review_script": "review.md", "review_script_sha256": sha256_file(transcript),
                "voices": {role: {"audio": "reference.wav", "transcript": "reference.txt"}
                           for role in ("candidate_a", "examiner")},
            }
            path = root / "episode.json"
            path.write_text(json.dumps(episode), encoding="utf-8")
            self.assertEqual(55, len(load_preview(path)[0]["turns"]))
            episode["speech_tempo"] = 1
            path.write_text(json.dumps(episode), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "0.8-tempo"):
                load_preview(path)
            episode["speech_tempo"] = .8
            path.write_text(json.dumps(episode), encoding="utf-8")
            transcript.write_text("Changed speech.", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "speech changed"):
                load_preview(path)


class A2ProductionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.source = self.root / "preview"
        self.source.mkdir()
        self.path = self.root / "production.json"
        self.visual = {"panels": []}
        original = {"id": "preview", "template": "a2_speaking_full_preview",
                    "fps": 24, "speech_tempo": .8, "turns": []}
        self.episode = {**original, "id": "production", "template": "a2_speaking_production",
                        "approved_preview": "preview",
                        "preview_approval": {"approved_by": "user", "approved_on": "2026-11-08"},
                        "render": {"motion_step": 2, "native_scale": 1., "samples": 8, "native_source": "youtube"},
                        "output_formats": ["youtube", "social"]}
        data = {
            "episode.json": original, "storyboard_episode.json": self.visual,
            "delivery_checks.json": {"status": "preview_only", "exports": {"youtube": {}},
                                    "source_sha256": {"asset_sha256": {}}},
            "speech_asr_check.json": {"all_match": False, "turns": [
                {"id": "a2_01", "matches": False, "recognized": "ASR fixture"},
                {"id": "a2_02", "matches": True}]},
            "timeline.json": {"turns": []}, "audio_timeline.json": {}, "word_alignment.json": {},
            "preview_state.json": {},
        }
        for name, value in data.items():
            (self.source / name).write_text(json.dumps(value), encoding="utf-8")
        for name in ("dialogue.wav", "preview_youtube.mp4", "subtitles.srt"):
            (self.source / name).write_bytes(b"synthetic fixture")
        self.repin()

    def repin(self):
        manifest_path = self.source / "export_manifest.json"
        previous = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
        manifest = {"files_sha256": {
            p.name: sha256_file(p) for p in self.source.iterdir()
            if p.is_file() and p.name != "export_manifest.json"},
            "generation_source_sha256": previous.get("generation_source_sha256", {})}
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        self.episode["approved_preview_manifest_sha256"] = sha256_file(manifest_path)

    def resolved(self):
        return resolve_production(copy.deepcopy(self.episode), self.path, self.visual)

    def test_approval_exact_content_and_source_hash_guards(self):
        self.assertEqual(str(self.source), self.resolved()["approved_preview"])
        for changes in ({"preview_approval": {}}, {"speech_tempo": 1}, {"turns": [{"speaker": "candidate_b"}]}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                resolve_production({**self.episode, **changes}, self.path, self.visual)
        (self.source / "dialogue.wav").write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "file changed"):
            self.resolved()

    def test_frozen_snapshot_is_verified_without_requiring_old_renderer_code(self):
        snapshot = self.source / "source_export"
        snapshot.mkdir()
        code = snapshot / "historical_renderer.py"
        code.write_text("historical fixture", encoding="utf-8")
        manifest_path = self.source / "export_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["generation_source_sha256"] = {code.name: sha256_file(code)}
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        self.repin()
        self.resolved()
        code.write_text("tampered", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "snapshot changed"):
            self.resolved()

    def test_exact_reuse_requires_selected_source_and_copies_flags_unchanged(self):
        episode = self.resolved()
        with self.assertRaisesRegex(ValueError, "--reuse-audio"):
            production_reuse_spec(episode, None)
        with self.assertRaisesRegex(ValueError, "--reuse-audio"):
            production_reuse_spec(episode, self.root)
        base_receipt = {"source": str(self.source), "voice_cache_sha256": {},
                        "files_sha256": {name: sha256_file(self.source / name)
                                         for name in ("dialogue.wav", "timeline.json", "word_alignment.json")}}
        with patch("pipeline.audio_reuse_spec", return_value=copy.deepcopy(base_receipt)):
            receipt = production_reuse_spec(episode, self.source)
        target = self.root / "target"
        target.mkdir()
        prepare_production_audio(target, receipt)
        for name in ("dialogue.wav", "timeline.json", "word_alignment.json", "speech_asr_check.json"):
            self.assertEqual(sha256_file(self.source / name), sha256_file(target / name))
        flags = json.loads((target / "auditory_review_flags.json").read_text(encoding="utf-8"))
        self.assertEqual([{"id": "a2_01", "matches": False, "recognized": "ASR fixture"}],
                         flags["asr_disagreements"])
        self.assertFalse(flags["human_listening_performed"])

    def test_changed_processed_clip_is_rejected(self):
        episode = self.resolved()
        audio = self.root / "clip.wav"
        audio.write_bytes(b"processed fixture")
        (self.source / "timeline.json").write_text(json.dumps({"turns": [{
            "id": "a2_01", "audio": str(audio), "raw_audio": str(audio),
            "tempo_processing": {"input_audio": str(audio), "input_sha256": "wrong"}}]}), encoding="utf-8")
        base = {"source": str(self.source), "files_sha256": {}, "voice_cache_sha256": {}}
        with patch("pipeline.audio_reuse_spec", return_value=base), \
                self.assertRaisesRegex(ValueError, "processed speech cache changed"):
            production_reuse_spec(episode, self.source)

    def test_full_resolution_shared_frame_plan_and_portrait_crop(self):
        from PIL import Image, ImageOps
        from long_speaking import FORMATS
        from long_speaking_preview import native_panel, output_name, output_sizes
        timeline = {"total_frames": 10, "turns": [
            {"start_frame": 0, "panel_id": "01_opening", "camera": "wide"},
            {"start_frame": 5, "panel_id": "contact_model", "camera": "candidate_a"},
            {"start_frame": 9, "panel_id": "12_final_cta", "camera": "wide"}]}
        plan = native_plan(self.episode, timeline)
        self.assertEqual([0, 2, 4, 5, 7], [p["frame"] for p in plan])
        self.assertEqual([1216, 580], plan[0]["size"])
        self.assertEqual({"youtube"}, {p["format"] for p in plan})
        self.assertEqual({"youtube": (1920, 1080), "social": (1080, 1920)}, output_sizes(self.episode))
        self.assertEqual("production_youtube.mp4", output_name(self.episode, "youtube"))
        image = Image.new("RGB", (1216, 580), "black")
        image.paste("red", (400, 0, 800, 580))
        box = FORMATS["social"]["scene"]
        size = box[2] - box[0], box[3] - box[1]
        expected = ImageOps.fit(image, size, Image.Resampling.LANCZOS, centering=(.5, .5))
        self.assertEqual(expected.tobytes(), native_panel(self.episode, "social", image).tobytes())

    def test_pipeline_dispatches_exact_audio_and_explicit_render_backend(self):
        import pipeline
        with patch("sys.argv", ["pipeline.py", "build", "--episode", "a2.json", "--build", "production",
                                "--profile", "production", "--reuse-audio", "preview",
                                "--render-device", "HIP", "--qwen-python", sys.executable]), \
                patch("pathlib.Path.read_text", return_value='{"template":"a2_speaking_production"}'), \
                patch("a2_speaking_preview.load_preview", return_value=({"id": "fixture"}, {})), \
                patch("a2_speaking_production.production_reuse_spec") as reuse, \
                patch("pipeline.check_render_device") as device, \
                patch("a2_speaking_preview.build_preview") as build, \
                patch("pipeline.build_episode", side_effect=AssertionError("wrong template")):
            pipeline.main()
        reuse.assert_called_once()
        device.assert_called_once_with("HIP")
        self.assertEqual("production", build.call_args.kwargs["profile"])
        self.assertEqual(Path("preview"), build.call_args.kwargs["reuse_audio"])
        self.assertEqual("HIP", build.call_args.kwargs["render_device"])


if __name__ == "__main__":
    unittest.main()
