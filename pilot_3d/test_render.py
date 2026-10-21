import json
import math
import os
import shutil
import struct
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from render import ROOT, RIG_CREDITS, ass_time, captions, credit_captions, escape_ass, mux, scene_hash, valid_frame, wrap


class CaptionTests(unittest.TestCase):
    def test_time_carries_to_next_minute(self):
        self.assertEqual(ass_time(59.999), "0:01:00.00")
        self.assertEqual(ass_time(3661.25), "1:01:01.25")

    def test_escape_blocks_override_injection(self):
        self.assertNotIn("{", escape_ass("{\\pos(0,0)}"))
        self.assertNotIn("\\", escape_ass("{\\pos(0,0)}"))

    def test_wrap_preserves_german_words(self):
        value = "Wir möchten zusammen einen Ausflug nach Münster machen."
        self.assertEqual(wrap(value).replace(r"\N", " "), value)

    def test_captions_use_actual_timeline(self):
        episode = {
            "branding": "TEST", "label": "B1", "title": "Ein Ausflug",
            "disclaimer": "Übung", "intro_seconds": 4, "outro_seconds": 4,
            "task_card": ["Wohin?"], "cta": ["Weiter üben"],
        }
        timeline = {"duration": 20, "turns": [{"start": 4.25, "end": 8.5, "name": "Lea", "text": "Gute Idee."}]}
        result = captions(episode, timeline)
        self.assertIn("0:00:04.25,0:00:08.50,Speech", result)
        self.assertIn("0:00:16.00,0:00:20.00,Card", result)
        self.assertIn("Gute Idee.", result)

    def test_clean_export_retains_required_character_credit(self):
        result = credit_captions(39.25)
        self.assertIn("0:00:39.25", result)
        for credit in RIG_CREDITS:
            self.assertIn(credit, result)
        self.assertIn("CC BY 4.0", result)

    def test_resume_rejects_wrong_dimensions_and_incomplete_png(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "frame.png"
            self.assertFalse(valid_frame(path, 90, 160))
            path.write_bytes(b"\x89PNG\r\n\x1a\n" + bytes(4) + b"IHDR" + struct.pack(">II", 90, 160) + bytes(32) + b"\x00\x00\x00\x00IEND\xaeB`\x82")
            self.assertTrue(valid_frame(path, 90, 160))
            self.assertFalse(valid_frame(path, 180, 320))
            path.write_bytes(b"\x89PNG\r\n\x1a\n")
            self.assertFalse(valid_frame(path, 90, 160))

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
    def test_mux_keeps_exact_frame_count_on_twos(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "frames").mkdir()
            episode = json.loads((ROOT / "episode.json").read_text())
            turn = {**episode["turns"][0], "start": 0.25, "end": 0.75, "duration": 0.5}
            episode.update(turns=[episode["turns"][0]], intro_seconds=0.25, outro_seconds=0.5)
            episode["book_cover"] = str(ROOT / episode["book_cover"])
            timeline = {"duration": 1.25, "fps": 24, "turns": [turn]}
            manifest = {"episode": episode, "timeline": timeline, "width": 90, "height": 160, "motion_step": 2}
            for name, value in (("episode.json", episode), ("timeline.json", timeline), ("scene_manifest.json", manifest)):
                (root / name).write_text(json.dumps(value))
            (root / "studio.blend").write_bytes(b"Explicit synthetic mux test; not a Blender scene")
            (root / "frames_manifest.json").write_text(json.dumps({"scene": manifest, "blend_sha256": scene_hash(root)}))
            subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                 "color=c=gray:s=90x160", "-frames:v", "1", "-update", "1", str(root / "plate.png")],
                check=True,
            )
            for index in range(1, 31, 2):
                os.link(root / "plate.png", root / "frames" / f"frame_{index:04d}.png")
            with wave.open(str(root / "dialogue.wav"), "wb") as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(48000)
                audio.writeframes(b"".join(
                    struct.pack("<h", round(2000 * math.sin(2 * math.pi * 440 * index / 48000)))
                    for index in range(60000)
                ))
            with patch("render.ROOT", root):
                mux(root)
            report = json.loads((root / "media_report.json").read_text())
            video = next(stream for stream in report["streams"] if stream["codec_type"] == "video")
            self.assertEqual(int(video["nb_frames"]), 30)
            self.assertAlmostEqual(float(video["duration"]), 1.25, places=4)


if __name__ == "__main__":
    unittest.main()
