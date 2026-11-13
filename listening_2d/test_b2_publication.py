import unittest

from publish_b2_assets import NUMBERS, TOTALS, caption


class B2PublicationTests(unittest.TestCase):
    episode = {
        "edition": {"month": "November", "year": 2026, "episode": 1},
        "promotion": {"amazon_url": "https://amzn.eu/d/07GfdR1Q"},
    }

    def clock(self, part):
        return dict(
            duration=150, selected_numbers=list(NUMBERS[part]),
            total_questions=TOTALS[part], adapted_pauses=True,
            events=[dict(kind="chime", audio_id="chime_back"),
                    dict(kind="reveal", audio_id="chime_remove")],
        )

    def test_short_scope_pauses_and_reveal_credit(self):
        for part in (1, 2, 3):
            with self.subTest(part=part):
                result = caption("instagram", part, self.clock(part), self.episode)
                self.assertIn(f"{len(NUMBERS[part])} von {TOTALS[part]}", result)
                self.assertIn("back/remove", result)
                self.assertNotIn("start/back", result)
                self.assertIn("https://amzn.eu/d/07GfdR1Q", result)
                self.assertIn("Link in der Bio", result)
                self.assertNotIn("unverändert", result)
                if part == 2:
                    self.assertIn("Aufgabe 49.", result)
                    self.assertNotIn("Aufgaben 49.", result)
                if part in (1, 2):
                    self.assertIn("15 stille Sekunden zum Lesen", result)
                    self.assertIn("10 stille Sekunden", result)
                else:
                    self.assertIn("Keine zusätzliche Lesephase", result)
                    self.assertIn("15 stille Sekunden Antwortzeit", result)
                self.assertLessEqual(len(result), 2200)

    def test_rejects_mismatched_selection_or_pause_contract(self):
        clock = self.clock(2)
        clock["selected_numbers"] = [49, 50]
        with self.assertRaises(AssertionError):
            caption("youtube", 2, clock, self.episode)
        clock = self.clock(2)
        clock["adapted_pauses"] = False
        with self.assertRaises(AssertionError):
            caption("youtube", 2, clock, self.episode)

    def test_full_reveal_groups_and_measured_chapters(self):
        clock = dict(duration=1386.8, events=[
            dict(id="instruction_2", start_frame=9000),
            dict(id="instruction_3", start_frame=24000),
            dict(id="summary_read", start_frame=32710),
            dict(id="reveal", audio_id="chime_remove", kind="reveal"),
        ])
        result = caption("youtube", None, clock, self.episode)
        self.assertIn("46–50 / 51–55", result)
        self.assertIn("je drei Sekunden", result)
        self.assertIn("06:15 Teil 2", result)
        self.assertIn("16:40 Teil 3", result)
        self.assertIn("22:42 Lösungen", result)
        self.assertIn("Link in der Beschreibung", result)


if __name__ == "__main__":
    unittest.main()
