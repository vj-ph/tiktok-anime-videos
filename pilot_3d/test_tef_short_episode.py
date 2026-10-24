import json
from pathlib import Path
import tempfile
import unittest

from episode_config import check_timeline, read_episode, section_windows, validate_template
from picture_presentation import picture_windows
from social_captions import caption_pages, make_ass, validate_layout, write_publication
from test_episode_config import clock

ROOT = Path(__file__).resolve().parent


class TefShortEpisodeTests(unittest.TestCase):
    def setUp(self):
        self.episode = read_episode(ROOT / "episodes/tef_canada_a1_short.json")
        self.full = read_episode(ROOT / "episodes/tef_canada_a1.json")

    def test_short_episode_and_original_assets_validate(self):
        validate_template(self.episode, check_assets=True)
        validate_layout(self.episode)
        self.assertEqual(self.episode["source"]["scope"], "short_excerpt")
        self.assertEqual(self.episode["source"]["duration_limit_seconds"], 90)
        self.assertEqual(self.episode["exam"], self.full["exam"])
        for field in ("voices", "pictures", "scene", "book_cover"):
            self.assertEqual(self.episode[field], self.full[field])
        self.assertEqual(self.episode["pictures"]["atelier_clic_voisin"]["layout"], "notice_detail")
        self.assertEqual(self.episode["pictures"]["atelier_clic_voisin"]["crop"], [236, 44, 966, 538])
        self.assertEqual(self.episode["source"]["exercise"], self.full["source"]["exercise"])
        self.assertEqual(self.episode["source"]["book"], self.full["source"]["book"])

    def test_ten_turn_excerpt_preserves_two_coherent_question_answer_exchanges(self):
        turns = self.episode["turns"]
        self.assertEqual([t["id"] for t in turns], ["01", "02", "03", "04", "05", "06", "07", "08", "23", "24"])
        original = {t["id"]: t for t in self.full["turns"]}
        for turn in turns:
            if turn["id"] == "23":
                self.assertEqual(turn["text"], "Merci pour ces renseignements. Bonne journée.")
            else:
                self.assertEqual(turn, {k: v for k, v in original[turn["id"]].items() if k != "section"})
        self.assertEqual([t["speaker"] for t in turns[2:]], ["candidate_a", "examiner"] * 4)
        self.assertIn("Quels jours", turns[4]["text"])
        self.assertIn("six semaines", turns[5]["text"])
        self.assertIn("Donc, je ne dois pas venir les deux soirs", turns[6]["text"])
        self.assertIn("gratuit", turns[7]["text"])
        self.assertIn("s'inscrire", turns[7]["text"])
        self.assertIn("Bonne journée", turns[-1]["text"])
        self.assertEqual(len(self.full["turns"]), 24)

    def test_coverage_does_not_claim_omitted_topics(self):
        source = self.episode["source"]
        turns = {t["id"] for t in self.episode["turns"]}
        self.assertEqual(len(source["coverage"]), 4)
        self.assertEqual(len(source["omitted_from_excerpt"]), 4)
        for ids in source["coverage"].values():
            self.assertTrue(ids and set(ids) <= turns)
        self.assertNotIn("Equipment and useful activities", source["coverage"])
        self.assertNotIn("Vague answer and full Thursday group", source["coverage"])
        self.assertIn("extrait", self.episode["publication"]["intro"].lower())
        self.assertIn("autres questions", self.episode["publication"]["disclosure"])

    def test_single_heading_and_concrete_opening_title_are_used_throughout(self):
        timeline = clock(self.episode, seconds=18)
        check_timeline(self.episode, timeline)
        self.assertEqual(self.episode["title"], "Atelier informatique")
        self.assertEqual(self.episode["hook"], "Atelier informatique")
        self.assertEqual(self.episode["header"]["topic"], "Section A · Se renseigner")
        windows = section_windows(self.episode, timeline)
        self.assertEqual(len(windows), 1)
        self.assertEqual(windows[0]["start"], 0)
        self.assertEqual(windows[0]["end"], timeline["duration"])
        ass = make_ass(self.episode, timeline)
        self.assertNotIn("Jeu de rôle", ass)
        self.assertNotIn("À vous de poser les questions", ass)
        self.assertIn("Atelier informatique", ass)

    def test_pacing_card_and_subtitle_policy_are_not_cut_to_meet_the_duration_limit(self):
        self.assertEqual(self.episode["intro_seconds"], 2.5)
        self.assertEqual(self.episode["outro_seconds"], 6)
        self.assertEqual(self.episode["takeaway"], [])
        self.assertEqual(self.episode["subtitle_mode"], "readable")
        self.assertEqual(self.episode["turns"][0]["pause_after"], 3)
        self.assertTrue(all(t["pause_after"] == 1.2 for t in self.episode["turns"][2:]))
        timeline = clock(self.episode, seconds=18)
        reveal, compact = picture_windows(self.episode, timeline)
        self.assertEqual(reveal["end_frame"] - reveal["start_frame"], 192)
        self.assertEqual(reveal["start_frame"] - timeline["turns"][1]["end_frame"], 29)
        self.assertEqual(compact["start_frame"], reveal["end_frame"])
        for turn in timeline["turns"]:
            pages = [p for p in caption_pages(self.episode, timeline) if p["turn_id"] == turn["id"]]
            self.assertEqual(" ".join(p["text"] for p in pages), turn["text"])

    def test_book_cta_and_both_posting_drafts_explicitly_point_to_the_full_model(self):
        self.assertEqual(self.episode["cta"],
                         ["Réponse modèle complète", "dans notre livre TEF Canada", "Lien Amazon dans le profil"])
        ass = make_ass(self.episode, clock(self.episode, seconds=18))
        self.assertIn("Réponse modèle complète", ass)
        for platform in ("tiktok", "instagram"):
            text = (ROOT.parent / "posts/tef_canada_a1_short" / f"{platform}.txt").read_text()
            for required in ("Publicité", "réponse modèle complète", "extrait",
                             "Annonce : French Compass", "Rain Rig", "Snow Rig", "CC BY 4.0"):
                self.assertIn(required, text)
            self.assertNotIn("jeudi est complet", text)
        with tempfile.TemporaryDirectory() as folder:
            write_publication(Path(folder), self.episode)
            text = (Path(folder) / "publishing_caption.txt").read_text()
            self.assertIn("réponse modèle complète", text)
            self.assertIn("Annonce : French Compass", text)


if __name__ == "__main__":
    unittest.main()
