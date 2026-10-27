import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from build_paths import build_directory, resolve_build_reference
from episode_config import read_episode


class BuildPathTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / "project"
        self.root.mkdir()
        self.builds = self.root / "builds"
        for name, value in (("ROOT", self.root), ("BUILDS", self.builds)):
            replacement = patch("build_paths." + name, value)
            replacement.start()
            self.addCleanup(replacement.stop)

    def test_project_level_names_and_legacy_names_use_the_builds_directory(self):
        for supplied, name in (("new_preview", "new_preview"), ("build", "pilot_v1"),
                               ("build_v2", "v2"), ("build_lerntreffen_preview", "lerntreffen_preview")):
            with self.subTest(supplied=supplied):
                self.assertEqual(build_directory(self.root / supplied), self.builds / name)

    def test_explicit_nested_and_external_directories_remain_explicit(self):
        for path in (self.builds / "lerntreffen/preview", self.root / "custom/output",
                     self.root.parent / "external"):
            with self.subTest(path=path):
                self.assertEqual(build_directory(path), path)

    def test_container_and_ancestor_directories_cannot_be_used_as_a_run(self):
        for path in (self.root, self.builds, self.root.parent,
                     self.root / "build_.", self.root / "build_.."):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "dedicated output"):
                build_directory(path)

    def test_old_absolute_references_find_relocated_files_without_changing_them(self):
        for old, name in (("build", "pilot_v1"), ("build_v2", "v2")):
            with self.subTest(old=old):
                moved = self.builds / name / "audio/01.wav"
                moved.parent.mkdir(parents=True)
                moved.write_bytes(b"unchanged frozen audio")
                self.assertEqual(resolve_build_reference(self.root / old / "audio/01.wav"), moved)
                self.assertEqual(resolve_build_reference(moved), moved)
                self.assertEqual(moved.read_bytes(), b"unchanged frozen audio")
                self.assertFalse((self.root / old).exists())

    def test_existing_legacy_paths_take_precedence_and_missing_paths_still_fail(self):
        original = self.root / "build_v2"
        original.mkdir()
        (self.builds / "v2").mkdir(parents=True)
        self.assertEqual(resolve_build_reference(original), original)
        missing = self.root / "build_v2/missing.wav"
        self.assertEqual(resolve_build_reference(missing), missing)
        with self.assertRaises(FileNotFoundError):
            resolve_build_reference(missing).read_bytes()

    def test_external_build_names_are_not_remapped(self):
        external = self.root.parent / "outside/build_v2/audio.wav"
        self.assertEqual(resolve_build_reference(external), external)

    @unittest.skipUnless(os.name == "nt", "Windows short-path aliases")
    def test_windows_short_path_aliases_use_canonical_project_and_reject_containers(self):
        import ctypes

        get_short_path = ctypes.windll.kernel32.GetShortPathNameW
        get_short_path.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint]
        get_short_path.restype = ctypes.c_uint
        buffer = ctypes.create_unicode_buffer(32768)
        length = get_short_path(str(self.root), buffer, len(buffer))
        if not length:
            raise ctypes.WinError()
        if length >= len(buffer):
            self.fail("Short path exceeds buffer")
        alias = Path(buffer.value)
        if alias == self.root:
            self.skipTest("Short path aliases are not enabled for this fixture")
        self.assertEqual(alias.resolve(), self.root)
        self.assertEqual(build_directory(alias / "new_preview"), self.builds / "new_preview")
        with self.assertRaisesRegex(ValueError, "dedicated output"):
            build_directory(alias)
        moved = self.builds / "v2" / "audio.wav"
        moved.parent.mkdir(parents=True)
        moved.write_bytes(b"fixture")
        self.assertEqual(resolve_build_reference(alias / "build_v2" / "audio.wav"), moved)

    def test_frozen_episode_can_be_opened_by_its_old_path_without_rewriting_asset_values(self):
        moved = self.builds / "v2/episode.json"
        moved.parent.mkdir(parents=True)
        data = {"schema_version": 1, "voices": {},
                "scene": {"base_scene": str(self.root / "build_v2/studio.blend")}}
        text = json.dumps(data)
        moved.write_text(text)
        self.assertEqual(read_episode(self.root / "build_v2/episode.json"), data)
        self.assertEqual(moved.read_text(), text)


if __name__ == "__main__":
    unittest.main()
