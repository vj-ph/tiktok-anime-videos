import json
from pathlib import Path
import unittest

from episode_config import read_episode, task_window, validate_template
from scene_direction import VERSION
from social_captions import validate_layout
from test_episode_config import clock

ROOT = Path(__file__).resolve().parent
EPISODE = ROOT / "episodes/lerntreffen_dtz.json"


class LerntreffenEpisodeTests(unittest.TestCase):
    def setUp(self):
        self.episode = read_episode(EPISODE)
        self.turns = {turn["id"]: turn for turn in self.episode["turns"]}

    def test_full_episode_has_its_own_identity_and_valid_assets_and_layout(self):
        validate_template(self.episode, check_assets=True)
        validate_layout(self.episode)
        self.assertEqual(self.episode["visual_version"], VERSION)
        self.assertEqual(self.episode["id"], "dtz_lerntreffen_v7")
        self.assertTrue(self.episode["scene"]["entrance"])
        self.assertEqual(len(self.turns), 14)
        self.assertEqual(self.episode["label"], "DTZ B1 · Sprechen · Teil 3")

    def test_source_is_the_book_exercise_not_the_three_turn_technical_demo(self):
        source = self.episode["source"]
        book = (EPISODE.parent / source["book"]).resolve(strict=True)
        text = book.read_text()
        heading = "## Übung 2: Lerntreffen für die DTZ-Prüfung planen"
        self.assertIn(heading, text)
        self.assertEqual(source["exercise"], "Teil 3, Übung 2: Lerntreffen für die DTZ-Prüfung planen")
        coverage = source["coverage"]
        self.assertEqual(list(coverage), self.episode["task_card"])
        for point, ids in coverage.items():
            with self.subTest(point=point):
                self.assertTrue(ids)
                self.assertTrue(all(self.turns[value]["speaker"].startswith("candidate") for value in ids))

    def text_for(self, point):
        return " ".join(self.turns[value]["text"] for value in self.episode["source"]["coverage"][point])

    def test_task_points_have_concrete_and_consistent_decisions(self):
        decisions = {
            "Tag und Uhrzeit": ("Samstag", "zehn", "halb zwölf"),
            "Ort und Dauer": ("Café", "Bibliothek", "eine Stunde", "bis elf"),
            "Was üben?": ("Bildbeschreibungen", "gemeinsam planen", "Fragen"),
            "Wer bringt was mit?": ("mein Heft", "Themenkarten", "Stifte", "Wasser"),
            "Essen und Budget": ("essen", "höchstens fünf Euro"),
            "Plan B": ("kein Platz frei", "Café nebenan", "ruhige Tische"),
        }
        for point, phrases in decisions.items():
            with self.subTest(point=point):
                for phrase in phrases:
                    self.assertIn(phrase, self.text_for(point))
        self.assertEqual(self.turns["04"]["speaker"], "candidate_b")
        self.assertIn("in einem Café lernen", self.turns["04"]["text"])
        self.assertEqual(self.turns["10"]["speaker"], "candidate_b")
        self.assertIn("ruhiger", self.turns["05"]["text"])

    def test_approved_voices_pacing_and_cta_are_unchanged(self):
        original = read_episode(ROOT / "episode_v4.json")
        self.assertEqual(self.episode["voices"], original["voices"])
        self.assertEqual(self.episode["cta"], original["cta"])
        self.assertEqual(self.episode["outro_seconds"], 6)
        self.assertEqual(self.episode["takeaway"], [])
        self.assertEqual(self.episode["takeaway_seconds"], 0)
        self.assertNotIn("promo", self.episode)
        for turn in self.episode["turns"][2:]:
            self.assertEqual(turn["pause_after"], 1.2)
            self.assertEqual(turn["camera"], turn["speaker"])
        timeline = clock(self.episode)
        start, stop = task_window(timeline)
        instruction = timeline["turns"][1]
        self.assertEqual(round((start - instruction["end"]) * timeline["fps"]), 29)
        self.assertEqual(round((stop - start) * timeline["fps"]), 192)
        self.assertEqual(stop, timeline["turns"][2]["start"])
        self.assertEqual(json.loads(EPISODE.read_text())["intro_seconds"], 2.5)


if __name__ == "__main__":
    unittest.main()
