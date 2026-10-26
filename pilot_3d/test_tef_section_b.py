"""Book-based persuasion content and portable synthetic-clock integration checks."""

import copy
from pathlib import Path
import tempfile
import unittest

from entrance import entrance_plan
from episode_config import check_timeline, read_episode, turn_phase, validate_template
from episode_profiles import active_actors, language_profile
from picture_presentation import picture_filters, picture_windows
from prepare_audio import build_timeline, sha256_file
from produce_v4 import camera_shots
from scene_direction import performance_plan
from social_captions import audit_ass, caption_pages, make_ass, validate_layout, write_publication

ROOT = Path(__file__).resolve().parent
EPISODE = ROOT / "episodes" / "tef_canada_b1_short.json"


def synthetic_timeline(episode):
    durations = [max(3, len(turn["text"]) / 17 + 0.7) for turn in episode["turns"]]
    infos = [{"frames": round(seconds * 48000), "sample_rate": 48000, "audio": "/synthetic.wav"}
             for seconds in durations]
    cues = [[{"start": 0, "end": seconds, "value": "X"}] for seconds in durations]
    timeline = build_timeline(episode, infos, cues)
    for turn, seconds in zip(timeline["turns"], durations):
        tokens = turn["text"].split()
        step = (seconds - 0.4) / len(tokens)
        turn["words"] = [{"word": token, "start": 0.15 + index * step,
                          "end": 0.15 + index * step + step * 0.85, "score": 0.9}
                         for index, token in enumerate(tokens)]
    return timeline


