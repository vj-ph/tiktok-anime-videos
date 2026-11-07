import tempfile
import unittest
import wave
from pathlib import Path

from derive_long_speaking import short_edit, splice_audio


class ShortEditTests(unittest.TestCase):
    def timeline(self):
        turns = []
        for index, (kind, part) in enumerate(
                (("opening", 0), ("dialogue", 1), ("dialogue", 2), ("dialogue", 3), ("cta", 0))):
            first = index * 100
            turns.append({"id": str(index), "kind": kind, "part": part,
                          "start_frame": first, "end_frame": first + 40,
                          "start": first / 24, "end": (first + 40) / 24,
                          "words": [{"word": "test", "start": .1, "end": .8}]})
        return {"fps": 24, "turns": turns, "duration": 20, "total_frames": 480}

    def ranges(self, timeline):
        return [{"turn_id": t["id"], "start_frame": t["start_frame"],
                 "end_frame": t["end_frame"] + 12} for t in timeline["turns"]]

    def test_complete_turns_keep_local_alignment_and_source_offsets(self):
        original = self.timeline()
        result, edits = short_edit(original, self.ranges(original))
        self.assertEqual(result["total_frames"], 5 * 52 + 3 * 72)
        self.assertEqual(len(result["silent_notices"]), 3)
        self.assertEqual([n["panel_id"] for n in result["silent_notices"]],
                         ["prepare_teil1", "reading_summary", "prepare_teil3"])
        for source, target in zip(original["turns"], result["turns"]):
            self.assertEqual(source["words"], target["words"])
            self.assertEqual(target["source_start_frame"], source["start_frame"])
            self.assertEqual(target["end_frame"] - target["start_frame"], 40)
        self.assertEqual(edits[-1]["output_end"], result["total_frames"])
        self.assertEqual(original["turns"][1]["start_frame"], 100)

    def test_truncated_turn_is_rejected(self):
        original = self.timeline()
        ranges = self.ranges(original)
        ranges[1]["end_frame"] = original["turns"][1]["end_frame"] - 1
        with self.assertRaisesRegex(ValueError, "complete speech"):
            short_edit(original, ranges)

    def test_audio_spans_and_silent_card_are_exact(self):
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory) / "source.wav", Path(directory) / "target.wav"
            pcm = b"\x10\x00" * 2000 + b"\x20\x00" * 2000
            with wave.open(str(source), "wb") as wav:
                wav.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
                wav.writeframes(pcm)
            edits = [{"source_start": 1, "source_end": 2, "output_end": 1},
                     {"frames": 1, "output_end": 2},
                     {"source_start": 0, "source_end": 1, "output_end": 3}]
            report = splice_audio(source, target, edits, 24)
            with wave.open(str(target), "rb") as wav:
                self.assertEqual(wav.readframes(wav.getnframes()),
                                 pcm[4000:] + bytes(4000) + pcm[:4000])
            self.assertTrue(report["exact_source_pcm_spans"])


if __name__ == "__main__":
    unittest.main()
