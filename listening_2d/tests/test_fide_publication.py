import unittest

from listening_2d.preparation.prepare_fide import EPISODE, read
from listening_2d.publishing.publish_fide_assets import SAFE, caption, contains, cover


class FidePublicationTests(unittest.TestCase):
    def setUp(self):
        self.episode = read(EPISODE)
        identifiers = ["context_a2_sbb", "context_a2_tram", "transition",
                       "context_b1_verwaltung", "context_b1_nachbarn",
                       "solution_7", "solution_13", "cta",
                       *(f"recording_{n}" for n in range(7, 19))]
        self.timeline = {"duration": 805.5, "events": [
            {"id": ident, "start": index * 30 + .25, "start_frame": index * 720 + 6}
            for index, ident in enumerate(identifiers, 1)]}

    def test_all_platforms_include_all_complete_replay_targets(self):
        for platform in ("youtube", "tiktok", "instagram"):
            result = caption(platform, self.episode, self.timeline)
            for number in range(7, 19):
                self.assertIn(f"· Aufgabe {number}\n", result)
            self.assertIn(self.episode["promotion"]["amazon_url"], result)
            if platform != "youtube":
                self.assertLessEqual(len(result), 2200)

    def test_descriptions_do_not_claim_official_fixed_timing(self):
        result = caption("youtube", self.episode, self.timeline)
        self.assertIn("keine offiziellen Zeitvorgaben", result)
        self.assertIn("erst nach dem gesamten Test", result)
        self.assertIn("KI-generierte Stimmen", result)

    def test_social_cover_essentials_survive_center_crops(self):
        image, report = cover(self.episode, portrait=True)
        self.assertEqual(image.size, (1080, 1920))
        for region in report["regions"]:
            self.assertTrue(contains(SAFE, region["bounds"]), region)
        landscape, _ = cover(self.episode, portrait=False)
        self.assertEqual(landscape.size, (1920, 1080))


if __name__ == "__main__":
    unittest.main()