class TefSectionBTests(unittest.TestCase):
    def setUp(self):
        self.episode = read_episode(EPISODE)

    def test_independent_section_b_identity_cast_and_strict_excerpt_limit(self):
        episode = self.episode
        validate_template(episode)
        validate_layout(episode)
        self.assertEqual(episode["exam"], {"family": "tef_canada", "skill": "speaking", "section": "B"})
        self.assertEqual(active_actors(episode), ("candidate_a", "examiner"))
        self.assertEqual([turn_phase(turn) for turn in episode["turns"]],
                         ["welcome", "instruction"] + ["dialogue"] * 7)
        self.assertEqual(episode["source"]["duration_limit_seconds"], 90)
        self.assertEqual(episode["source"]["official_section_duration_seconds"], 600)
        self.assertTrue(episode["source"]["exercise_number_not_cefr_level"])
        self.assertIn("TEF Canada", episode["title"])
        self.assertIn("Section B", episode["header"]["topic"])
        self.assertIn("B1 est le numéro", episode["publication"]["disclosure"])
        self.assertIn("10 minutes", episode["publication"]["disclosure"])
        self.assertIn("ni épreuve complète", episode["publication"]["disclosure"])
        self.assertIn("Réponse modèle complète", episode["cta"])
        timeline = synthetic_timeline(episode)
        check_timeline(episode, timeline)
        timeline["total_frames"] = 90 * episode["fps"]
        with self.assertRaisesRegex(ValueError, "strictly below"):
            check_timeline(episode, timeline)

    def test_friend_resists_and_candidate_tailors_arguments_without_inventing_availability(self):
        turns = {turn["id"]: turn for turn in self.episode["turns"]}
        self.assertIn("convaincre", turns["02"]["text"])
        self.assertIn("Je joue votre ami", turns["02"]["text"])
        for phrase in ("deux heures", "samedi matin", "trente-deux dollars", "ingrédients sont compris"):
            self.assertIn(phrase, turns["03"]["text"])
        for phrase in ("cher", "tutoriel gratuit"):
            self.assertIn(phrase, turns["04"]["text"])
        for phrase in ("C'est vrai", "demander de l'aide", "comparer"):
            self.assertIn(phrase, turns["05"]["text"])
        self.assertIn("déjà un déjeuner", turns["06"]["text"])
        self.assertIn("Gardons ton déjeuner", turns["07"]["text"])
        self.assertIn("Vérifions une autre date", turns["07"]["text"])
        self.assertIn("je préfère essayer seul", turns["08"]["text"])
        self.assertIn("Tu décideras", turns["09"]["text"])
        for turn in self.episode["turns"][2:]:
            self.assertNotIn("vous", turn["text"].lower())
            self.assertNotIn(turn["action"], ("describe", "agree"))
            if turn["speaker"] == "examiner":
                self.assertEqual(turn["name"], "Ami")
                self.assertEqual(turn["action"], "consider")
        self.assertEqual(set(sum(self.episode["source"]["coverage"].values(), [])),
                         {turn["id"] for turn in self.episode["turns"][2:]})

    def test_book_advertisement_is_unmodified_and_crop_retains_all_offer_details(self):
        from PIL import Image

        picture = self.episode["pictures"]["cuisine_vegetarienne"]
        self.assertEqual(sha256_file(Path(picture["path"])),
                         "dc04ff7a120a28039e770da9a61fe96ccbe7be21038043b5e335d5810e09e9c6")
        self.assertEqual(picture["purpose"], "task")
        self.assertEqual(picture["layout"], "notice_detail")
        self.assertEqual(picture["crop"], [340, 236, 868, 638])
        with Image.open(picture["path"]) as image:
            self.assertEqual(image.size, (1200, 896))
            image.verify()
        self.assertIn("Practice set B1: Vegetarian cooking workshop", self.episode["source"]["exercise"])
        source = (EPISODE.parent / self.episode["source"]["book"]).resolve()
        if source.is_file():
            text = source.read_text(encoding="utf-8")
            section = text.split("## " + self.episode["source"]["exercise"], 1)[1].split("## Practice set B2", 1)[0]
            for phrase in ("images/25.jpg", "10 h-12 h", "32 dollars", "ingrédients compris",
                           "Le prix me gêne.", "J'ai déjà un déjeuner prévu."):
                self.assertIn(phrase, section)
            original = (EPISODE.parent / self.episode["source"]["images"]["cuisine_vegetarienne"]).resolve()
            self.assertEqual(sha256_file(original), sha256_file(Path(picture["path"])))

    def test_reference_texts_and_voice_ids_match_existing_french_cast(self):
        original = read_episode(ROOT / "episodes" / "tef_canada_a1_short.json")
        for role, voice in self.episode["voices"].items():
            self.assertEqual(voice["voice_id"], original["voices"][role]["voice_id"])
            self.assertEqual(voice["reference_text"], original["voices"][role]["reference_text"])
            self.assertEqual(Path(voice["audio"]).name, Path(original["voices"][role]["audio"]).name)

    def test_argument_prompt_is_scoped_without_mutating_french_or_german_defaults(self):
        original = copy.deepcopy(language_profile({"language": "fr"}))
        self.assertEqual(language_profile(self.episode)["task_picture_prompt"], "Préparez vos arguments.")
        self.assertEqual(language_profile({"language": "fr"}), original)
        for exam in ({"family": "tef_canada", "skill": "speaking", "section": "A"},
                     {"family": "other", "skill": "speaking", "section": "B"},
                     {"family": "tef_canada", "skill": "listening", "section": "B"}):
            self.assertEqual(language_profile({"language": "fr", "exam": exam})["task_picture_prompt"],
                             "Préparez vos questions.")
        self.assertEqual(language_profile({})["task_picture_prompt"], "Bereite deine Fragen vor.")
        ass = make_ass(self.episode, synthetic_timeline(self.episode))
        self.assertIn("Préparez vos arguments.", ass)
        self.assertNotIn("Préparez vos questions.", ass)
        self.assertNotIn("Décrivez l'image.", ass)
        self.assertIn("Intervenant : Ami", ass)

    def test_synthetic_timing_caption_crop_camera_and_entrance_integration(self):
        episode = self.episode
        timeline = synthetic_timeline(episode)
        check_timeline(episode, timeline)
        windows = picture_windows(episode, timeline)
        self.assertEqual([window["mode"] for window in windows], ["reveal", "compact"])
        self.assertEqual([window["turn"] for window in windows], ["02", "03"])
        self.assertAlmostEqual(windows[0]["end"] - windows[0]["start"], 6.0)
        self.assertEqual(windows[0]["end"], timeline["turns"][2]["start"])
        self.assertEqual(windows[1]["end"], timeline["turns"][3]["start"])
        inputs, filters, _, _ = picture_filters(episode, timeline)
        self.assertEqual(inputs.count(episode["pictures"]["cuisine_vegetarienne"]["path"]), 2)
        self.assertTrue(any("crop=528:402:340:236" in item for item in filters))
        self.assertIn((windows[0]["start"], "wide"), camera_shots(episode, timeline))
        self.assertEqual(set(entrance_plan(episode, timeline)["actors"]), {"candidate_a"})
        plan = performance_plan(timeline, episode)
        self.assertEqual(set(plan["attention"]), {"candidate_a", "examiner"})
        self.assertTrue(caption_pages(episode, timeline))
        with tempfile.TemporaryDirectory() as directory:
            report = audit_ass(Path(directory), make_ass(episode, timeline))
            self.assertTrue(report["all_inside"])

    def test_publication_drafts_include_book_cta_disclosures_and_rig_credits(self):
        with tempfile.TemporaryDirectory() as directory:
            build = Path(directory)
            write_publication(build, self.episode)
            for filename in ("publishing_caption.txt", "CREDITS.txt"):
                text = (build / filename).read_text(encoding="utf-8")
                for phrase in ("Snow Rig", "Rain Rig", "CC BY 4.0", "pratique B1"):
                    self.assertIn(phrase, text)
        for platform in ("tiktok", "instagram"):
            text = (ROOT.parent / "posts" / "tef_canada_b1_short" / f"{platform}.txt").read_text(encoding="utf-8")
            for phrase in ("Publicité", "Section B", "B1 est le numéro", "10 minutes",
                           "ni épreuve complète", "Lien Amazon", "Snow Rig", "Rain Rig", "CC BY 4.0"):
                self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
