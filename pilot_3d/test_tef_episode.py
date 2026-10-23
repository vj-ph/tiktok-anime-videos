import copy
import json
from pathlib import Path
import unittest

from episode_config import check_timeline, read_episode, section_windows, task_window, validate_template
from episode_profiles import active_actors
from produce_v4 import camera_shots
from scene_direction import performance_plan
from social_captions import caption_pages, make_ass, validate_layout
from test_episode_config import clock

ROOT = Path(__file__).resolve().parent


class TefEpisodeTests(unittest.TestCase):
    def setUp(self):
        self.path = ROOT / "episodes/tef_canada_a1.json"
        self.episode = read_episode(self.path)

    def test_real_episode_and_external_assets_validate(self):
        validate_template(self.episode, check_assets=True)
        validate_layout(self.episode)
        self.assertEqual(self.episode["language"], "fr")
        self.assertEqual(self.episode["exam"], {"family": "tef_canada", "skill": "speaking", "section": "A"})
        self.assertNotIn("exam_part", self.episode)
        self.assertEqual(active_actors(self.episode), ("candidate_a", "examiner"))
        source = (self.path.parent / self.episode["source"]["book"]).resolve()
        self.assertTrue(source.is_file())
        self.assertIn(self.episode["source"]["exercise"], source.read_text())
        self.assertNotIn("exercises", self.episode["source"])
        self.assertNotIn("pictures", self.episode)

    def test_french_voice_texts_match_the_authoritative_existing_registry(self):
        registry_path = (self.path.parent / self.episode["source"]["voice_registry"]).resolve()
        registry = {entry["voice_id"]: entry for entry in json.loads(registry_path.read_text())["voices"]}
        for voice in self.episode["voices"].values():
            entry = registry[voice["voice_id"]]
            self.assertTrue(entry["availability"])
            self.assertEqual(voice["reference_text"], entry["reference_text"])
            self.assertEqual(Path(voice["audio"]),
                             registry_path.parents[2] / entry["reference_audio"])
            self.assertNotIn("transcript", voice)
        self.assertEqual(len({voice["voice_id"] for voice in self.episode["voices"].values()}), 2)

    def test_a1_requirements_have_real_speaking_turns_and_consistent_facts(self):
        turns = {turn["id"]: turn for turn in self.episode["turns"]}
        for point, ids in self.episode["source"]["coverage"].items():
            with self.subTest(point=point):
                self.assertTrue(ids)
                self.assertTrue(set(ids) <= set(turns))
        for turn_id, words in {
            "03": ("Bonjour Monsieur", "renseigner"),
            "06": ("mardi ou le jeudi", "dix-huit heures", "dix-neuf heures trente", "six semaines"),
            "08": ("gratuit", "s'inscrire"),
            "10": ("six ordinateurs", "à deux"),
            "12": ("messagerie", "formulaires"),
            "14": ("deux cent quatre", "deuxième étage", "ascenseur"),
            "16": ("Saint-Paul", "deux minutes", "quelques places"),
            "17": ("Quand vous dites", "deux groupes", "jeudi"),
            "18": ("deux places le mardi", "jeudi est complet"),
            "19": ("liste d'attente", "mardi"),
            "20": ("si une place se libère",),
            "22": ("même programme",),
            "23": ("rappellerai", "confirmer l'inscription", "Bonne journée"),
        }.items():
            for word in words:
                self.assertIn(word, turns[turn_id]["text"])
        self.assertEqual([t["speaker"] for t in self.episode["turns"][2:]],
                         ["candidate_a", "examiner"] * 11)
        self.assertTrue(all(turn["look_at"] == ("examiner" if turn["speaker"] == "candidate_a"
                                              else "candidate_a") for turn in turns.values()))

    def test_pedagogical_hold_and_card_do_not_change_exam_timing_claims(self):
        episode = self.episode
        timeline = clock(episode, seconds=18)
        check_timeline(episode, timeline)
        start, end = task_window(timeline)
        self.assertEqual(round((start - timeline["turns"][1]["end"]) * 24), 29)
        self.assertEqual(round((end-start) * 24), 192)
        self.assertEqual(episode["outro_seconds"], 6)
        self.assertEqual(episode["takeaway"], [])
        self.assertTrue(all(t["pause_after"] == 1.2 for t in episode["turns"][2:]))
        self.assertIn("pas au temps officiel", episode["publication"]["disclosure"])
        self.assertNotIn("candidates", [camera for _, camera in camera_shots(episode, timeline)])

    def test_french_headers_caption_words_and_cast_are_consistent(self):
        timeline = clock(self.episode, seconds=18)
        pages = caption_pages(self.episode, timeline)
        for turn in timeline["turns"]:
            self.assertEqual(" ".join(page["text"] for page in pages if page["turn_id"] == turn["id"]),
                             turn["text"])
        self.assertEqual([window["section"] for window in section_windows(self.episode, timeline)],
                         [None, "A", None])
        ass = make_ass(self.episode, timeline)
        self.assertIn("Intervenant : Interlocuteur", ass)
        self.assertIn("Lien Amazon dans le profil", ass)
        for stale in ("DEUTSCHKOMPASS", "DTZ", "Es spricht:", "Amazon-Buchlink", "Samir"):
            self.assertNotIn(stale, ass)
        plan = performance_plan(timeline, self.episode)
        self.assertEqual(set(plan["attention"]), set(active_actors(self.episode)))

    def test_inherited_dtz_voice_cannot_leak_into_interview(self):
        data = copy.deepcopy(self.episode)
        data["voices"]["candidate_b"] = copy.deepcopy(data["voices"]["candidate_a"])
        with self.assertRaisesRegex(ValueError, "inactive"):
            validate_template(data)


if __name__ == "__main__":
    unittest.main()
