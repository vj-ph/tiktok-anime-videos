"""Whole-turn partition, source-frame clock, exact PCM and portrait layout tests."""

import copy
import tempfile
import shutil
from pathlib import Path
import unittest
import wave

from PIL import Image

from derive_tef_speaking_social import (audio_chunks, compose, edit_clip, native_frame,
                                      pages_for, read, speech_episode, encode, review)
from tef_speaking_full import compile_episode
from test_tef_section_b import synthetic_timeline

ROOT = Path(__file__).resolve().parent


class TefSpeakingSocialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = read(ROOT / "episodes" / "tef_canada_mock1_social_five.json")
        cls.episode = compile_episode(ROOT / "episodes" / "tef_canada_mock1_full_preview.json")
        cls.original = synthetic_timeline(cls.episode)
        cls.wrappers = synthetic_timeline(speech_episode(cls.episode, cls.config))
        cls.original["word_alignment"] = {"synthetic_fixture": True}
        cls.wrappers["word_alignment"] = {"synthetic_fixture": True}

    def test_five_parts_cover_all_models_once_keep_silences_and_never_split_a_turn(self):
        model_ids, notices = [], []
        for index, clip in enumerate(self.config["clips"], 1):
            edited, edits = edit_clip(self.original, self.wrappers, clip, index)
            self.assertLess(edited["total_frames"], 4320)
            self.assertEqual([t["kind"] for t in edited["turns"][:2]], ["opening", "setup"])
            self.assertEqual(edited["turns"][-1]["kind"], "cta")
            for turn, edit in zip(edited["turns"], edits):
                src = self.original if edit["source_kind"] == "production" else self.wrappers
                original = next(t for t in src["turns"] if t["id"] == turn["id"])
                self.assertEqual(turn["words"], original["words"])
                self.assertEqual(turn["text"], original["text"])
                self.assertEqual(turn["end_frame"] - turn["start_frame"],
                                 original["end_frame"] - original["start_frame"])
                self.assertEqual(edit["source_start"], original["start_frame"])
                self.assertGreaterEqual(edit["source_end"], original["end_frame"])
                if turn["kind"] == "model":
                    model_ids.append(turn["id"])
                if turn["kind"] == "notice":
                    notices.append(turn["id"])
                    self.assertEqual(turn["pause_after_frames"], 192)
            self.assertEqual(sum(e["source_end"] - e["source_start"] for e in edits),
                             edited["total_frames"])
        self.assertEqual(model_ids, [t["id"] for t in self.original["turns"] if t["kind"] == "model"])
        self.assertEqual(notices, ["A_notice", "B_notice"])

    def test_subthree_minute_limit_includes_openings_and_cta(self):
        original = copy.deepcopy(self.original)
        original["total_frames"] += 4320
        with self.assertRaisesRegex(ValueError, "strictly below"):
            edit_clip(original, self.wrappers, self.config["clips"][0], 1)

    def test_native_mapping_uses_original_global_motion_clock_even_at_odd_cut(self):
        for requested in (0, 1, 2, 1142, 13001, 16290):
            turn = {"source_kind": "production", "source_frame": requested, "start_frame": 101}
            self.assertEqual(native_frame(turn, 101), 1 + requested // 2 * 2)
            self.assertEqual(native_frame(turn, 102), 1 + (requested + 1) // 2 * 2)
        self.assertEqual(native_frame({"source_kind": "speech"}, 0), 1)

    def test_pcm_splice_is_byte_identical_at_both_edit_boundaries(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name, pcm in (("production", bytes(range(250)) * 100), ("speech", b"\x02\x01" * 8000)):
                (root / name).mkdir()
                with wave.open(str(root / name / "dialogue.wav"), "wb") as wav:
                    wav.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
                    wav.writeframes(pcm)
            edits = [{"source_kind": "speech", "source_start": 1, "source_end": 3},
                     {"source_kind": "production", "source_start": 2, "source_end": 5}]
            self.assertEqual(audio_chunks(root / "production", root / "speech", edits),
                             (b"\x02\x01" * 8000)[4000:12000] + (bytes(range(250)) * 100)[8000:20000])

    def test_every_portrait_page_title_promotion_and_notice_boundary_fits(self):
        for index, clip in enumerate(self.config["clips"], 1):
            timeline, _ = edit_clip(self.original, self.wrappers, clip, index)
            pages = pages_for(timeline)
            episode = {**clip, "part": index, "cover": self.episode["book_cover"],
                       "notices": self.episode["preview_notices"],
                       "visible_url": self.episode["promotion"]["visible_url"]}
            native = Image.new("RGB", (1280, 640), (70, 100, 140))
            frames = [round((p["start"] + p["end"]) * 12) for p in pages]
            for turn in timeline["turns"]:
                if turn["kind"] == "notice":
                    frames += [turn["end_frame"] - 1, turn["end_frame"], turn["end_frame"] + 191,
                               turn["end_frame"] + 192]
            for frame in frames:
                image = compose(episode, timeline, pages, frame, native)
                self.assertEqual(image.size, (1080, 1920))
                self.assertEqual(image.getpixel((1000, 1400)), (20, 36, 46))
            self.assertEqual([w for p in pages for w in p["words"]],
                             [w for t in timeline["turns"] for w in t["words"]])
            with self.assertRaisesRegex(ValueError, "native production"):
                compose(episode, timeline, pages, 0, Image.new("RGB", (640, 320)))

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
    def test_real_encoded_portrait_preserves_countdown_silence_and_frame_boundaries(self):
        import math
        import struct

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, folder = root / "source", root / "part"
            (source / "frames").mkdir(parents=True)
            folder.mkdir()
            for frame in range(1, 241, 2):
                Image.new("RGB", (1280, 640), (frame, 100, 140)).save(
                    source / "frames" / f"frame_{frame:04d}.png")
            turns = []
            for identifier, kind, start, end, pause in (
                    ("opening_1", "opening", 0, 12, 0),
                    ("A_notice", "notice", 12, 24, 192),
                    ("A_01", "model", 216, 228, 0),
                    ("closing", "cta", 228, 240, 0)):
                turns.append({"id": identifier, "kind": kind, "section": "A", "start": start/24,
                    "end": end/24, "start_frame": start, "end_frame": end, "pause_after_frames": pause,
                    "source_frame": start, "source_kind": "production",
                    "words": [{"word": "Essai", "start": .1, "end": .3}]})
            timeline = {"fps": 24, "total_frames": 240, "duration": 10, "turns": turns}
            episode = {"id": "portrait_fixture", "part": 1, "section": "A", "title": "Essai",
                       "cover": self.episode["book_cover"], "notices": self.episode["preview_notices"],
                       "visible_url": self.episode["promotion"]["visible_url"]}
            pcm = bytearray(480000 * 2)
            for turn in turns:
                for sample in range(turn["start_frame"]*2000, turn["end_frame"]*2000):
                    struct.pack_into("<h", pcm, sample*2, int(5000*math.sin(sample*2*math.pi*440/48000)))
            with wave.open(str(folder / "dialogue.wav"), "wb") as wav:
                wav.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
                wav.writeframes(pcm)
            encode(source, folder, episode, timeline, [])
            review(source, folder, episode, timeline, [])
            checks = read(folder / "delivery_checks.json")
            self.assertGreater(checks["audio_correlation"], .98)
            self.assertEqual(checks["reading_silences"],
                             [{"id": "A_notice", "seconds": 8, "encoded_guarded_peak_pcm16": 0.0}])
            self.assertIn(216, [c["frame"] for c in checks["encoded_checks"]])


if __name__ == "__main__":
    unittest.main()
