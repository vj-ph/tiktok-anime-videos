import unittest

from listening_2d.preparation.prepare_fide import EPISODE, read
from listening_2d.publishing.publication_assets import timestamp
from listening_2d.publishing.publish_fide_social_assets import PAIRS, SAFE, caption, contains, cover


class FideSocialPublicationTests(unittest.TestCase):
    def setUp(self):
        self.episode = read(EPISODE)
        self.episode["promotion"]["amazon_url"] = "https://amzn.eu/d/0dDgJ1ZT"
        ids = ["context_a2_sbb", "context_a2_tram", "transition", "context_b1_verwaltung",
               "context_b1_nachbarn", "end_test", "cta", *(f"recording_{n}" for n in range(7, 19))]
        self.timeline = {"events": [{"id": name, "start": i * 31 + .75} for i, name in enumerate(ids)]}

    def test_short_captions_bind_only_selected_replay_targets_and_pauses(self):
        for part, numbers in enumerate(PAIRS, 1):
            for platform in ("youtube", "instagram", "tiktok"):
                result = caption(platform, self.episode, self.timeline, part)
                self.assertIn(f"Video {part}/6", result)
                self.assertIn("kein kompletter Test", result)
                self.assertIn("https://amzn.eu/d/0dDgJ1ZT", result)
                self.assertIn("Mixkit Software interface remove", result)
                self.assertIn("keine offiziellen Zeitvorgaben", result)
                self.assertIn("zehn Sekunden Antwortzeit" if part < 4 else "zwanzig Sekunden Antwortzeit", result)
                self.assertLessEqual(len(result), 2200)
                for n in range(7, 19):
                    target = f"· Aufgabe {n}\n"
                    self.assertEqual(target in result, n in numbers)

    def test_full_chapters_follow_actual_timeline_with_inline_solutions(self):
        result = caption("youtube", self.episode, self.timeline)
        self.assertIn(f'{timestamp(4 * 31 + .75)} B1 · Nachbarschaft', result)
        self.assertIn("alle 12 Aufgaben", result)
        self.assertNotIn("erst nach dem gesamten Test", result)
        self.assertNotIn("keine Musik oder Soundeffekte", result)
        self.assertNotIn("Abschluss\n", result)
        for n in range(7, 19):
            self.assertIn(f"· Aufgabe {n}\n", result)

    def test_covers_preserve_large_numbering_and_all_essentials_in_safe_crops(self):
        for part in range(1, 7):
            image, report = cover(self.episode, True, part)
            self.assertEqual(image.size, (1080, 1920))
            for region in report["regions"]:
                self.assertTrue(contains(SAFE, region["bounds"]))
            badge = next(r for r in report["regions"] if r["text"] == f"Video {part}/6")
            self.assertGreaterEqual(badge["font_px"], 70)
        image, _ = cover(self.episode)
        self.assertEqual(image.size, (1920, 1080))


if __name__ == "__main__":
    unittest.main()
