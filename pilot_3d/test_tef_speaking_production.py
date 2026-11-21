"""Approval-bound production, native-resolution composition and encoded checks."""

import json
from io import StringIO
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

import numpy as np
from PIL import Image

from prepare_audio import atomic_json, sha256_file
from social_captions import caption_pages
from tef_speaking_full import compile_episode
from tef_speaking_preview import compose, native_settings, review
from tef_speaking_production import RENDER, REQUIRED, build_production, load_production, production_reuse_spec
from test_tef_section_b import synthetic_timeline

ROOT = Path(__file__).resolve().parent


class TefProductionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / "preview"
        self.source.mkdir()
        self.preview = compile_episode(ROOT / "episodes" / "tef_canada_mock1_full_preview.json")
        for name in REQUIRED:
            (self.source / name).write_bytes(b"explicit synthetic frozen-preview fixture")
        atomic_json(self.source / "episode.json", self.preview)
        self.input_asset = self.root / "source_asset.txt"
        self.input_asset.write_bytes(b"explicit original input fixture")
        atomic_json(self.source / "preview_inputs.json", {
            str(self.input_asset): sha256_file(self.input_asset)})
        atomic_json(self.source / "delivery_checks.json", {
            "preview_only": True, "encoded_checks": [{"frame": 0, "synthetic": True}]})
        (self.source / "source_export").mkdir()
        (self.source / "source_export" / "fixture.py").write_text("frozen fixture", encoding="utf-8")
        atomic_json(self.source / "export_manifest.json", {
            "files_sha256": {name: sha256_file(self.source / name) for name in REQUIRED},
            "source_sha256": {"fixture.py": sha256_file(
                self.source / "source_export" / "fixture.py")}})
        self.config = {
            "template": "tef_speaking_full_production", "id": "tef_production_fixture",
            "approved_preview": "preview",
            "approved_preview_manifest_sha256": sha256_file(self.source / "export_manifest.json"),
            "approved_base_scene_sha256": sha256_file(Path(self.preview["scene"]["base_scene"])),
            "preview_approval": {"approved_by": "user", "approved_on": "2026-11-18"},
            "render": dict(RENDER),
        }
        self.path = self.root / "production.json"
        atomic_json(self.path, self.config)

    def test_production_preserves_approved_content_and_rejects_modified_source(self):
        episode = load_production(self.path)
        for name in ("turns", "voices", "promotion", "sections", "source", "fps"):
            self.assertEqual(episode[name], self.preview[name])
        self.assertEqual(native_settings(episode),
                         {"width": 1280, "height": 640, "samples": 8, "motion_step": 2})
        self.assertEqual(native_settings(self.preview),
                         {"width": 640, "height": 320, "samples": 2, "motion_step": 3})
        for target in (self.source / "dialogue.wav", self.source / "source_export" / "fixture.py",
                       self.input_asset):
            before = target.read_bytes()
            target.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "changed"):
                load_production(self.path)
            target.write_bytes(before)
        base_digest = self.config["approved_base_scene_sha256"]
        self.config["approved_base_scene_sha256"] = "0" * 64
        atomic_json(self.path, self.config)
        with self.assertRaisesRegex(ValueError, "base scene changed"):
            load_production(self.path)
        self.config["approved_base_scene_sha256"] = base_digest
        self.config["render"]["native_scale"] = .5
        atomic_json(self.path, self.config)
        with self.assertRaisesRegex(ValueError, "full-resolution"):
            load_production(self.path)
        self.config["render"] = dict(RENDER)
        self.config.pop("preview_approval")
        atomic_json(self.path, self.config)
        with self.assertRaisesRegex(ValueError, "approved preview"):
            load_production(self.path)

    def test_cli_dispatches_production_and_rejects_preview_or_missing_audio(self):
        from pipeline import main

        args = ["pipeline.py", "build", "--episode", str(self.path), "--build",
                str(self.root / "production"), "--profile", "production",
                "--reuse-audio", str(self.source), "--qwen-python", sys.executable]
        with patch.object(sys, "argv", args), \
                patch("tef_speaking_production.build_production") as build:
            main()
        build.assert_called_once_with(self.path, self.root / "production", reuse_audio=self.source,
                                      jobs=4, until="export", render_device="CPU")
        for variant in (
                ["pipeline.py", "validate", "--episode", str(self.path)],
                ["pipeline.py", "validate", "--episode", str(self.path), "--profile", "production"]):
            with patch.object(sys, "argv", [*variant, "--qwen-python", sys.executable]), \
                    patch("sys.stderr", new_callable=StringIO), self.assertRaises(SystemExit) as result:
                main()
            self.assertEqual(result.exception.code, 1)

    def test_requires_exact_approved_reuse_and_never_uses_preview_scene(self):
        episode = load_production(self.path)
        with self.assertRaisesRegex(ValueError, "--reuse-audio"):
            production_reuse_spec(episode, None)
        with self.assertRaisesRegex(ValueError, "--reuse-audio"):
            production_reuse_spec(episode, self.root)
        with patch("pipeline.audio_reuse_spec", return_value={"files_sha256": {}}) as reuse:
            production_reuse_spec(episode, self.source)
        reuse.assert_called_once_with(episode, self.source)
        target = self.root / "production"
        with patch("tef_speaking_production.production_reuse_spec"), \
                patch("tef_speaking_preview.build_preview") as build:
            build_production(self.path, target, reuse_audio=self.source, jobs=3, until="scene")
        self.assertEqual(build.call_args.kwargs,
                         {"jobs": 3, "until": "scene", "reuse_audio": self.source,
                          "profile": "production", "render_device": "CPU"})
        with patch("tef_speaking_production.production_reuse_spec"):
            with self.assertRaisesRegex(ValueError, "separate sibling"):
                build_production(self.path, self.source, reuse_audio=self.source)

    def test_1080p_composition_uses_native_pixels_and_preserves_every_layout(self):
        episode = load_production(self.path)
        timeline = synthetic_timeline(episode)
        pages = caption_pages(episode, timeline)
        rng = np.random.default_rng(42)
        native = Image.fromarray(rng.integers(0, 256, (640, 1280, 3), dtype=np.uint8))
        for turn in timeline["turns"]:
            frame = turn["start_frame"] + 24
            image = compose(episode, timeline, pages, frame, native)
            self.assertEqual(image.size, (1920, 1080))
            if turn["kind"] in ("opening", "model"):
                self.assertEqual(image.crop((64, 212, 1344, 852)).tobytes(), native.tobytes())
            if turn["kind"] == "notice":
                image = compose(episode, timeline, pages, turn["end_frame"], native)
                self.assertEqual(image.getpixel((100, 990)), (244, 206, 114))
        with self.assertRaisesRegex(ValueError, "native landscape"):
            compose(episode, timeline, pages, 0, Image.new("RGB", (640, 320)))
        self.assertEqual(episode["turns"], self.preview["turns"])

    def test_caption_pagination_measures_real_1080p_font_without_retiming_words(self):
        episode = load_production(self.path)
        text = ("les options et l'annulation. Je t'enverrai les r\u00e9ponses, sans t'inscrire. "
                "Tu d\u00e9cideras ensuite si un samedi libre vaut cet essai ou si tu pr\u00e9f\u00e8res "
                "une autre activit\u00e9 cr\u00e9ative.")
        episode["turns"] = [dict(episode["turns"][0], text=text)]
        timeline = synthetic_timeline(episode)
        before = json.dumps(timeline, sort_keys=True)
        pages = caption_pages(episode, timeline)
        self.assertEqual(len(pages), 2)
        self.assertEqual([word for page in pages for word in page["words"]], timeline["turns"][0]["words"])
        native = Image.new("RGB", (1280, 640))
        for page in pages:
            frame = round((page["start"] + page["end"]) * 12)
            self.assertEqual(compose(episode, timeline, pages, frame, native).size, (1920, 1080))
        self.assertEqual(json.dumps(timeline, sort_keys=True), before)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
    def test_real_encoded_1080p_frame_clock_motion_on_twos_and_silent_countdowns(self):
        episode = load_production(self.path)
        episode["title"] = "Essai"
        turns = []
        for identifier, kind, section, start, end, pause in (
                ("opening", "opening", None, 0, 3, 0),
                ("A", "notice", "A", 3, 6, 6),
                ("B", "notice", "B", 12, 15, 6),
                ("closing", "cta", None, 21, 24, 0)):
            turn = {"id": identifier, "kind": kind, "section": section, "start_frame": start,
                    "end_frame": end, "pause_after_frames": pause, "start": start / 24,
                    "end": end / 24, "words": []}
            if identifier == "opening":
                turn["words"] = [{"word": "Essai", "start": .01, "end": .1}]
            turns.append(turn)
        episode["turns"] = turns
        timeline = {"fps": 24, "total_frames": 24, "duration": 1.0, "turns": turns}
        build = self.root / "encoded"
        (build / "frames").mkdir(parents=True)
        pcm = np.zeros(48000, dtype="<i2")
        for turn in turns:
            left, right = turn["start_frame"] * 2000, turn["end_frame"] * 2000
            pcm[left:right] = (6000 * np.sin(np.arange(right - left) * 2 * np.pi * 440 / 48000)).astype("<i2")
        with wave.open(str(build / "dialogue.wav"), "wb") as wav:
            wav.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
            wav.writeframes(pcm.tobytes())
        for frame in range(1, 25, 2):
            Image.new("RGB", (1280, 640), (frame, 80, 110)).save(
                build / "frames" / f"frame_{frame:04d}.png")
        command = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "rawvideo",
                   "-pix_fmt", "rgb24", "-s", "1920x1080", "-r", "24", "-i", "pipe:0",
                   "-i", str(build / "dialogue.wav"), "-c:v", "libx264", "-preset", "ultrafast",
                   "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
                   "-t", "1", str(build / "production_youtube.mp4")]
        with subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.PIPE) as encoder:
            for frame in range(24):
                with Image.open(build / "frames" / f"frame_{1 + frame//2*2:04d}.png") as native:
                    image = compose(episode, timeline, [], frame, native)
                encoder.stdin.write(image.tobytes())
            encoder.stdin.close()
            errors = encoder.stderr.read().decode()
            self.assertEqual(encoder.wait(), 0, errors)
        review(build, episode, timeline, [])
        report = json.loads((build / "delivery_checks.json").read_text(encoding="utf-8"))
        self.assertFalse(report["preview_only"])
        self.assertGreater(report["audio_correlation"], .98)
        self.assertEqual(len(report["notice_silences"]), 2)
        self.assertTrue(all(c["encoded_guarded_peak_pcm16"] == 0 for c in report["notice_silences"]))


if __name__ == "__main__":
    unittest.main()
