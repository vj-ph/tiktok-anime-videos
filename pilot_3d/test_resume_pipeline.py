import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import resume_pipeline as recovery
from prepare_audio import atomic_json, sha256_file


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.build = self.root / "build"
        self.build.mkdir()
        (self.root / "render.py").write_text("explicit source fixture", encoding="utf-8")
        (self.build / "studio.blend").write_bytes(b"explicit non-Blender fixture")
        (self.build / "episode.json").write_text("{}", encoding="utf-8")
        (self.build / "frames").mkdir()
        self.frame = self.build / "frames" / "frame_0001.png"
        self.frame.write_bytes(b"explicit saved-frame preservation fixture")
        manifest = {"width": 720, "height": 1280, "samples": 16, "motion_step": 1}
        atomic_json(self.build / "scene_manifest.json", manifest)
        atomic_json(self.build / "render_checkpoint.json", {
            "scene": manifest, "blend_sha256": sha256_file(self.build / "studio.blend"),
            "render_device": "HIP",
        })
        self.spec = {"profile": "production", "render_device": "HIP", "speech_device": "cpu",
                     "code_sha256": {"render.py": sha256_file(self.root / "render.py")}}
        stages = {}
        for stage in ("audio", "alignment", "scene", "scene_checks"):
            path = self.build / f"{stage}.fixture"
            path.write_bytes(b"explicit checkpoint output fixture")
            stages[stage] = {"outputs": {path.name: sha256_file(path)}}
        self.state = {"spec": self.spec, "stages": stages}
        self.write_state()
        self.log = self.build / "pipeline_frames.log"
        self.log.write_text("original failed-run evidence", encoding="utf-8")
        self.original = {str(path.relative_to(self.build)): path.read_bytes()
                         for path in self.build.rglob("*") if path.is_file() and path != self.log}
        patches = [patch.object(recovery, "ROOT", self.root),
                   patch.object(recovery, "SOURCES", ("render.py",)),
                   patch.object(recovery, "qwen_python", return_value=Path(sys.executable)),
                   patch.object(recovery, "GenerationRun"),
                   patch("builtins.print")]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    def write_state(self):
        atomic_json(self.build / "pipeline_state.json", self.state)

    def crash(self, command, log):
        text = self.log.read_text(encoding="utf-8")
        self.log.write_text(text + "\nEXCEPTION_ACCESS_VIOLATION\nModule: amdhip64_6.dll",
                            encoding="utf-8")
        return 1, f"Error: Stage failed (1); see {self.log}\n"

    def test_recognized_crashes_reduce_workers_and_preserve_frames_and_frozen_state(self):
        count = 0

        def attempt(command, log):
            nonlocal count
            count += 1
            return self.crash(command, log) if count < 3 else (0, "Ready")

        with patch.object(recovery, "run_attempt", side_effect=attempt) as run, \
                patch.object(recovery.time, "sleep") as sleep:
            self.assertEqual(recovery.resume(self.build, jobs=4), self.build)
        self.assertEqual([call.args[0][call.args[0].index("--jobs") + 1]
                          for call in run.call_args_list], ["4", "2", "1"])
        self.assertEqual(sleep.call_count, 2)
        for name, original in self.original.items():
            self.assertEqual((self.build / name).read_bytes(), original)
        report = json.loads(next((self.build / "recovery").glob("*/recovery.json")).read_text())
        self.assertTrue(report["complete"])
        first = next((self.build / "recovery").glob("*/attempt_1/before/pipeline_frames.log"))
        self.assertEqual(first.read_text(), "original failed-run evidence")
        for call in run.call_args_list:
            command = call.args[0]
            self.assertEqual(command[command.index("--profile") + 1], "production")
            self.assertEqual(command[command.index("--render-device") + 1], "HIP")

    def test_default_starts_at_two_and_stops_after_bounded_recognized_failures(self):
        with patch.object(recovery, "run_attempt", side_effect=self.crash) as run, \
                patch.object(recovery.time, "sleep"):
            with self.assertRaisesRegex(RuntimeError, "No further automatic retry"):
                recovery.resume(self.build)
        self.assertEqual([call.args[0][call.args[0].index("--jobs") + 1]
                          for call in run.call_args_list], ["2", "1", "1"])

    def test_nonhip_stale_log_and_cancellation_failures_are_not_retried(self):
        for code, tail, log in (
                (1, "Error: audio failed", "EXCEPTION_ACCESS_VIOLATION amdhip64_6.dll"),
                (1, f"Error: Stage failed (1); see {self.log}", "No space left on device"),
                (130, f"Error: Stage failed (1); see {self.log}", "amdhip64_6.dll EXCEPTION_ACCESS_VIOLATION"),
                (1, f"Error: Stage failed (1); see {self.log}", None)):
            def failure(command, output):
                if log is not None:
                    self.log.write_text(log, encoding="utf-8")
                return code, tail

            with self.subTest(code=code, log=log), \
                    patch.object(recovery, "run_attempt", side_effect=failure) as run, \
                    patch.object(recovery.time, "sleep") as sleep:
                with self.assertRaises(RuntimeError):
                    recovery.resume(self.build)
                run.assert_called_once()
                sleep.assert_not_called()

    def test_kernel_assertion_is_recognized_only_during_the_frames_stage(self):
        self.log.write_text("Unhandled kernel integrator_init_from_camera used for path iteration",
                            encoding="utf-8")
        self.assertTrue(recovery.recognized_hip_crash(
            f"Error: Stage failed (1); see {self.log}", self.build))
        self.assertFalse(recovery.recognized_hip_crash("speech error", self.build))

    def test_changed_code_incomplete_stages_and_mismatched_backend_are_rejected_before_launch(self):
        mutations = [
            lambda: self.spec["code_sha256"].update({"render.py": "changed"}),
            lambda: self.state["stages"].pop("alignment"),
            lambda: self.spec.update(render_device="CPU"),
        ]
        for mutate in mutations:
            original = json.loads(json.dumps(self.state))
            mutate()
            self.write_state()
            with patch.object(recovery, "run_attempt") as run:
                with self.assertRaises(ValueError):
                    recovery.resume(self.build)
                run.assert_not_called()
            self.state = original
            self.spec = self.state["spec"]
            self.write_state()
        (self.build / "studio.blend").write_bytes(b"changed scene")
        with self.assertRaisesRegex(ValueError, "Frame checkpoint"):
            recovery.verified_build(self.build)

    def test_exact_audio_reuse_source_is_forwarded(self):
        self.spec["reuse_audio"] = {"source": "explicit-previous-delivery"}
        self.write_state()
        with patch.object(recovery, "run_attempt", return_value=(0, "")) as run:
            recovery.resume(self.build)
        command = run.call_args.args[0]
        self.assertEqual(command[command.index("--reuse-audio") + 1], "explicit-previous-delivery")

    def test_attempt_tees_output_and_cleans_up_its_owned_process_on_cancellation(self):
        process = MagicMock()
        process.stdout = io.StringIO("frames: running\nReady\n")
        process.wait.return_value = 0
        with patch.object(recovery, "start_process", return_value=process), \
                patch.object(recovery, "forget_process") as forget:
            code, tail = recovery.run_attempt(["explicit-mocked-command"], self.root / "attempt.log")
        self.assertEqual((code, tail), (0, "frames: running\nReady\n"))
        self.assertEqual((self.root / "attempt.log").read_text(), tail)
        forget.assert_called_once_with(process)
        process.wait.side_effect = KeyboardInterrupt
        process.stdout = io.StringIO("")
        with patch.object(recovery, "start_process", return_value=process), \
                patch.object(recovery, "stop_processes") as stop, \
                patch.object(recovery, "forget_process"):
            with self.assertRaises(KeyboardInterrupt):
                recovery.run_attempt(["explicit-mocked-command"], self.root / "cancel.log")
        stop.assert_called_once_with([process])

    def test_invalid_retry_configuration_never_starts_a_process(self):
        for options in ({"jobs": 3}, {"max_retries": -1}, {"max_retries": 4},
                        {"retry_delay": -1}, {"retry_delay": float("nan")}):
            with self.subTest(options=options), patch.object(recovery, "run_attempt") as run:
                with self.assertRaises(ValueError):
                    recovery.resume(self.build, **options)
                run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
