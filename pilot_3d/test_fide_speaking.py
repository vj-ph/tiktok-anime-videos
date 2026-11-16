import copy
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fide_content import compile_turns, load_episode, pronunciation
from fide_speaking import STATIC, compose_turn, native_plan
from long_speaking_preview import caption_pages, caption_words, output_name, output_sizes
from prepare_audio import atomic_json, sha256_file

ROOT = Path(__file__).resolve().parent
EPISODE = ROOT / "episodes" / "fide_a2_b1_combined_full_preview.json"


class FideSpeakingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.episode, cls.pins = load_episode(EPISODE)
        except FileNotFoundError as error:
            raise unittest.SkipTest(f"Local book/scene assets are required: {error}")

    def test_complete_source_models_and_individual_cast(self):
        turns = self.episode["turns"]
        source = [t for t in turns if "source_segment" in t]
        self.assertEqual(34, len(source))
        self.assertEqual(34, len({t["source_segment"] for t in source}))
        self.assertTrue(all(t["display_text"] == t["source_text"] for t in source))
        self.assertEqual({"candidate_a", "examiner"}, {t["speaker"] for t in turns})
        picture = next(t for t in source if t["source_track"] == "fide_a2_037_picture")
        self.assertEqual("candidate_a", picture["speaker"])
        self.assertTrue(self.episode["scene"]["observer"])
        self.assertTrue(all(Path(v["audio"]).parent.name == "swiss" for v in self.episode["voices"].values()))

    def test_consent_precedes_topic_choice_and_b1_models(self):
        turns = self.episode["turns"]
        decision = next(i for i, t in enumerate(turns) if t["display_text"] == "Ja, ich möchte gerne B1 versuchen.")
        choice = next(i for i, t in enumerate(turns) if t["section"] == "b1_choice")
        b1 = next(i for i, t in enumerate(turns) if t.get("source_track", "").startswith("fide_b1"))
        self.assertLess(decision, choice)
        self.assertLess(choice, b1)
        self.assertIn("Möchten Sie das versuchen?", turns[decision - 1]["display_text"])
        self.assertIn("Nadia Hoxha", next(t["display_text"] for t in turns if t["section"] == "a2_phone"))
        self.assertIn("persönlich, Lea", next(t["display_text"] for t in turns if t["section"] == "a2_conversation"))

    def test_numbers_and_title_use_exact_measured_word_groups(self):
        spoken, groups = pronunciation(self.episode["title"], opening=True)
        self.assertEqual("fide Test A zwei B eins Sprechen Prüfungssimulation.", spoken)
        self.assertEqual([[0, 1], [2, 3, 4, 5], [6], [7]], groups)
        for turn in self.episode["turns"]:
            measured = {**turn, "wav_duration": len(turn["text"].split()) * .4 + .1,
                        "words": [{"word": w, "start": i * .4, "end": i * .4 + .3, "score": .9}
                                  for i, w in enumerate(turn["text"].split())]}
            self.assertEqual(turn["display_text"].split(), [w["word"] for w in caption_words(measured)])
        with self.assertRaisesRegex(ValueError, "Unmapped"):
            pronunciation("Um 17:30.")

    def test_native_plan_skips_static_tasks_and_restarts_at_cuts(self):
        timeline = {"total_frames": 20, "turns": [
            {"start_frame": 0, "panel_id": "welcome", "camera": "wide"},
            {"start_frame": 5, "panel_id": "a2_picture", "camera": "candidate_a"},
            {"start_frame": 10, "panel_id": "a2_phone", "camera": "examiner"},
            {"start_frame": 15, "panel_id": "cta", "camera": "wide"}]}
        plan = native_plan(self.episode, timeline)
        self.assertEqual([0, 3, 10, 13], [p["frame"] for p in plan])
        self.assertEqual({"youtube"}, {p["format"] for p in plan})
        self.assertIn("b1_choice", STATIC)

    def test_all_caption_pages_fit_both_layouts_and_correct_book(self):
        for turn in self.episode["turns"]:
            for mode in ("youtube", "social"):
                for first, last in caption_pages(turn):
                    image, check = compose_turn(self.episode, turn, mode, first, last)
                    self.assertEqual((1920, 1080) if mode == "youtube" else (1080, 1920), image.size)
                    if turn["kind"] == "cta":
                        self.assertEqual(2, check["cover_count"])
                        self.assertFalse(check["promo_group"])
                    else:
                        expected = self.episode["promotion"]["b1" if turn["section"].startswith("b1")
                                                             or turn["section"] == "closing" else "a2"]["url"]
                        self.assertEqual(expected, check["book_url"])

    def test_pipeline_dispatches_to_fide_not_oeif_or_short_route(self):
        import pipeline
        with patch("sys.argv", ["pipeline.py", "build", "--episode", "fide.json",
                                "--build", "fide-fixture", "--qwen-python", sys.executable]), \
                patch("pathlib.Path.read_text", return_value='{"template":"fide_speaking_full_preview"}'), \
                patch("fide_content.load_episode", return_value=(self.episode, {})), \
                patch("fide_speaking.build_preview") as build, \
                patch("pipeline.build_episode", side_effect=AssertionError("Wrong route")):
            pipeline.main()
        build.assert_called_once()

    def test_production_uses_full_size_shared_frames_without_preview_branding(self):
        episode = copy.deepcopy(self.episode)
        episode.update(template="fide_speaking_production",
                       render={"motion_step": 2, "native_scale": 1.0, "samples": 8, "native_source": "youtube"})
        self.assertEqual({"youtube": (1920, 1080), "social": (1080, 1920)}, output_sizes(episode))
        self.assertEqual("production_social.mp4", output_name(episode, "social"))
        timeline = {"total_frames": 15, "turns": [
            {"start_frame": 0, "panel_id": "welcome", "camera": "wide"},
            {"start_frame": 5, "panel_id": "a2_picture", "camera": "candidate_a"},
            {"start_frame": 10, "panel_id": "a2_phone", "camera": "examiner"}]}
        plan = native_plan(episode, timeline)
        self.assertEqual([0, 2, 4, 10, 12, 14], [p["frame"] for p in plan])
        self.assertTrue(all(p["size"] == [1216, 580] and p["format"] == "youtube" for p in plan))
        _, check = compose_turn(episode, episode["turns"][0], "youtube")
        self.assertNotIn("VORSCHAU", " ".join(line for text in check["text"] for line in text["lines"]))

    def test_pipeline_production_dispatch_requires_exact_reuse(self):
        import pipeline
        with patch("sys.argv", ["pipeline.py", "build", "--episode", "fide.json",
                                "--profile", "production", "--reuse-audio", "approved",
                                "--build", "fide-production", "--qwen-python", sys.executable]), \
                patch("pathlib.Path.read_text", return_value='{"template":"fide_speaking_production"}'), \
                patch("fide_content.load_episode", return_value=(self.episode, {})), \
                patch("fide_speaking_production.production_reuse_spec") as reuse, \
                patch("fide_speaking.build_preview") as build, \
                patch("pipeline.build_episode", side_effect=AssertionError("Wrong route")):
            pipeline.main()
        reuse.assert_called_once_with(self.episode, Path("approved"))
        self.assertEqual("production", build.call_args.kwargs["profile"])
        self.assertEqual(Path("approved"), build.call_args.kwargs["reuse_audio"])

    def test_loader_rejects_short_or_pair_configuration(self):
        data = json.loads(EPISODE.read_text(encoding="utf-8"))
        for patch_data in ({"source": {"duration_limit_seconds": 90}}, {"scene": {"layout": "pair"}}):
            changed = copy.deepcopy(data)
            changed.update(patch_data)
            with patch("fide_content.read_episode", return_value=changed):
                with self.assertRaisesRegex(ValueError, "bounded fide individual"):
                    load_episode(EPISODE)

    def test_targeted_revision_keeps_core_functions_and_slows_speech(self):
        revised, pins = load_episode(ROOT / "episodes" / "fide_a2_b1_trimmed_08_preview.json")
        self.assertEqual(.8, revised["speech_tempo"])
        personal = [t for t in revised["turns"] if t["section"] == "a2_conversation"]
        self.assertEqual(3, sum(t["speaker"] == "candidate_a" for t in personal))
        self.assertEqual(3, sum(t["speaker"] == "examiner" for t in personal) - 1)
        self.assertIn("einzelnen Schritte", personal[-2]["display_text"])
        self.assertNotIn("gesund bleiben", " ".join(t["display_text"] for t in personal))
        for section in ("a2_phone", "b1_experience", "b1_process", "b1_aspects", "b1_hypothesis"):
            original = [t["source_segment"] for t in self.episode["turns"]
                        if t["section"] == section and "source_segment" in t]
            actual = [t["source_segment"] for t in revised["turns"]
                      if t["section"] == section and "source_segment" in t]
            self.assertEqual(original, actual)
        for section in ("b1_process", "b1_aspects", "b1_hypothesis"):
            self.assertFalse(any(t["section"] == section and t["speaker"] == "candidate_a"
                                 and "source_segment" not in t for t in revised["turns"]))
        for asset in revised["scene"]["swiss_flags"].values():
            self.assertIn(asset, pins)
        for turn in revised["turns"]:
            for mode in ("youtube", "social"):
                for first, last in caption_pages(turn):
                    compose_turn(revised, turn, mode, first, last)
        routing = [t for t in revised["turns"] if t["section"] == "routing"]
        self.assertIn("A1", routing[0]["display_text"])
        self.assertIn("Verstehen", routing[0]["display_text"])
        self.assertIn("Möchten Sie das versuchen?", routing[0]["display_text"])
        self.assertEqual("Ja, ich möchte gerne B1 versuchen.", routing[1]["display_text"])

    def test_explicit_source_selection_still_rejects_missing_or_duplicate_segments(self):
        tracks = {"one": {"track_id": "one", "model_kind": "picture", "segments": [
            {"segment_id": "a", "speaker_label": "Kandidat/in", "text_original": "Ein Bild."},
            {"segment_id": "b", "speaker_label": "Kandidat/in", "text_original": "Noch ein Bild."}]}}
        block = {"section": "a2_picture", "track": "one", "segments": [0]}
        self.assertEqual("a", compile_turns([block], tracks, {"one": [0]})[0]["source_segment"])
        with self.assertRaisesRegex(ValueError, "exactly once"):
            compile_turns([block], tracks)
        with self.assertRaisesRegex(ValueError, "exactly once"):
            compile_turns([block, block], tracks, {"one": [0]})
        with self.assertRaisesRegex(ValueError, "Invalid source selection"):
            compile_turns([block], tracks, {"one": [0, 0]})


class FideProductionApprovalTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "preview"
        self.source.mkdir()
        self.path = self.root / "production.json"
        original = {"template": "fide_speaking_full_preview", "title": "Approved title",
                    "render": {"native_scale": .25}, "turns": [{"text": "Guten Tag."}]}
        self.episode = {**original, "template": "fide_speaking_production",
                        "render": {"native_scale": 1.0}, "approved_preview": "preview",
                        "preview_approval": {"approved_by": "user", "approved_on": "2026-11-14"}}
        self.asset = self.root / "flag.png"
        self.asset.write_bytes(b"approved flag")
        self.snapshot = self.source / "source_export" / "scene.py"
        self.snapshot.parent.mkdir()
        self.snapshot.write_bytes(b"approved generation code")
        for name in ("preview_youtube.mp4", "preview_social.mp4", "dialogue.wav", "timeline.json",
                     "audio_timeline.json", "word_alignment.json", "subtitles.srt", "speech_asr_check.json",
                     "speech_chain_hashes.json", "preview_state.json"):
            (self.source / name).write_bytes(b"verified fixture")
        for name in ("episode.json", "storyboard_episode.json"):
            atomic_json(self.source / name, original)
        atomic_json(self.source / "delivery_checks.json", {
            "status": "full_length_preview_only", "exports": {"youtube": {}, "social": {}},
            "source_sha256": {"asset_sha256": {str(self.asset): sha256_file(self.asset)}}})
        self.manifest = {"files_sha256": {p.name: sha256_file(p) for p in self.source.iterdir() if p.is_file()},
                         "generation_source_sha256": {"scene.py": sha256_file(self.snapshot)}}
        self.pin_manifest()

    def pin_manifest(self):
        target = self.source / "export_manifest.json"
        atomic_json(target, self.manifest)
        self.episode["approved_preview_manifest_sha256"] = sha256_file(target)

    def resolve(self, **changes):
        from fide_speaking_production import resolve_production
        return resolve_production(copy.deepcopy({**self.episode, **changes}), self.path)

    def test_rejects_missing_approval_changed_content_and_changed_manifest(self):
        self.resolve()
        with self.assertRaisesRegex(ValueError, "approval"):
            self.resolve(preview_approval={})
        with self.assertRaisesRegex(ValueError, "content differs"):
            self.resolve(title="Different speech")
        (self.source / "export_manifest.json").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "manifest changed"):
            self.resolve()

    def test_both_complete_exports_must_be_unchanged(self):
        video = self.source / "preview_social.mp4"
        video.write_bytes(b"corrupt")
        with self.assertRaisesRegex(ValueError, "preview file changed"):
            self.resolve()
        del self.manifest["files_sha256"]["preview_social.mp4"]
        self.pin_manifest()
        with self.assertRaisesRegex(ValueError, "both complete"):
            self.resolve()

    def test_preserves_approved_assets_and_frozen_source_snapshots(self):
        self.asset.write_bytes(b"different flag")
        with self.assertRaisesRegex(ValueError, "asset changed"):
            self.resolve()
        self.asset.write_bytes(b"approved flag")
        self.snapshot.write_bytes(b"different code")
        with self.assertRaisesRegex(ValueError, "snapshot changed"):
            self.resolve()

    def test_exact_reuse_also_pins_pre_tempo_metadata(self):
        from fide_speaking_production import production_reuse_spec
        metadata = self.root / "pre_tempo.cache.json"
        metadata.write_bytes(b"approved metadata")
        atomic_json(self.source / "speech_chain_hashes.json", {str(metadata): sha256_file(metadata)})
        with patch("fide_speaking_production.exact_audio_reuse_spec", return_value={
                "source": str(self.source), "files_sha256": {}, "clip_sha256": {}}):
            receipt = production_reuse_spec(self.episode, self.source)
            self.assertEqual(sha256_file(metadata), receipt["clip_sha256"][str(metadata)])
            metadata.write_bytes(b"corrupt metadata")
            with self.assertRaisesRegex(ValueError, "speech chain changed"):
                production_reuse_spec(self.episode, self.source)


if __name__ == "__main__":
    unittest.main()
