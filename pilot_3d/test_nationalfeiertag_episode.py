"""The approved comedy introduction and shortened, book-based B2 discussion."""

import json
from pathlib import Path
import unittest

from entrance import entrance_plan
from episode_config import (check_timeline, instruction_turn, read_episode,
                            section_windows, task_window, turn_phase, validate_template)
from prepare_audio import sha256_file
from produce_v4 import camera_shots
from scene_dressing import ASSETS
from social_captions import make_ass, validate_layout
from test_episode_config import clock

ROOT = Path(__file__).resolve().parent


class NationalfeiertagEpisodeTests(unittest.TestCase):
    def setUp(self):
        self.episode = read_episode(ROOT / "episodes/oeif_b2_nationalfeiertag.json")

    def test_real_assets_and_independent_b2_identity(self):
        episode = self.episode
        validate_template(episode, check_assets=True)
        validate_layout(episode)
        self.assertEqual(episode["exam"], {"family": "oeif", "skill": "speaking", "section": "discussion"})
        self.assertEqual(episode["exam_part"], 2)
        self.assertEqual(episode["language"], "de")
        self.assertIn("speaking_oeif_gpt_v2", episode["source"]["book"])
        self.assertIn("Diskussion 7:", episode["source"]["exercise"])
        self.assertIn("zusätzlicher", episode["source"]["exercise"])
        self.assertIn("keine vollständige Prüfung", episode["publication"]["disclosure"])
        self.assertEqual(episode["source"]["duration_limit_seconds"], 120)
        self.assertIn("explicitly selected", episode["source"]["duration_exception"])
        self.assertEqual(sha256_file(Path(episode["book_cover"])),
                         "9057da8026914936a47192f6eafb32ed4042bd698e2b78c23781c4f085084a66")
        self.assertIn("speaking_oeif_gpt_v1/oeif_b2_speaking.jpg", episode["source"]["cover_source"])

    def test_intro_is_welcome_banter_then_one_real_instruction_and_discussion(self):
        turns = self.episode["turns"]
        self.assertEqual([turn_phase(turn) for turn in turns],
                         ["welcome"] * 5 + ["instruction"] + ["dialogue"] * 7)
        self.assertEqual(instruction_turn(turns)["id"], "06")
        self.assertEqual(turns[0]["text"], "Guten Tag. Nehmen Sie bitte Platz.")
        self.assertEqual(turns[0]["camera"], "wide")
        self.assertEqual(turns[1]["camera"], "wide")
        timeline = clock(self.episode)
        check_timeline(self.episode, timeline)
        start, end = task_window(timeline)
        self.assertEqual(round((start - timeline["turns"][5]["end"]) * 24), 29)
        self.assertAlmostEqual(end - start, 8)
        self.assertEqual(end, timeline["turns"][6]["start"])
        self.assertGreater(start, timeline["turns"][4]["end"])
        entrance = entrance_plan(self.episode, timeline)
        self.assertLessEqual(max(item["seat_end"] for item in entrance["actors"].values()), 8)
        self.assertEqual(len(entrance["actors"]), 2)
        self.assertIn((timeline["turns"][1]["start"], "wide"), camera_shots(self.episode, timeline))

    def test_comedy_history_is_not_the_discussion_or_an_official_claim(self):
        turns = self.episode["turns"]
        self.assertIn("Staatsbesuch", turns[1]["text"])
        history = turns[2]["text"]
        for fact in ("26. Oktober 1955", "Nationalrat", "Neutralität", "Seit 1965"):
            self.assertIn(fact, history)
        self.assertNotIn("Staatsvertrag", history)
        self.assertIn("ausschlafen oder spazieren", turns[3]["text"])
        self.assertIn("zusätzlichen Feiertag", turns[5]["text"])
        self.assertIn("Comedy-Intro", self.episode["disclaimer"])
        self.assertIn("keine Prüfungsphase", self.episode["publication"]["disclosure"])
        self.assertNotIn("bestanden", " ".join(turn["text"] for turn in turns).lower())

    def test_dialogue_reacts_to_text_shows_experience_and_debates_real_constraints(self):
        turns = {turn["id"]: turn for turn in self.episode["turns"]}
        for turn_id, phrases in {
            "07": ("Der Text", "Schwester", "gleichzeitig frei", "dafür"),
            "08": ("Hinweis", "Pflegekräfte", "nach eigener Wahl", "gerechter"),
            "09": ("Trotzdem", "Welcher Anlass", "Schichtarbeit"),
            "10": ("Ehrenamt", "Zeitausgleich", "Arbeitsverdichtung"),
            "11": ("faire Verteilung", "kleine Betriebe", "Planungssicherheit"),
            "12": ("faire Dienstpläne", "Frühdienst"),
        }.items():
            for phrase in phrases:
                self.assertIn(phrase, turns[turn_id]["text"])
        for turn_id in ("07", "08", "09", "10", "11", "12"):
            turn = turns[turn_id]
            self.assertEqual(turn["camera"], turn["speaker"])
            self.assertEqual(turn["look_at"], "candidate_b" if turn["speaker"] == "candidate_a" else "candidate_a")
        ids = set(turns)
        self.assertTrue(all(set(value) <= ids for value in self.episode["source"]["coverage"].values()))

    def test_headers_learning_card_and_book_ending_are_coherent(self):
        self.assertEqual(self.episode["title"], "ÖIF B2: Neutral? Nicht bei Feiertagen!")
        self.assertEqual(self.episode["hook"], self.episode["title"])
        self.assertIn("ÖIF B2", self.episode["header"]["brand"])
        timeline = clock(self.episode, seconds=8)
        windows = section_windows(self.episode, timeline)
        self.assertEqual([item["section"] for item in windows], [None, "intro", "discussion", None])
        self.assertEqual(windows[2]["start"], timeline["turns"][5]["start"])
        self.assertEqual(windows[3]["start"], timeline["turns"][-1]["start"])
        self.assertEqual(self.episode["intro_seconds"], 2.5)
        self.assertEqual(self.episode["outro_seconds"], 6)
        self.assertEqual(self.episode["takeaway"], [])
        self.assertEqual(self.episode["cta"][-1], "Amazon-Buchlink im Profil")
        self.assertIn("im ÖIF-B2-Sprechbuch", self.episode["cta"])
        self.assertIn("GEKÜRZTER", self.episode["task_title"])
        self.assertEqual(self.episode["turns"][0]["pause_after"], 3.0)
        self.assertTrue(all(turn["pause_after"] == 1.2 for turn in self.episode["turns"]
                            if turn["id"] not in ("01", "06")))
        ass = make_ass(self.episode, timeline)
        self.assertIn("ÖIF B2:", ass)
        self.assertIn("Nationalfeiertag", ass)
        self.assertNotIn("DTZ B1", ass)
        self.assertNotIn("TIPPS FÜR EUREN DIALOG", ass)

    def test_approved_dressing_and_austrian_reference_provenance(self):
        self.assertEqual(self.episode["scene"]["dressing"],
                         json.loads((ASSETS / "austria.json").read_text()))
        provenance = json.loads((ROOT / "assets/voices/austrian/provenance.json").read_text())
        for role, voice in self.episode["voices"].items():
            record = provenance["voices"][role]
            self.assertIn("gemini_3.8_flash_tts/austrain", record["source_directory"])
            self.assertEqual(record["clip_sha256"], sha256_file(Path(voice["audio"])))
            self.assertTrue(record["unprompted_asr_matches"])
            self.assertGreater(record["clip_duration_seconds"], 3)
        self.assertEqual(provenance["voices"]["candidate_b"]["source_file"], "male_young_adlut_austrian.wav")
        self.assertIn("Wie ein kleiner König.", Path(self.episode["voices"]["examiner"]["transcript"]).read_text())


if __name__ == "__main__":
    unittest.main()
