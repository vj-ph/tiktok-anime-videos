import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import wave

import numpy as np

import long_speaking_production as production
from long_speaking_preview import (
    native_plan, output_name, output_sizes, load_preview, overlay,
)
from prepare_audio import atomic_json, sha256_file
import test_long_speaking as fixtures


class ProductionReuseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source, self.approved = self.root / "source", self.root / "approved"
        self.source.mkdir()
        self.approved.mkdir()
        self.expected_turns = [
            {"id": "opening", "text": "Titel", "kind": "opening"},
            {"id": "teil3_instruction", "text": "Planen", "kind": "task"},
        ]
        self.timeline = {
            "language": "de", "fps": 24, "intro_seconds": 0, "outro_seconds": 0,
            "total_frames": 48, "duration": 2, "word_alignment": {"language": "de"},
            "turns": [
                {**turn, "start": i, "end": i + 1, "start_frame": i * 24,
                 "end_frame": (i + 1) * 24, "wav_duration": 1,
                 "alignment_key": str(i),
                 "tempo_processing": {"tempo": .85},
                 "words": [{"word": turn["text"], "start": .1, "end": .8, "score": .9}]}
                for i, turn in enumerate(self.expected_turns)
            ],
        }
        atomic_json(self.source / "timeline.json", self.timeline)
        self.pcm = (np.sin(np.arange(96000) * .03) * 12000).astype("<i2").tobytes()
        self.write_wav(self.source / "dialogue.wav", self.pcm)
        atomic_json(self.source / "word_alignment.json", {
            "provenance": self.timeline["word_alignment"],
            "turns": [{key: t[key] for key in ("id", "start", "words", "alignment_key")}
                      for t in self.timeline["turns"]],
        })
        atomic_json(self.source / "speech_asr_check.json", {"all_match": True, "turns": []})
        atomic_json(self.source / "delivery_checks.json", {"asset_sha256": {}})
        atomic_json(self.source / "export_manifest.json", {
            "files_sha256": {p.name: sha256_file(p) for p in self.source.iterdir()},
        })
        self.playback = copy.deepcopy(self.timeline)
        self.playback.update(total_frames=192, duration=8)
        for key in ("start", "end"):
            self.playback["turns"][1][key] += 6
        for key in ("start_frame", "end_frame"):
            self.playback["turns"][1][key] += 144
        atomic_json(self.approved / "playback_timeline.json", self.playback)
        self.write_wav(self.approved / "dialogue_with_notice.wav",
                       self.pcm[:96000] + bytes(576000) + self.pcm[96000:])
        atomic_json(self.approved / "edit_manifest.json", {
            "source": str(self.source), "fps": 24, "source_frames": 48,
            "source_export_manifest_sha256": sha256_file(self.source / "export_manifest.json"),
            "insert_before_source_frame": 24, "notice_frames": 144, "notice_seconds": 6,
            "notice_text": production.NOTICE_TEXT, "spoken_text": None, "speech_tempo": .85,
        })
        atomic_json(self.approved / "delivery_checks.json", {
            "status": "verified_postproduction_preview", "visual_review": {"completed": True},
            "new_tts": False, "new_native_rendering": False,
        })
        atomic_json(self.approved / "auditory_review_flags.json", {"items": []})
        for mode in ("youtube", "social"):
            (self.approved / f"notice_{mode}.png").write_bytes(b"verified-card")
        self.episode = {
            "template": "long_speaking_production", "language": "de",
            "fps": 24, "speech_tempo": .85, "intro_seconds": 0, "outro_seconds": 0,
            "scene": {"entrance": False}, "turns": self.expected_turns,
            "source": {"duration_limit_seconds": 900}, "approved_preview": str(self.approved),
            "silent_notice": {"before_turn": "teil3_instruction", "seconds": 6,
                             "text": production.NOTICE_TEXT},
        }
        self.freeze_approved()
        self.reuse = patch("pipeline.audio_reuse_spec", return_value={
            "source": str(self.source), "files_sha256": {
                name: sha256_file(self.source / name)
                for name in ("dialogue.wav", "timeline.json", "word_alignment.json")},
            "voice_cache_sha256": {},
        })
        self.audio_spec = self.reuse.start()
        self.addCleanup(self.reuse.stop)

    @staticmethod
    def write_wav(path, data):
        with wave.open(str(path), "wb") as wav:
            wav.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
            wav.writeframes(data)

    def freeze_approved(self):
        atomic_json(self.approved / "export_manifest.json", {
            "files_sha256": {name: sha256_file(self.approved / name)
                             for name in production.APPROVED_FILES},
        })
        self.episode["approved_preview_manifest_sha256"] = sha256_file(
            self.approved / "export_manifest.json")

    def test_exact_reuse_preserves_pcm_local_words_and_shifts_only_absolute_positions(self):
        receipt = production.production_reuse_spec(self.episode, self.source)
        build = self.root / "production"
        build.mkdir()
        with patch("prepare_audio.synthesize", side_effect=AssertionError("TTS must not run")):
            production.prepare_production_audio(build, self.episode, receipt)
        self.assertEqual(sha256_file(self.approved / "dialogue_with_notice.wav"),
                         sha256_file(build / "dialogue.wav"))
        timeline = json.loads((build / "timeline.json").read_text())
        self.assertEqual(192, timeline["total_frames"])
        self.assertEqual(7, timeline["turns"][1]["start"])
        self.assertEqual(self.timeline["turns"][1]["words"], timeline["turns"][1]["words"])
        self.assertIsNone(production.notice_at(timeline, 23))
        self.assertIsNotNone(production.notice_at(timeline, 24))
        self.assertIsNotNone(production.notice_at(timeline, 167))
        self.assertIsNone(production.notice_at(timeline, 168))
        alignment = json.loads((build / "word_alignment.json").read_text())
        self.assertEqual(7, alignment["turns"][1]["start"])
        self.assertEqual(sha256_file(self.source / "speech_asr_check.json"),
                         sha256_file(build / "speech_asr_check.json"))
        self.audio_spec.assert_called_once_with(self.episode, self.source)

    def test_missing_reuse_and_other_source_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "requires --reuse-audio"):
            production.production_reuse_spec(self.episode, None)
        other = self.root / "other"
        other.mkdir()
        with self.assertRaisesRegex(ValueError, "source differs"):
            production.production_reuse_spec(self.episode, other)

    def test_unverified_preview_or_modified_base_manifest_is_rejected(self):
        report = json.loads((self.approved / "delivery_checks.json").read_text())
        report["visual_review"]["completed"] = False
        atomic_json(self.approved / "delivery_checks.json", report)
        self.freeze_approved()
        with self.assertRaisesRegex(ValueError, "visually reviewed"):
            production.production_reuse_spec(self.episode, self.source)
        report["visual_review"]["completed"] = True
        atomic_json(self.approved / "delivery_checks.json", report)
        self.freeze_approved()
        (self.source / "export_manifest.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "base delivery manifest changed"):
            production.production_reuse_spec(self.episode, self.source)

    def test_changed_tempo_or_card_bytes_are_rejected(self):
        self.episode["speech_tempo"] = .9
        with self.assertRaisesRegex(ValueError, "notice or tempo differs"):
            production.production_reuse_spec(self.episode, self.source)
        self.episode["speech_tempo"] = .85
        (self.approved / "notice_social.png").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "preview changed"):
            production.production_reuse_spec(self.episode, self.source)

    def test_changed_speech_or_word_intervals_cannot_be_hidden_by_a_new_manifest(self):
        final = bytearray((self.approved / "dialogue_with_notice.wav").read_bytes())
        final[100] ^= 16
        (self.approved / "dialogue_with_notice.wav").write_bytes(final)
        self.freeze_approved()
        with self.assertRaisesRegex(ValueError, "exact speech plus digital silence"):
            production.production_reuse_spec(self.episode, self.source)
        self.write_wav(self.approved / "dialogue_with_notice.wav",
                       self.pcm[:96000] + bytes(576000) + self.pcm[96000:])
        self.playback["turns"][1]["words"][0]["start"] += .01
        atomic_json(self.approved / "playback_timeline.json", self.playback)
        self.freeze_approved()
        with self.assertRaisesRegex(ValueError, "measured word timing"):
            production.production_reuse_spec(self.episode, self.source)

    def test_changed_notice_position_or_duration_is_rejected(self):
        edit = json.loads((self.approved / "edit_manifest.json").read_text())
        edit["insert_before_source_frame"] += 1
        atomic_json(self.approved / "edit_manifest.json", edit)
        self.freeze_approved()
        with self.assertRaisesRegex(ValueError, "measured Teil 3 boundary"):
            production.production_reuse_spec(self.episode, self.source)
        self.episode["silent_notice"]["seconds"] = 5
        with self.assertRaisesRegex(ValueError, "notice or tempo differs"):
            production.production_reuse_spec(self.episode, self.source)

    def test_silent_hold_counts_towards_the_strict_encoded_duration_limit(self):
        receipt = production.production_reuse_spec(self.episode, self.source)
        self.episode["source"]["duration_limit_seconds"] = 8
        build = self.root / "production"
        build.mkdir()
        with self.assertRaisesRegex(ValueError, "strictly below"):
            production.prepare_production_audio(build, self.episode, receipt)
        self.assertFalse((build / "dialogue.wav").exists())

    def test_notice_seconds_and_base_frame_clock_must_match_the_approved_edit(self):
        edit = json.loads((self.approved / "edit_manifest.json").read_text())
        edit["notice_seconds"] = 7
        atomic_json(self.approved / "edit_manifest.json", edit)
        self.freeze_approved()
        with self.assertRaisesRegex(ValueError, "notice or tempo differs"):
            production.production_reuse_spec(self.episode, self.source)
        edit["notice_seconds"] = 6
        edit["source_frames"] += 1
        atomic_json(self.approved / "edit_manifest.json", edit)
        self.freeze_approved()
        with self.assertRaisesRegex(ValueError, "base frame clock differs"):
            production.production_reuse_spec(self.episode, self.source)

    def test_audio_stage_resume_never_invokes_synthesis_and_repairs_only_derived_outputs(self):
        from long_speaking_preview import build_preview

        fixture = fixtures.LongSpeakingTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        episode = copy.deepcopy(self.episode)
        episode.update(storyboard=str(fixture.path), review_script=str(fixture.path),
                       review_manifest=str(fixture.path), voices={
                           "examiner": {"audio": str(self.source / "dialogue.wav"),
                                        "transcript": str(fixture.root / "book.md")}},
                       scene={**episode["scene"],
                              "base_scene": fixture.episode["scene"]["base_scene"]},
                       render={"motion_step": 1, "native_scale": 1, "samples": 16})
        (fixture.root / "teil1_revision.json").write_text("{}")
        build = self.root / "production"
        with patch("long_speaking_preview.load_preview", return_value=(episode, fixture.episode)), \
                patch("long_speaking_production.production_inputs", return_value=[]), \
                patch("long_speaking_preview.caption_preflight"), \
                patch("long_speaking_preview.native_plan", return_value=[]), \
                patch("pipeline.run_command",
                      side_effect=AssertionError("No inference subprocess may run")):
            build_preview(fixture.path, build, until="audio", profile="production",
                          reuse_audio=self.source)
            (build / "dialogue.wav").write_bytes(b"corrupt derived output")
            build_preview(fixture.path, build, until="audio", profile="production",
                          reuse_audio=self.source)
            self.assertEqual(sha256_file(self.approved / "dialogue_with_notice.wav"),
                             sha256_file(build / "dialogue.wav"))
            state = json.loads((build / "production_state.json").read_text())
            self.assertEqual({"audio_reuse"}, set(state["stages"]))
            self.assertTrue((build / "source_export" / "long_speaking_production.py").is_file())
            frozen = sha256_file(build / "production_state.json")
            with self.assertRaisesRegex(ValueError, "inputs changed"):
                build_preview(fixture.path, build, until="audio", profile="production",
                              reuse_audio=self.source, render_device="HIP")
            self.assertEqual(frozen, sha256_file(build / "production_state.json"))
            with self.assertRaisesRegex(ValueError, "both verified source builds"):
                build_preview(fixture.path, self.approved / "nested-output", until="audio",
                              profile="production", reuse_audio=self.source)


