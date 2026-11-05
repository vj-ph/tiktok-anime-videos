import copy
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image

from prepare_audio import atomic_json, sha256_file
import recover_long_speaking as recovery

ENSURE_STOPPED = recovery.ensure_stopped


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.build = self.root / "builds" / "production"
        self.build.mkdir(parents=True)
        (self.root / "episodes").mkdir()
        (self.root / "scene.py").write_text("# frozen scene")
        shutil.copy2(recovery.__file__, self.root / Path(recovery.__file__).name)
        self.episode = {
            "id": "test", "template": "long_speaking_production", "render_device": "CPU",
            "render": {"motion_step": 2, "native_scale": 1.0, "samples": 8, "native_source": "youtube"},
        }
        self.episode_path = self.root / "episodes" / "test.json"
        atomic_json(self.episode_path, self.episode)
        self.storyboard = {"title": "test"}
        self.plan = [
            {"format": "youtube", "frame": frame, "camera": "wide", "size": [12, 8],
             "file": f"native/youtube_{frame:05d}.png"} for frame in (0, 2, 4, 6)]
        atomic_json(self.build / "episode.json", self.episode)
        atomic_json(self.build / "storyboard_episode.json", self.storyboard)
        atomic_json(self.build / "native_plan.json", self.plan)
        atomic_json(self.build / "timeline.json", {"fps": 24, "total_frames": 8})
        for name in ("dialogue.wav", "word_alignment.json", "audio_reuse.json", "speech_asr_check.json",
                     "auditory_review_flags.json", "subtitles.srt", "preview.blend", "scene_checks.json"):
            (self.build / name).write_bytes(b"frozen unit fixture")
        snapshot = self.build / "source_export"
        snapshot.mkdir()
        shutil.copy2(self.root / "scene.py", snapshot / "scene.py")
        self.state = {
            "spec": {"episode": self.episode,
                     "code_sha256": {"scene.py": sha256_file(self.root / "scene.py")},
                     "asset_sha256": {str(self.episode_path): sha256_file(self.episode_path)},
                     "audio_reuse": {"source": "approved"}},
            "stages": {
                "audio_reuse": {name: sha256_file(self.build / name) for name in (
                    "dialogue.wav", "timeline.json", "word_alignment.json", "audio_reuse.json",
                    "speech_asr_check.json", "auditory_review_flags.json", "subtitles.srt")},
                "scene": {name: sha256_file(self.build / name)
                          for name in ("preview.blend", "scene_checks.json")},
            },
        }
        atomic_json(self.build / "production_state.json", self.state)
        for item in self.plan[:2]:
            self.write_png(item)
        self.log = self.build / "frames_0.log"
        self.log.write_text("\n".join(f"Saved: '{self.build / item['file']}'"
                                      for item in self.plan[:2]), encoding="utf-8")
        self.heads = [{"in_front": True, "bounds": [.2, .2, .8, .8]}]
        for context in (
                patch.object(recovery, "ROOT", self.root),
                patch("long_speaking_preview.SOURCES", ("scene.py",)),
                patch("long_speaking_preview.load_preview", return_value=(copy.deepcopy(self.episode), self.storyboard)),
                patch("long_speaking_preview.native_plan", return_value=self.plan),
                patch.object(recovery, "ensure_stopped")):
            context.start()
            self.addCleanup(context.stop)

    def write_png(self, item):
        path = self.build / item["file"]
        path.parent.mkdir(exist_ok=True)
        Image.new("RGB", tuple(item["size"]), "green").save(path)

    def journal(self, item, origin="existing"):
        path = recovery.receipt_path(self.build, item)
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_json(path, {**item, "head_bounds": self.heads,
                           "sha256": sha256_file(self.build / item["file"]),
                           "recovery_origin": origin})

    def mocked_worker(self, command, **kwargs):
        index = int(command[command.index("--worker") + 1])
        jobs = int(command[command.index("--jobs") + 1])
        import math
        count = math.ceil(len(self.plan) / jobs)
        for item in self.plan[index * count:(index + 1) * count]:
            path = self.build / item["file"]
            if not path.exists():
                self.write_png(item)
            self.journal(item)
        return SimpleNamespace(returncode=0)

    def test_audit_is_read_only_and_identifies_only_missing_frames(self):
        before = {p: sha256_file(p) for p in self.build.rglob("*") if p.is_file()}
        state, plan, _, _, manifest, found, _ = recovery.audit(self.build)
        self.assertEqual(self.state, state)
        self.assertEqual(self.plan, plan)
        self.assertIsNone(manifest)
        self.assertEqual({p["file"] for p in self.plan[:2]}, set(found))
        self.assertEqual(before, {p: sha256_file(p) for p in before})
        self.assertFalse((self.build / recovery.RECOVERY).exists())

    def test_png_corruption_wrong_dimensions_and_missing_save_evidence_are_rejected(self):
        first = self.build / self.plan[0]["file"]
        first.write_bytes(b"truncated png")
        with self.assertRaisesRegex(ValueError, "Invalid saved PNG"):
            recovery.audit(self.build)
        Image.new("RGB", (10, 10)).save(first)
        with self.assertRaisesRegex(ValueError, "Invalid saved PNG"):
            recovery.audit(self.build)
        self.write_png(self.plan[0])
        self.log.write_text("")
        with self.assertRaisesRegex(ValueError, "completed-save evidence"):
            recovery.audit(self.build)

    def test_original_code_assets_and_checkpoint_hash_guards_remain_strict(self):
        for path in (self.root / "scene.py", self.build / "source_export" / "scene.py",
                     self.episode_path, self.build / "preview.blend", self.build / "timeline.json"):
            original = path.read_bytes()
            path.write_bytes(b"changed")
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "changed"):
                recovery.audit(self.build)
            path.write_bytes(original)

    def test_changed_derived_plan_or_episode_is_rejected(self):
        atomic_json(self.build / "native_plan.json", self.plan[:-1])
        with self.assertRaisesRegex(ValueError, "Native plan differs"):
            recovery.audit(self.build)
        atomic_json(self.build / "native_plan.json", self.plan)
        atomic_json(self.build / "episode.json", {**self.episode, "id": "different"})
        with self.assertRaisesRegex(ValueError, "episode differs"):
            recovery.audit(self.build)

    def test_receipt_must_match_image_plan_and_head_clearance(self):
        self.journal(self.plan[0])
        path = recovery.receipt_path(self.build, self.plan[0])
        receipt = recovery.read(path)
        for changes in ({"sha256": "wrong"}, {"frame": 7}, {"head_bounds": []},
                        {"head_bounds": [{"in_front": False, "bounds": [.2, .2, .8, .8]}]}):
            atomic_json(path, {**receipt, **changes})
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, "receipt differs"):
                recovery.audit(self.build)

    def test_execution_preserves_pngs_spec_sources_and_commits_complete_receipts(self):
        before = {p["file"]: sha256_file(self.build / p["file"]) for p in self.plan[:2]}
        snapshot = sha256_file(self.build / "source_export" / "scene.py")
        with patch("generation_runtime.run_process", side_effect=self.mocked_worker) as run, \
                patch.object(recovery, "export") as export:
            recovery.execute(self.build, 2, "export")
        self.assertEqual(2, run.call_count)
        export.assert_called_once()
        state = recovery.read(self.build / "production_state.json")
        self.assertEqual(self.state["spec"], state["spec"])
        self.assertEqual(self.state["stages"]["scene"], state["stages"]["scene"])
        self.assertEqual(5, len(state["stages"]["frames"]))
        self.assertEqual(snapshot, sha256_file(self.build / "source_export" / "scene.py"))
        self.assertEqual(before, {name: sha256_file(self.build / name) for name in before})
        self.assertEqual(4, len(recovery.read(self.build / "native_checks.json")))
        with patch("generation_runtime.run_process", side_effect=AssertionError("Already complete")), \
                patch.object(recovery, "export"):
            recovery.execute(self.build, 1, "frames")

    def test_interruption_preserves_journals_and_subsequent_run_finishes(self):
        def partial(command, **kwargs):
            index = int(command[command.index("--worker") + 1])
            if index == 0:
                for item in self.plan[:2]:
                    self.journal(item)
            return SimpleNamespace(returncode=1)

        with patch("generation_runtime.run_process", side_effect=partial), \
                patch("generation_runtime.cancel_processes"):
            with self.assertRaisesRegex(RuntimeError, "worker"):
                recovery.execute(self.build, 2, "frames")
        self.assertNotIn("frames", recovery.read(self.build / "production_state.json")["stages"])
        self.assertTrue(recovery.receipt_path(self.build, self.plan[0]).exists())
        with patch("generation_runtime.run_process", side_effect=self.mocked_worker):
            recovery.execute(self.build, 2, "frames")
        self.assertIn("frames", recovery.read(self.build / "production_state.json")["stages"])

    def test_existing_png_tampering_is_rejected_on_recovery_resume(self):
        with patch("generation_runtime.run_process", side_effect=self.mocked_worker):
            recovery.execute(self.build, 2, "frames")
        Image.new("RGB", (12, 8), "blue").save(self.build / self.plan[0]["file"])
        with self.assertRaisesRegex(ValueError, "receipt differs|verified PNG changed"):
            recovery.audit(self.build)

    def test_new_image_without_journal_can_be_recovered_from_completed_save_log(self):
        self.write_png(self.plan[2])
        attempt = self.build / recovery.RECOVERY / "attempt_fixture"
        attempt.mkdir(parents=True)
        (attempt / "worker_1.log").write_text(
            f"Saved: '{self.build / self.plan[2]['file']}'", encoding="utf-8")
        result = recovery.audit(self.build)
        self.assertEqual(3, len(result[5]))

    def test_commit_refuses_concurrent_state_change(self):
        for item in self.plan:
            if not (self.build / item["file"]).exists():
                self.write_png(item)
            self.journal(item)
        atomic_json(self.build / "production_state.json", {**self.state, "unexpected": True})
        with self.assertRaisesRegex(ValueError, "state changed"):
            recovery.commit_frames(self.build, self.state, self.plan)

    def test_recovery_rejects_modified_original_logs_or_runner_provenance(self):
        with patch("generation_runtime.run_process", side_effect=self.mocked_worker):
            recovery.execute(self.build, 2, "frames")
        original_log = self.log.read_bytes()
        self.log.write_text("changed original log")
        with self.assertRaisesRegex(ValueError, "input/checkpoint changed"):
            recovery.audit(self.build)
        self.log.write_bytes(original_log)
        snapshot = self.build / recovery.RECOVERY / "runner.py"
        snapshot.write_text("# changed recovery snapshot")
        with self.assertRaisesRegex(ValueError, "input/checkpoint changed"):
            recovery.audit(self.build)

    def test_exclusive_recovery_lock_releases_after_failure(self):
        with recovery.recovery_lock(self.build):
            with self.assertRaisesRegex(ValueError, "holds this build"):
                with recovery.recovery_lock(self.build):
                    self.fail("Concurrent recovery acquired the lock")
        with recovery.recovery_lock(self.build):
            pass

    def test_export_uses_original_builder_without_changing_content_or_device(self):
        with patch("long_speaking_preview.build_preview") as builder:
            recovery.export(self.build, self.state, self.episode_path, 2)
        builder.assert_called_once_with(
            self.episode_path, self.build, jobs=2, profile="production", reuse_audio="approved",
            reuse_scene=None, render_device="CPU")

    def test_active_build_is_rejected_without_touching_other_processes(self):
        own = SimpleNamespace(pid=100, parents=lambda: [])
        active = SimpleNamespace(pid=200, cwd=lambda: str(self.root), info={
            "cmdline": ["python", "pipeline.py", "--build", str(self.build.relative_to(self.root))]})
        with patch("psutil.Process", return_value=own), \
                patch("psutil.process_iter", return_value=[active]):
            with self.assertRaisesRegex(ValueError, "still in use"):
                ENSURE_STOPPED(self.build)
            active.info["cmdline"][-1] = "builds/unrelated"
            ENSURE_STOPPED(self.build)

    def test_native_worker_only_renders_missing_frames_and_skips_valid_journals(self):
        folder = self.build / recovery.RECOVERY
        attempt = folder / "attempt_native"
        attempt.mkdir(parents=True)
        (folder / "receipts").mkdir()
        atomic_json(attempt / "inventory.json", {
            p["file"]: sha256_file(self.build / p["file"]) for p in self.plan[:2]})
        atomic_json(folder / "manifest.json", {
            "spec": self.state["spec"], "protected_sha256": {},
            "runner_sha256": sha256_file(Path(recovery.__file__)),
        })
        self.journal(self.plan[0])
        settings = SimpleNamespace(engine="CYCLES", fps=24, resolution_percentage=100,
                                   image_settings=SimpleNamespace(file_format="PNG"), use_sequencer=False)
        scene = SimpleNamespace(
            render=settings, cycles=SimpleNamespace(samples=16, device="CPU"),
            frame_start=1, frame_end=8, frame_set=lambda frame: None,
            objects={"Preview youtube wide": "camera"})
        rendered = []

        def render(**kwargs):
            rendered.append(scene.render.filepath)
            Image.new("RGB", (scene.render.resolution_x, scene.render.resolution_y)).save(scene.render.filepath)

        bpy = SimpleNamespace(
            context=SimpleNamespace(scene=scene, view_layer=SimpleNamespace(update=lambda: None),
                                    preferences=SimpleNamespace(addons={
                                        "cycles": SimpleNamespace(preferences=SimpleNamespace(compute_device_type="NONE"))})),
            ops=SimpleNamespace(render=SimpleNamespace(render=render)))
        helpers = SimpleNamespace(actors_from_scene=lambda: {"wide": "actor"},
                                  head_bounds=lambda *args: self.heads, roles=lambda camera: ["wide"])
        with patch.dict("sys.modules", {"bpy": bpy, "long_speaking_preview_scene": helpers}), \
                patch("runtime_config.configure_cycles"):
            recovery.native_worker(self.build, attempt, 0, 1)
            self.assertEqual(2, len(rendered))
            self.assertEqual(8, scene.cycles.samples)
            recovery.native_worker(self.build, attempt, 0, 1)
            self.assertEqual(2, len(rendered))
        self.assertEqual("existing", recovery.read(recovery.receipt_path(self.build, self.plan[1]))["recovery_origin"])
        self.assertEqual("rendered", recovery.read(recovery.receipt_path(self.build, self.plan[2]))["recovery_origin"])


if __name__ == "__main__":
    unittest.main()
