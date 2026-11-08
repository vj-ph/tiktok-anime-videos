import copy
import unittest

from derive_a2_speaking import SHORT_TURNS, short_edit


class A2DerivativeTests(unittest.TestCase):
    def timeline(self):
        turns = []
        for number in range(1, 56):
            start = (number - 1) * 48
            turns.append({
                "id": f"a2_{number:02d}", "start_frame": start, "end_frame": start + 36,
                "start": start / 24, "end": (start + 36) / 24,
                "part": 0 if number < 6 or number == 55 else 1 if number < 24 else 2 if number < 40 else 3,
                "kind": "opening" if number == 1 else "cta" if number == 55 else "model",
                "words": [{"word": "fixture", "start": .2, "end": .8}],
                "mouth_cues": [{"value": "B", "start": .2, "end": .8}],
            })
        return {"fps": 24, "turns": turns, "total_frames": 55 * 48, "duration": 110}

    def test_rebases_complete_turns_without_changing_local_words_or_lips(self):
        source = self.timeline()
        before = copy.deepcopy(source)
        result, edits = short_edit(source)
        self.assertEqual(before, source)
        self.assertEqual(32, len(result["turns"]))
        self.assertEqual(64, result["duration"])
        self.assertEqual([f"a2_{n:02d}" for n in SHORT_TURNS], [t["id"] for t in result["turns"]])
        for index, (turn, edit) in enumerate(zip(result["turns"], edits)):
            original = next(t for t in source["turns"] if t["id"] == turn["id"])
            self.assertEqual(original["words"], turn["words"])
            self.assertEqual(original["mouth_cues"], turn["mouth_cues"])
            self.assertEqual(original["start_frame"], turn["source_start_frame"])
            self.assertEqual(48 * index, turn["start_frame"])
            self.assertEqual(48, edit["source_end"] - edit["source_start"])
            self.assertEqual(36, turn["end_frame"] - turn["start_frame"])

    def test_missing_required_turn_or_incomplete_speech_is_rejected(self):
        source = self.timeline()
        source["turns"] = [t for t in source["turns"] if t["id"] != "a2_36"]
        with self.assertRaises(ValueError):
            short_edit(source)
        source = self.timeline()
        source["turns"][0]["end_frame"] = 49
        with self.assertRaisesRegex(ValueError, "complete speech"):
            short_edit(source)

    def test_strict_three_minute_ceiling(self):
        source = self.timeline()
        for turn in source["turns"]:
            for key in ("start_frame", "end_frame"):
                turn[key] *= 3
            for key in ("start", "end"):
                turn[key] *= 3
        source["total_frames"] *= 3
        with self.assertRaisesRegex(ValueError, "strictly below"):
            short_edit(source)


if __name__ == "__main__":
    unittest.main()
