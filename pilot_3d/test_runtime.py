"""Portable tests; no production scene, reference voices or ML downloads required."""

import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import zipfile

import runtime_config as runtime
import setup_runtime as setup


class RuntimeTests(unittest.TestCase):
    def test_platform_tools_and_legacy_linux_layout(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for platform, directory, executable in (("win32", "windows", "blender.exe"),
                                                     ("linux", "linux", "blender")):
                path = root / ".tools" / directory / "blender" / executable
                path.parent.mkdir(parents=True)
                path.touch()
                with patch.object(runtime, "ROOT", root), patch.object(sys, "platform", platform):
                    self.assertEqual(runtime.tool_path("blender"), path)
            legacy = root / ".tools" / "rhubarb" / "rhubarb"
            legacy.parent.mkdir(parents=True)
            legacy.touch()
            with patch.object(runtime, "ROOT", root), patch.object(sys, "platform", "linux"):
                self.assertEqual(runtime.tool_path("rhubarb"), legacy)

    def test_explicit_tool_override_takes_priority(self):
        with patch.dict(os.environ, {"BLENDER_EXE": sys.executable}):
            self.assertEqual(runtime.tool_path("blender"), Path(sys.executable).resolve())

    def test_portable_tools_take_priority_without_searching_path(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {}, clear=True):
            root = Path(folder)
            portable = root / ".tools" / "linux" / "blender" / "blender"
            legacy = root / ".tools" / "blender" / "blender"
            for path in (portable, legacy):
                path.parent.mkdir(parents=True)
                path.touch()
            with patch.object(runtime, "ROOT", root), patch.object(sys, "platform", "linux"):
                with patch("runtime_config.shutil.which", side_effect=AssertionError("unexpected PATH lookup")):
                    self.assertEqual(runtime.tool_path("blender"), portable)
                    portable.unlink()
                    self.assertEqual(runtime.tool_path("blender"), legacy)

    def test_path_tools_are_supported(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(runtime, "ROOT", Path(folder)):
            with patch("runtime_config.shutil.which", return_value=sys.executable):
                self.assertEqual(runtime.tool_path("rhubarb"), Path(sys.executable))

    def test_missing_tool_returns_expected_portable_path(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {}, clear=True):
            root = Path(folder)
            with patch.object(runtime, "ROOT", root), patch.object(sys, "platform", "linux"):
                with patch("runtime_config.shutil.which", return_value=None) as which:
                    self.assertEqual(runtime.tool_path("blender"), root / ".tools" / "linux" / "blender" / "blender")
                    which.assert_called_once_with("blender")

    def test_qwen_interpreter_override_and_local_environment(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            local = root / ".venv" / "Scripts" / "python.exe"
            local.parent.mkdir(parents=True)
            local.touch()
            with patch.dict(os.environ, {}, clear=True), patch.object(runtime, "ROOT", root):
                with patch.object(sys, "platform", "win32"):
                    self.assertEqual(runtime.qwen_python(), local)
                with patch.dict(os.environ, {"QWEN_PYTHON": sys.executable}):
                    self.assertEqual(runtime.qwen_python(), Path(sys.executable))

    def test_fonts_are_staged_for_ffmpeg_without_absolute_filter_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            fonts = root / "fonts with spaces"
            fonts.mkdir()
            build = root / "vidéo"
            build.mkdir()
            for name in ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf"):
                (fonts / name).write_bytes(b"explicit font fixture")
            with patch.dict(os.environ, {"DEJAVU_FONT_DIR": str(fonts)}):
                runtime.caption_fonts(build)
                self.assertEqual(runtime.font_path(True), fonts / "DejaVuSans-Bold.ttf")
                for source in fonts.iterdir():
                    self.assertEqual((build / "caption_fonts" / source.name).read_bytes(), source.read_bytes())

    def test_missing_fonts_fail_without_substituting_another_typeface(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(os.environ, {"DEJAVU_FONT_DIR": folder}):
                with self.assertRaisesRegex(FileNotFoundError, "setup_runtime.py"):
                    runtime.caption_fonts(Path(folder))

    def fake_bpy(self, devices):
        preferences = SimpleNamespace(devices=devices, refresh_devices=Mock())
        return SimpleNamespace(
            context=SimpleNamespace(
                scene=SimpleNamespace(render=SimpleNamespace(engine="CYCLES"),
                                      cycles=SimpleNamespace(device="CPU")),
                preferences=SimpleNamespace(addons={"cycles": SimpleNamespace(preferences=preferences)})))

    def test_gpu_selection_enables_only_requested_backend(self):
        for backend in runtime.RENDER_DEVICES[1:]:
            devices = [SimpleNamespace(name="processor", type="CPU", use=True),
                       SimpleNamespace(name="selected GPU", type=backend, use=False),
                       SimpleNamespace(name="other GPU", type="OTHER", use=True)]
            bpy = self.fake_bpy(devices)
            runtime.configure_cycles(bpy, backend)
            self.assertEqual([d.use for d in devices], [False, True, False])
            self.assertEqual(bpy.context.scene.cycles.device, "GPU")
            self.assertEqual(bpy.context.preferences.addons["cycles"].preferences.compute_device_type, backend)

    def test_unavailable_gpu_never_silently_falls_back_to_cpu(self):
        bpy = self.fake_bpy([SimpleNamespace(name="CPU", type="CPU", use=True)])
        with self.assertRaisesRegex(RuntimeError, "No HIP GPU"):
            runtime.configure_cycles(bpy, "HIP")
        bpy.context.scene.render.engine = "BLENDER_WORKBENCH"
        with self.assertRaisesRegex(ValueError, "Cycles"):
            runtime.configure_cycles(bpy, "HIP")

    def test_cpu_is_explicit_even_when_saved_scene_uses_gpu(self):
        bpy = self.fake_bpy([])
        bpy.context.scene.cycles.device = "GPU"
        runtime.configure_cycles(bpy, "CPU")
        self.assertEqual(bpy.context.scene.cycles.device, "CPU")

    def test_worker_expression_handles_spaces_unicode_and_quotes(self):
        build = Path("output é 'quoted'")
        bpy = self.fake_bpy([])
        bpy.context.scene.render.filepath = ""
        with patch.dict(sys.modules, {"bpy": bpy}):
            exec(runtime.render_expression("CPU", build), {})
        self.assertEqual(bpy.context.scene.render.filepath, str(build / "frames" / "frame_"))

    def test_gpu_probe_propagates_failure(self):
        with patch("runtime_config.tool_path", return_value=Path(sys.executable)):
            with patch("runtime_config.run_process", side_effect=subprocess.CalledProcessError(1, "blender")):
                with self.assertRaises(subprocess.CalledProcessError):
                    runtime.check_render_device("HIP")

    def test_text_io_is_explicitly_utf8(self):
        import ast

        for path in runtime.ROOT.glob("*.py"):
            if path.name.startswith("test_"):
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    if node.func.attr in ("read_text", "write_text"):
                        self.assertTrue(any(k.arg == "encoding" for k in node.keywords),
                                        f"{path.name}:{node.lineno} must specify encoding")


class SetupTests(unittest.TestCase):
    def test_optional_windows_ffmpeg_install(self):
        with patch.object(sys, "argv", ["setup_runtime.py", "--only", "ffmpeg"]), \
                patch.object(sys, "platform", "win32"), \
                patch("setup_runtime.platform.machine", return_value="AMD64"), \
                patch("setup_runtime.install") as install:
            setup.main()
        url, digest, folder = setup.FFMPEG_WINDOWS
        install.assert_called_once_with(url, digest, setup.ROOT / ".tools" / "windows" / "ffmpeg",
                                        folder, "ffmpeg.exe")

    def test_optional_ffmpeg_rejects_linux(self):
        with patch.object(sys, "argv", ["setup_runtime.py", "--only", "ffmpeg"]), \
                patch.object(sys, "platform", "linux"), \
                patch("setup_runtime.platform.machine", return_value="x86_64"), \
                patch("setup_runtime.install") as install, \
                patch("sys.stderr"):
            with self.assertRaises(SystemExit):
                setup.main()
        install.assert_not_called()

    def test_download_verifies_new_and_cached_files(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "archive.zip"
            def retrieve(url, target):
                Path(target).write_bytes(b"bad download")
            with patch("setup_runtime.urllib.request.urlretrieve", side_effect=retrieve):
                with self.assertRaisesRegex(ValueError, "Checksum"):
                    setup.download("https://example.invalid/archive", "0" * 64, path)
            self.assertFalse(path.exists())
            self.assertFalse(path.with_name(path.name + ".part").exists())
            path.write_bytes(b"bad cache")
            with self.assertRaisesRegex(ValueError, "Checksum"):
                setup.download("unused", "0" * 64, path)

    def test_extract_rejects_zip_traversal(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            archive = root / "archive.zip"
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr("../escaped.txt", "not allowed")
            with self.assertRaisesRegex(ValueError, "Unsafe"):
                setup.extract(archive, root / "target")
            self.assertFalse((root / "escaped.txt").exists())

    def test_install_selects_platform_folder_and_preserves_existing_files(self):
        import hashlib

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            archive = root / ".tools" / "downloads" / "fixture.zip"
            archive.parent.mkdir(parents=True)
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr("portable/tool.exe", "explicit fixture")
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            target = root / ".tools" / "windows" / "tool"
            with patch.object(setup, "ROOT", root):
                setup.install("https://example.invalid/fixture.zip", digest, target, "portable", "tool.exe")
                setup.install("https://example.invalid/fixture.zip", digest, target, "portable", "tool.exe")
            self.assertEqual((target / "tool.exe").read_text(encoding="utf-8"), "explicit fixture")

    def test_install_reuses_an_explicit_original_archive_without_network(self):
        import hashlib

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            archive = root / "original.zip"
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr("Rig/source.blend", "explicit rig fixture")
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            target = root / "installed"
            with patch.object(setup, "ROOT", root), \
                    patch("setup_runtime.urllib.request.urlretrieve") as retrieve:
                setup.install("https://example.invalid/missing.zip", digest, target, "",
                              "Rig/source.blend", archive=archive)
            retrieve.assert_not_called()
            self.assertEqual((target / "Rig" / "source.blend").read_text(encoding="utf-8"),
                             "explicit rig fixture")


class RenderWorkerTests(unittest.TestCase):
    def test_backend_is_forwarded_to_workers_and_invalidates_frame_checkpoints(self):
        import render

        with tempfile.TemporaryDirectory(prefix="vidéo workers 'quoted' ") as folder:
            root = Path(folder)
            (root / "frames").mkdir()
            episode = json.loads((runtime.ROOT / "episode.json").read_text(encoding="utf-8"))
            episode["turns"] = []
            episode_file = root / "episode.json"
            episode_file.write_text(json.dumps(episode), encoding="utf-8")
            from episode_config import read_episode
            resolved = read_episode(episode_file)
            timeline = {"duration": 2 / 24, "fps": 24, "turns": []}
            manifest = {"episode": resolved, "timeline": timeline, "width": 32, "height": 32,
                        "motion_step": 1}
            (root / "timeline.json").write_text(json.dumps(timeline), encoding="utf-8")
            (root / "scene_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            (root / "studio.blend").write_bytes(b"explicit worker fixture, not an actual Blender scene")
            commands = []

            def worker(command, **kwargs):
                commands.append(command)
                for frame in command[command.index("-f") + 1].split(","):
                    path = root / "frames" / f"frame_{int(frame):04d}.png"
                    path.write_bytes(b"\x89PNG\r\n\x1a\n" + bytes(4) + b"IHDR"
                                     + struct.pack(">II", 32, 32) + bytes(32)
                                     + b"\x00\x00\x00\x00IEND\xaeB`\x82")
                return SimpleNamespace(returncode=0)

            def invoke(backend):
                argv = ["render.py", "frames", "--episode", str(episode_file), "--build", str(root),
                        "--jobs", "1", "--render-device", backend]
                with patch.object(sys, "argv", argv), patch("render.run_process", side_effect=worker):
                    render.main()

            invoke("HIP")
            self.assertEqual(len(commands), 1)
            expression = commands[0][commands[0].index("--python-expr") + 1]
            self.assertIn("configure_cycles(bpy, 'HIP')", expression)
            self.assertIn(repr(str(root / "frames" / "frame_")), expression)
            invoke("HIP")
            self.assertEqual(len(commands), 1, "Matching backend must resume valid frames")
            invoke("CPU")
            self.assertEqual(len(commands), 2, "Backend change must rerender all frames")
            checkpoint = json.loads((root / "render_checkpoint.json").read_text(encoding="utf-8"))
            self.assertEqual(checkpoint["render_device"], "CPU")


@unittest.skipUnless(os.environ.get("BLENDER_SMOKE_TEST"), "Set BLENDER_SMOKE_TEST=1 to render a test frame")
class BlenderSmokeTests(unittest.TestCase):
    def test_actual_frame(self):
        from render import valid_frame

        backend = os.environ.get("BLENDER_TEST_DEVICE", "CPU")
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "smoke.png"
            expression = (
                "import bpy; s=bpy.context.scene; s.render.engine='CYCLES'; "
                + runtime.render_expression(backend)
                + "s.cycles.samples=1; s.cycles.use_denoising=False; "
                "s.render.resolution_x=32; s.render.resolution_y=32; "
                "s.render.resolution_percentage=100; s.render.image_settings.file_format='PNG'; "
                f"s.render.filepath={str(output)!r}; bpy.ops.render.render(write_still=True)"
            )
            subprocess.run([str(runtime.tool_path("blender")), "-b", "--factory-startup",
                            "--disable-autoexec", "--python-exit-code", "1",
                            "--python-expr", expression], check=True, timeout=300)
            self.assertTrue(valid_frame(output, 32, 32))


if __name__ == "__main__":
    unittest.main()