class ProductionSceneReuseTests(unittest.TestCase):
    def setUp(self):
        self.audio = ProductionReuseTests()
        self.audio.setUp()
        self.addCleanup(self.audio.doCleanups)
        self.visual = fixtures.LongSpeakingTests()
        self.visual.setUp()
        self.addCleanup(self.visual.doCleanups)
        self.root = self.audio.root
        self.source = self.root / "baked"
        self.source.mkdir()
        self.storyboard = self.visual.episode
        for timeline in (self.audio.timeline, self.audio.playback):
            for turn, panel, camera in zip(timeline["turns"],
                                           ("01_opening", "08_teil3_task"), ("wide", "candidates")):
                turn.update(panel_id=panel, camera=camera)
        atomic_json(self.audio.source / "timeline.json", self.audio.timeline)
        atomic_json(self.audio.source / "export_manifest.json", {
            "files_sha256": {p.name: sha256_file(p) for p in self.audio.source.iterdir()
                             if p.name != "export_manifest.json"}})
        self.audio.audio_spec.return_value["files_sha256"]["timeline.json"] = sha256_file(
            self.audio.source / "timeline.json")
        edit = json.loads(production.read_json(self.audio.approved / "edit_manifest.json"))
        edit["source_export_manifest_sha256"] = sha256_file(self.audio.source / "export_manifest.json")
        atomic_json(self.audio.approved / "edit_manifest.json", edit)
        atomic_json(self.audio.approved / "playback_timeline.json", self.audio.playback)
        self.audio.freeze_approved()
        self.episode = copy.deepcopy(self.audio.episode)
        self.episode.update(
            id="shared", storyboard=str(self.visual.path), review_script=str(self.visual.path),
            review_manifest=str(self.visual.path), voices={
                "examiner": {"audio": str(self.audio.source / "dialogue.wav"),
                             "transcript": str(self.visual.root / "book.md")}},
            scene={**self.episode["scene"], "base_scene": self.visual.episode["scene"]["base_scene"]},
            render={"motion_step": 2, "native_scale": 1.0, "samples": 8, "native_source": "youtube"})
        (self.visual.root / "teil1_revision.json").write_text("{}")
        self.reuse = production.production_reuse_spec(self.episode, self.audio.source)
        original = copy.deepcopy(self.episode)
        original.update(id="original", render={"motion_step": 1, "native_scale": 1.0, "samples": 16})
        production.prepare_production_audio(self.source, original, self.reuse)
        self.timeline = json.loads(production.read_json(self.source / "timeline.json"))
        self.original_plan = native_plan(original, self.storyboard, self.timeline)
        atomic_json(self.source / "native_plan.json", self.original_plan)
        atomic_json(self.source / "episode.json", original)
        atomic_json(self.source / "storyboard_episode.json", self.storyboard)
        (self.source / "preview.blend").write_bytes(b"unit-test baked-scene fixture")
        self.checks = {
            "preview_scene_sha256": sha256_file(self.source / "preview.blend"),
            "hair_hangs_down_all_sampled_frames": True,
            "all_planned_head_and_hair_bounds_fit": True,
            "camera_lenses": {f"Preview {p['format']} {p['camera']}": 28 for p in self.original_plan},
        }
        atomic_json(self.source / "scene_checks.json", self.checks)
        from long_speaking_preview import ROOT, SOURCES
        snapshot = self.source / "source_export"
        snapshot.mkdir()
        for name in SOURCES:
            shutil.copy2(ROOT / name, snapshot / name)
        self.state = {
            "spec": {"episode": original, "audio_reuse": self.reuse,
                     "code_sha256": {name: sha256_file(snapshot / name) for name in SOURCES},
                     "asset_sha256": {original["scene"]["base_scene"]: sha256_file(
                         Path(original["scene"]["base_scene"]))}},
            "stages": {
                "scene": {name: sha256_file(self.source / name)
                          for name in ("preview.blend", "scene_checks.json")},
                "audio_reuse": {name: sha256_file(self.source / name) for name in (
                    "dialogue.wav", "timeline.json", "word_alignment.json", "audio_reuse.json",
                    "speech_asr_check.json", "auditory_review_flags.json", "subtitles.srt")},
            },
        }
        self.save_state()

    def save_state(self):
        atomic_json(self.source / "production_state.json", self.state)

    def receipt(self):
        return production.production_scene_reuse_spec(
            self.episode, self.storyboard, self.reuse, self.source)

    def test_exact_scene_copy_preserves_source_and_records_inherited_checks(self):
        before = {p: sha256_file(p) for p in self.source.rglob("*") if p.is_file()}
        receipt = self.receipt()
        target = self.root / "copy"
        target.mkdir()
        production.prepare_reused_scene(target, receipt)
        for name in ("preview.blend", "scene_checks.json"):
            self.assertEqual(sha256_file(self.source / name), sha256_file(target / name))
        self.assertEqual(receipt, json.loads(production.read_json(target / "scene_reuse.json")))
        self.assertEqual(before, {p: sha256_file(p) for p in before})

    def test_missing_scene_checkpoint_and_changed_scene_bytes_are_rejected(self):
        stage = self.state["stages"].pop("scene")
        self.save_state()
        with self.assertRaisesRegex(ValueError, "complete scene checkpoint"):
            self.receipt()
        self.state["stages"]["scene"] = stage
        self.save_state()
        (self.source / "preview.blend").write_bytes(b"modified")
        with self.assertRaisesRegex(ValueError, "checkpoint changed: preview.blend"):
            self.receipt()

    def test_changed_frozen_code_and_changed_scene_inputs_are_rejected(self):
        path = self.source / "source_export" / "long_speaking_scene.py"
        path.write_text("# different scene implementation")
        with self.assertRaisesRegex(ValueError, "snapshot changed"):
            self.receipt()
        self.state["spec"]["code_sha256"][path.name] = sha256_file(path)
        self.save_state()
        with self.assertRaisesRegex(ValueError, "implementation differs"):
            self.receipt()
        from long_speaking_preview import ROOT
        shutil.copy2(ROOT / path.name, path)
        self.state["spec"]["code_sha256"][path.name] = sha256_file(path)
        self.save_state()
        Path(self.episode["scene"]["base_scene"]).write_bytes(b"modified base asset")
        with self.assertRaisesRegex(ValueError, "scene input changed"):
            self.receipt()

    def test_render_orchestration_changes_do_not_require_rebaking(self):
        path = self.source / "source_export" / "long_speaking_preview.py"
        path.write_text("# earlier render/export orchestration")
        self.state["spec"]["code_sha256"][path.name] = sha256_file(path)
        self.save_state()
        self.assertEqual(str(self.source), self.receipt()["source"])

    def test_changed_animation_episode_and_exact_timeline_are_rejected(self):
        for key, value in (("fps", 30), ("intro_seconds", 1), ("scene", {"entrance": True}),
                           ("voices", {}), ("turns", [])):
            original = self.episode[key]
            self.episode[key] = value
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "animation/episode"):
                self.receipt()
            self.episode[key] = original
        self.timeline["turns"][0]["end_frame"] -= 1
        atomic_json(self.source / "timeline.json", self.timeline)
        self.state["stages"]["audio_reuse"]["timeline.json"] = sha256_file(self.source / "timeline.json")
        self.save_state()
        with self.assertRaisesRegex(ValueError, "measured timeline"):
            self.receipt()

    def test_changed_pcm_is_rejected_even_with_a_new_checkpoint_hash(self):
        (self.source / "dialogue.wav").write_bytes(b"not the approved PCM")
        self.state["stages"]["audio_reuse"]["dialogue.wav"] = sha256_file(self.source / "dialogue.wav")
        self.save_state()
        with self.assertRaisesRegex(ValueError, "PCM differs"):
            self.receipt()

    def test_incomplete_plan_or_missing_camera_proof_is_rejected(self):
        atomic_json(self.source / "native_plan.json", self.original_plan[:-1])
        with self.assertRaisesRegex(ValueError, "native plan differs"):
            self.receipt()
        atomic_json(self.source / "native_plan.json", self.original_plan)
        del self.checks["camera_lenses"]["Preview youtube wide"]
        atomic_json(self.source / "scene_checks.json", self.checks)
        self.state["stages"]["scene"]["scene_checks.json"] = sha256_file(self.source / "scene_checks.json")
        self.save_state()
        with self.assertRaisesRegex(ValueError, "cameras/frames"):
            self.receipt()

    def test_new_native_frames_must_be_a_subset_of_the_verified_bake(self):
        desired = native_plan(self.episode, self.storyboard, self.timeline)
        desired[0]["frame"] = self.timeline["total_frames"] + 1
        with patch("long_speaking_preview.native_plan", side_effect=[self.original_plan, desired]):
            with self.assertRaisesRegex(ValueError, "cameras/frames"):
                self.receipt()

    def test_source_overlap_and_source_changes_after_preflight_are_rejected(self):
        receipt = self.receipt()
        with self.assertRaisesRegex(ValueError, "separate from the baked scene source"):
            production.prepare_reused_scene(self.source, receipt)
        with self.assertRaisesRegex(ValueError, "separate from the baked scene source"):
            production.prepare_reused_scene(self.source / "nested", receipt)
        (self.source / "preview.blend").write_bytes(b"changed after preflight")
        target = self.root / "copy"
        target.mkdir()
        with self.assertRaisesRegex(ValueError, "source changed before copying"):
            production.prepare_reused_scene(target, receipt)
        self.assertFalse((target / "preview.blend").exists())

    def test_scene_stage_resume_and_repair_never_invoke_blender_or_tts(self):
        from long_speaking_preview import build_preview

        target = self.root / "shared-production"
        kwargs = dict(until="scene", profile="production", reuse_audio=self.audio.source,
                      reuse_scene=self.source)
        before = sha256_file(self.source / "production_state.json")
        with patch("long_speaking_preview.load_preview", return_value=(self.episode, self.storyboard)), \
                patch("long_speaking_production.production_inputs", return_value=[]), \
                patch("long_speaking_preview.caption_preflight"), \
                patch("pipeline.run_command", side_effect=AssertionError("No subprocess may run")):
            build_preview(self.visual.path, target, **kwargs)
            saved = sha256_file(target / "production_state.json")
            build_preview(self.visual.path, target, **kwargs)
            self.assertEqual(saved, sha256_file(target / "production_state.json"))
            (target / "preview.blend").write_bytes(b"corrupt derived copy")
            build_preview(self.visual.path, target, **kwargs)
            self.assertEqual(sha256_file(self.source / "preview.blend"),
                             sha256_file(target / "preview.blend"))
            with self.assertRaisesRegex(ValueError, "inputs changed"):
                build_preview(self.visual.path, target, **{**kwargs, "reuse_scene": None})
            with self.assertRaisesRegex(ValueError, "separate from the baked scene source"):
                build_preview(self.visual.path, self.source / "nested", **kwargs)
        state = json.loads(production.read_json(target / "production_state.json"))
        self.assertEqual({"audio_reuse", "scene"}, set(state["stages"]))
        self.assertEqual(before, sha256_file(self.source / "production_state.json"))

    def test_both_workers_override_saved_samples_and_render_only_youtube(self):
        from long_speaking_preview import build_preview
        import math
        from types import SimpleNamespace
        from threading import Lock

        target = self.root / "shared-production"
        seen, lock = [], Lock()
        bpy = SimpleNamespace(context=SimpleNamespace(scene=SimpleNamespace(cycles=None)))

        def render(command, log):
            self.assertNotIn("--bake", command)
            worker = int(command[command.index("--worker") + 1])
            jobs = int(command[command.index("--jobs") + 1])
            with lock:
                bpy.context.scene.cycles = SimpleNamespace(samples=16, use_denoising=False)
                exec(command[command.index("--python-expr") + 1])
                self.assertEqual(8, bpy.context.scene.cycles.samples)
                self.assertTrue(bpy.context.scene.cycles.use_denoising)
                seen.append(worker)
            plan = json.loads(production.read_json(target / "native_plan.json"))
            count = math.ceil(len(plan) / jobs)
            checks = []
            for item in plan[worker * count:(worker + 1) * count]:
                self.assertEqual("youtube", item["format"])
                image = target / item["file"]
                image.parent.mkdir(exist_ok=True)
                image.write_bytes(b"mocked native frame")
                checks.append({**item, "sha256": sha256_file(image)})
            atomic_json(target / f"native_checks_{worker}.json", checks)

        def encode(build, episode, storyboard, timeline, mode):
            (build / output_name(episode, mode)).write_bytes(b"mocked encoding")

        with patch("long_speaking_preview.load_preview", return_value=(self.episode, self.storyboard)), \
                patch("long_speaking_production.production_inputs", return_value=[]), \
                patch("long_speaking_preview.caption_preflight"), \
                patch("pipeline.run_command", side_effect=render), \
                patch.dict("sys.modules", {"bpy": bpy}), \
                patch("long_speaking_preview.encode", side_effect=encode), \
                patch("long_speaking_preview.review_export", return_value={"mocked": True}):
            build_preview(self.visual.path, target, jobs=2, profile="production",
                          reuse_audio=self.audio.source, reuse_scene=self.source)
        self.assertEqual([0, 1], sorted(seen))
        checks = json.loads(production.read_json(target / "delivery_checks.json"))
        self.assertEqual(str(self.source), checks["scene_reuse"]["source"])


