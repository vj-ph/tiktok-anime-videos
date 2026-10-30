import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import cleanup_builds as cleanup


class CleanupBuildsTest(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / "builds"
        self.root.mkdir()
        self.run = self.root / "example"
        self.run.mkdir()

    def listening_delivery(self):
        audio = self.run / "audio"
        audio.mkdir()
        (audio / "speech.wav").write_bytes(b"speech")
        (self.run / "studio.blend").write_bytes(b"scene")
        (self.run / "listening_state.json").write_text('{"profile":"preview"}', encoding="utf-8")
        (self.run / "pilot.mp4").write_bytes(b"video")
        frames = self.run / "listener_frames"
        frames.mkdir()
        (frames / "listener_000.png").write_bytes(b"frame")
        receipt = {"listener_000.png": hashlib.sha256(b"frame").hexdigest()}
        (self.run / "listener_frames.json").write_text(json.dumps(receipt), encoding="utf-8")
        report = {"output_sha256": hashlib.sha256(b"video").hexdigest(), "listener_frames_sha256": receipt}
        (self.run / "delivery_checks.json").write_text(json.dumps(report), encoding="utf-8")
        return frames / "listener_000.png"

    def speaking_delivery(self):
        (self.run / "pipeline_state.json").write_text(
            json.dumps({"stages": {"frames": {}, "export": {}, "review": {}}}), encoding="utf-8")
        files = {}
        for name in ("pilot.mp4", "pilot_clean.mp4"):
            (self.run / name).write_bytes(name.encode())
            files[name] = {"sha256": hashlib.sha256(name.encode()).hexdigest(), "decoded": True}
        (self.run / "delivery_checks.json").write_text(json.dumps({"files": files}), encoding="utf-8")
        (self.run / "frames").mkdir()
        frame = self.run / "frames" / "frame_0001.png"
        frame.write_bytes(b"frame")
        return frame

    def test_inventory_and_dry_run_do_not_delete(self):
        frame = self.listening_delivery()
        results = cleanup.inventory(self.root)
        self.assertEqual(results[0][0], "example")
        self.assertEqual(results[0][2:], (5, 1))
        with contextlib.redirect_stdout(io.StringIO()):
            cleanup.clean_frames(self.run)
        self.assertTrue(frame.exists())

    def test_apply_removes_only_selected_frames(self):
        frame = self.listening_delivery()
        with patch.object(cleanup, "active_generators", return_value=[]), contextlib.redirect_stdout(io.StringIO()):
            cleanup.clean_frames(self.run, apply=True)
        self.assertFalse(frame.exists())
        for name in ("pilot.mp4", "studio.blend", "audio/speech.wav", "listener_frames.json", "delivery_checks.json"):
            self.assertTrue((self.run / name).is_file())

    def test_speaking_delivery_requires_verified_outputs_and_complete_stages(self):
        frame = self.speaking_delivery()
        with contextlib.redirect_stdout(io.StringIO()):
            cleanup.clean_frames(self.run)
        (self.run / "pilot_clean.mp4").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "differs"):
            cleanup.clean_frames(self.run, apply=True)
        self.assertTrue(frame.exists())
        (self.run / "pipeline_state.json").write_text('{"stages":{}}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "fully exported"):
            cleanup.clean_frames(self.run)

    def test_active_process_and_unexpected_frame_are_rejected(self):
        frame = self.listening_delivery()
        with patch.object(cleanup, "active_generators", return_value=["123 (blender)"]):
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(ValueError, "Active"):
                cleanup.clean_frames(self.run, apply=True)
        (frame.parent / "notes.txt").write_text("keep", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Unexpected item"):
            cleanup.clean_frames(self.run)
        self.assertTrue(frame.exists())

    def test_tampered_receipt_and_missing_frames_are_rejected(self):
        frame = self.listening_delivery()
        (self.run / "listener_frames.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "report"):
            cleanup.clean_frames(self.run)
        self.assertTrue(frame.exists())

    def test_select_requires_direct_name_and_refuses_symlink(self):
        for name in ("../example", "example/frames", "*", "..", ""):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "exactly one"):
                cleanup.selected_run(self.root, name)
        link = self.root / "link"
        try:
            link.symlink_to(self.run, target_is_directory=True)
        except OSError:
            self.skipTest("Creating symlinks requires privileges on this platform")
        with self.assertRaisesRegex(ValueError, "symbolic link"):
            cleanup.selected_run(self.root, "link")

    def test_multiple_hardlinks_are_rejected(self):
        frame = self.listening_delivery()
        try:
            os.link(frame, self.root / "other.png")
        except OSError:
            self.skipTest("Hard links are unavailable")
        with self.assertRaisesRegex(ValueError, "multiply linked"):
            cleanup.clean_frames(self.run)
        self.assertTrue(frame.exists())

    def test_apply_requires_matching_explicit_confirmation(self):
        frame = self.listening_delivery()
        with patch.object(cleanup, "BUILDS", self.root), contextlib.redirect_stderr(io.StringIO()):
            for args in (["--apply"], ["--run", "example", "--apply"],
                         ["--run", "example", "--apply", "--confirm", "other"]):
                with self.subTest(args=args), self.assertRaises(SystemExit):
                    cleanup.main(args)
        self.assertTrue(frame.exists())

    def test_explicit_cli_apply_removes_frames_only_for_the_named_run(self):
        frame = self.speaking_delivery()
        other = self.root / "other"
        other.mkdir()
        (other / "important.txt").write_text("keep", encoding="utf-8")
        with (patch.object(cleanup, "BUILDS", self.root),
              patch.object(cleanup, "active_generators", return_value=[]),
              contextlib.redirect_stdout(io.StringIO())):
            cleanup.main(["--run", "example", "--apply", "--confirm", "example"])
        self.assertFalse(frame.exists())
        self.assertTrue((self.run / "pilot.mp4").exists())
        self.assertEqual((other / "important.txt").read_text(encoding="utf-8"), "keep")

    def test_bulk_dry_run_reports_eligible_and_skipped_without_deletion(self):
        frame = self.listening_delivery()
        incomplete = self.root / "incomplete"
        (incomplete / "frames").mkdir(parents=True)
        unfinished = incomplete / "frames" / "frame_0001.png"
        unfinished.write_bytes(b"unfinished")
        output = io.StringIO()
        with patch.object(cleanup, "BUILDS", self.root), contextlib.redirect_stdout(output):
            cleanup.main(["--all"])
        self.assertIn("Eligible: example", output.getvalue())
        self.assertIn("Skipped: incomplete", output.getvalue())
        self.assertIn("--all --apply --confirm ", output.getvalue())
        self.assertTrue(frame.exists())
        self.assertTrue(unfinished.exists())

    def test_bulk_apply_only_removes_frames_from_reviewed_plan(self):
        first_frame = self.listening_delivery()
        first = self.run
        self.run = self.root / "second"
        self.run.mkdir()
        second_frame = self.speaking_delivery()
        incomplete = self.root / "incomplete"
        (incomplete / "frames").mkdir(parents=True)
        unfinished = incomplete / "frames" / "frame_0001.png"
        unfinished.write_bytes(b"unfinished")
        plans, skipped = cleanup.bulk_plan(self.root)
        token = cleanup.plan_token(self.root, plans, skipped)
        with (patch.object(cleanup, "BUILDS", self.root),
              patch.object(cleanup, "active_generators", return_value=[]),
              contextlib.redirect_stdout(io.StringIO())):
            cleanup.main(["--all", "--apply", "--confirm", token])
        self.assertFalse(first_frame.exists())
        self.assertFalse(second_frame.exists())
        self.assertTrue(unfinished.exists())
        for path in (first / "pilot.mp4", first / "studio.blend", first / "audio" / "speech.wav",
                     first / "listener_frames.json", self.run / "pilot.mp4",
                     self.run / "pilot_clean.mp4", self.run / "delivery_checks.json"):
            self.assertTrue(path.is_file(), str(path))

    def test_bulk_rejects_stale_confirmation_and_active_generation(self):
        frame = self.listening_delivery()
        plans, skipped = cleanup.bulk_plan(self.root)
        token = cleanup.plan_token(self.root, plans, skipped)
        frame.write_bytes(b"changed frame")
        with (patch.object(cleanup, "BUILDS", self.root), contextlib.redirect_stdout(io.StringIO()),
              contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as result):
            cleanup.main(["--all", "--apply", "--confirm", token])
        self.assertNotEqual(result.exception.code, 0)
        self.assertTrue(frame.exists())
        plans, skipped = cleanup.bulk_plan(self.root)
        token = cleanup.plan_token(self.root, plans, skipped)
        with (patch.object(cleanup, "BUILDS", self.root),
              patch.object(cleanup, "active_generators", return_value=["123 (blender)"]),
              contextlib.redirect_stdout(io.StringIO()),
              contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit)):
            cleanup.main(["--all", "--apply", "--confirm", token])
        self.assertTrue(frame.exists())

    def test_bulk_rechecks_the_plan_after_process_check(self):
        frame = self.listening_delivery()
        plans, skipped = cleanup.bulk_plan(self.root)
        token = cleanup.plan_token(self.root, plans, skipped)

        def change_during_check():
            frame.write_bytes(b"changed while checking")
            return []

        with (patch.object(cleanup, "active_generators", side_effect=change_during_check),
              contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(ValueError, "changed")):
            cleanup.clean_all(self.root, apply=True, confirm=token)
        self.assertTrue(frame.exists())

    def test_bulk_confirmation_changes_when_delivery_metadata_changes(self):
        frame = self.listening_delivery()
        plans, skipped = cleanup.bulk_plan(self.root)
        token = cleanup.plan_token(self.root, plans, skipped)
        state = self.run / "listening_state.json"
        state.write_text('{"profile":"preview","changed":true}', encoding="utf-8")
        with (contextlib.redirect_stdout(io.StringIO()),
              self.assertRaisesRegex(ValueError, "Confirmation token")):
            cleanup.clean_all(self.root, apply=True, confirm=token)
        self.assertTrue(frame.exists())

    def test_bulk_requires_confirmation_and_cannot_combine_with_run(self):
        frame = self.listening_delivery()
        with patch.object(cleanup, "BUILDS", self.root), contextlib.redirect_stderr(io.StringIO()):
            for args in (["--all", "--apply"], ["--all", "--run", "example"],
                         ["--all", "--confirm", "anything"]):
                with self.subTest(args=args), self.assertRaises(SystemExit):
                    cleanup.main(args)
        self.assertTrue(frame.exists())


if __name__ == "__main__":
    unittest.main()