class ProductionLayoutTests(unittest.TestCase):
    def test_shared_native_plan_is_youtube_only_on_twos_and_skips_notice(self):
        episode = {"template": "long_speaking_production", "render": {
            "motion_step": 2, "native_scale": 1.0, "samples": 8, "native_source": "youtube"}}
        timeline = {"total_frames": 15, "turns": [
            {"start_frame": 0, "panel_id": "01_opening", "camera": "wide"},
            {"start_frame": 7, "panel_id": "08_teil3_task", "camera": "candidates"},
            {"start_frame": 12, "panel_id": "12_final_cta", "camera": None},
        ], "silent_notices": [{"id": "notice", "start_frame": 3, "end_frame": 7}]}
        with patch("long_speaking_preview.compile_script"), patch("long_speaking_preview.panels",
                return_value=[{"id": "01_opening", "camera": "wide"},
                              {"id": "08_teil3_task", "camera": "candidates"}]):
            plan = native_plan(episode, {}, timeline)
        self.assertEqual([0, 2, 7, 9, 11], [item["frame"] for item in plan])
        self.assertEqual({"youtube"}, {item["format"] for item in plan})
        self.assertEqual({(1216, 580)}, {tuple(item["size"]) for item in plan})

    def test_shared_social_panel_is_exact_fixed_center_crop_without_repositioning(self):
        from PIL import Image, ImageChops
        from long_speaking_preview import native_panel

        episode = {"template": "long_speaking_production", "render": {"native_source": "youtube"}}
        image = Image.new("RGB", (1216, 580))
        image.putdata([(x % 256, y % 256, (x + y) % 256)
                       for y in range(580) for x in range(1216)])
        width = 580 * 836 / 505
        expected = image.resize((836, 505), Image.Resampling.LANCZOS,
                                box=((1216 - width) / 2, 0, (1216 + width) / 2, 580))
        actual = native_panel(episode, "social", image)
        self.assertIsNone(ImageChops.difference(expected, actual).getbbox())
        self.assertEqual(image.tobytes(), native_panel(episode, "youtube", image).tobytes())
        original = {"template": "long_speaking_production", "render": {}}
        self.assertEqual(
            image.resize((836, 505), Image.Resampling.LANCZOS).tobytes(),
            native_panel(original, "social", image).tobytes())

    def test_shared_render_rejects_unapproved_sampling_or_missing_native_source(self):
        import copy

        base = {"template": "long_speaking_production", "source": {"duration_limit_seconds": 900},
                "fps": 24, "intro_seconds": 0, "scene": {"entrance": False}}
        for render in (
                {"motion_step": 1, "native_scale": 1.0, "samples": 8, "native_source": "youtube"},
                {"motion_step": 2, "native_scale": 1.0, "samples": 8},
                {"motion_step": 2, "native_scale": 1.0, "samples": 8, "native_source": "social"}):
            episode = {**copy.deepcopy(base), "render": render}
            with self.subTest(render=render), patch("long_speaking_preview.read_episode", return_value=episode), \
                    patch("long_speaking_production.resolve_production", return_value=episode), \
                    patch("long_speaking_preview.validate_episode"):
                with self.assertRaisesRegex(ValueError, "production quality"):
                    load_preview(Path(__file__), "production")

    def test_native_full_resolution_per_frame_plan_omits_silent_hold(self):
        episode = {"template": "long_speaking_production",
                   "render": {"motion_step": 1, "native_scale": 1, "samples": 16}}
        timeline = {"total_frames": 7, "turns": [
            {"start_frame": 0, "panel_id": "01_opening", "camera": "wide"},
            {"start_frame": 5, "panel_id": "08_teil3_task", "camera": "candidates"},
        ], "silent_notices": [{"id": "note", "start_frame": 2, "end_frame": 5}]}
        with patch("long_speaking_preview.compile_script"), patch("long_speaking_preview.panels",
                return_value=[{"id": "01_opening", "camera": "wide"},
                              {"id": "08_teil3_task", "camera": "candidates"}]):
            plan = native_plan(episode, {}, timeline)
        self.assertEqual(8, len(plan))
        self.assertEqual({0, 1, 5, 6}, {item["frame"] for item in plan})
        self.assertEqual({(1216, 580), (836, 505)}, {tuple(item["size"]) for item in plan})
        self.assertEqual({"youtube": (1920, 1080), "social": (1080, 1920)}, output_sizes(episode))
        self.assertEqual("production_social.mp4", output_name(episode, "social"))

    def test_production_requires_production_profile_and_native_quality(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "episode.json"
            episode = {"template": "long_speaking_production", "source": {"duration_limit_seconds": 900},
                       "fps": 24, "intro_seconds": 0, "scene": {"entrance": False},
                       "render": {"motion_step": 3, "native_scale": .25, "samples": 2}}
            path.write_text(json.dumps(episode))
            with self.assertRaisesRegex(ValueError, "production template"):
                load_preview(path)
            with patch("long_speaking_production.resolve_production", return_value=episode), \
                    patch("long_speaking_preview.validate_episode"):
                with self.assertRaisesRegex(ValueError, "production quality"):
                    load_preview(path, "production")

    def test_silent_production_card_has_no_preview_brand_or_word_highlights(self):
        fixture = fixtures.LongSpeakingTests()
        fixture.setUp()
        try:
            notice = {"id": "silent_samir_notice", "text": production.NOTICE_TEXT,
                      "start_frame": 24, "end_frame": 168}
            timeline = {"silent_notices": [notice]}
            episode = {"template": "long_speaking_production"}
            for mode in ("youtube", "social"):
                image, check = overlay(episode, fixture.episode, timeline, mode, 24)
                self.assertEqual(output_sizes(episode)[mode], image.size)
                self.assertTrue(check["silent"])
                self.assertIsNone(check["spoken_text"])
                self.assertFalse(any("highlighted_word" in text for text in check["text"]))
                self.assertNotIn("VORSCHAU", " ".join(
                    line for text in check["text"] for line in text["lines"]))
        finally:
            fixture.doCleanups()

    def test_pipeline_routes_production_reuse_instead_of_synthesis(self):
        import pipeline
        import sys

        episode = {"template": "long_speaking_production", "id": "production",
                   "source": {"duration_limit_seconds": 900}}
        with patch("sys.argv", [
                "pipeline.py", "build", "--episode", "production.json", "--build", "production-run",
                "--profile", "production", "--reuse-audio", "approved-base",
                "--render-device", "HIP", "--jobs", "3",
                "--qwen-python", sys.executable]), \
                patch("pathlib.Path.read_text", return_value=json.dumps(episode)), \
                patch("long_speaking_preview.load_preview", return_value=(episode, {})), \
                patch("long_speaking_production.production_reuse_spec") as reuse, \
                patch("pipeline.check_render_device") as device, \
                patch("long_speaking_preview.build_preview") as build, \
                patch("pipeline.build_episode", side_effect=AssertionError("wrong template")):
            pipeline.main()
        reuse.assert_called_once_with(episode, Path("approved-base"))
        self.assertEqual("production", build.call_args.kwargs["profile"])
        self.assertEqual(Path("approved-base"), build.call_args.kwargs["reuse_audio"])
        self.assertEqual(3, build.call_args.args[2])
        self.assertEqual("HIP", build.call_args.kwargs["render_device"])
        device.assert_called_once_with("HIP")

    def test_pipeline_forwards_verified_scene_reuse_and_rejects_other_templates(self):
        import pipeline
        import sys

        episode = {"template": "long_speaking_production", "id": "shared",
                   "render": {"native_source": "youtube"}, "source": {"duration_limit_seconds": 900}}
        with patch("sys.argv", [
                "pipeline.py", "build", "--episode", "production.json", "--build", "new-run",
                "--profile", "production", "--reuse-audio", "approved-base",
                "--reuse-scene", "baked-source", "--qwen-python", sys.executable]), \
                patch("pathlib.Path.read_text", side_effect=lambda *a, **k: json.dumps(episode)), \
                patch("long_speaking_preview.load_preview", return_value=(episode, {})), \
                patch("long_speaking_production.production_reuse_spec", return_value={"audio": "verified"}), \
                patch("long_speaking_production.production_scene_reuse_spec") as reuse, \
                patch("long_speaking_preview.build_preview") as build:
            pipeline.main()
            reuse.assert_called_once_with(episode, {}, {"audio": "verified"}, Path("baked-source"))
            self.assertEqual(Path("baked-source"), build.call_args.kwargs["reuse_scene"])
            episode["template"] = "long_speaking_preview"
            with self.assertRaises(SystemExit) as error:
                pipeline.main()
            self.assertEqual(1, error.exception.code)


if __name__ == "__main__":
    unittest.main()
