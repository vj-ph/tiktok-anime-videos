from pathlib import Path
import tempfile
import unittest

from PIL import Image

from a2_speaking_contacts import compose_panel, read_turns, review_panels
from long_speaking import FORMATS
from runtime_config import font_path


class A2SpeakingContactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.transcript = self.root / "transcript.md"
        self.turns = {number: {"label": "Lea", "text": f"Sentence {number}."}
                      for number in range(1, 56)}
        self.turns[9]["text"] = "Ich komme aus Warschau in Polen."
        self.turns[13]["text"] = "Zu Hause spreche ich meistens Polnisch."
        self.text = "\n\n".join(f"**{number:02d} · {turn['label']}**\n\n{turn['text']}"
                                for number, turn in self.turns.items())
        self.transcript.write_text(self.text, encoding="utf-8")

    def test_complete_transcript_and_approved_background_are_required(self):
        self.assertEqual(self.turns, read_turns(self.transcript))
        for text in (self.text.replace("**09 · Lea**", "**08 · Lea**"),
                     self.text + "\n\n**55 · Lea**\n\nDuplicate.",
                     self.text.replace("Warschau in Polen", "Berlin in Deutschland")):
            with self.subTest(text=text[-60:]):
                self.transcript.write_text(text, encoding="utf-8")
                with self.assertRaises(ValueError):
                    read_turns(self.transcript)

    def test_contact_and_role_questions_retain_their_transcript_sources(self):
        panels = {panel["id"]: panel for panel in review_panels(self.turns)}
        for key, number in (("contact_candidate_question", 19),
                            ("role_question_01", 33), ("role_question_02", 36)):
            self.assertEqual(self.turns[number]["text"], panels[key]["body"])
            self.assertEqual(number, panels[key]["source_turn"])
        self.assertLess(list(panels).index("picture_choice"),
                        list(panels).index("05_teil2_picture"))
        self.assertNotIn("Arzt", panels["picture_choice"]["heading"])
        self.assertNotIn("Arzt", panels["picture_choice"]["body"])

    def test_both_layouts_use_neutral_picture_choice_and_a2_stage_labels(self):
        if not font_path().is_file():
            self.skipTest("Project fonts not installed.")
        picture = self.root / "image.png"
        Image.new("RGB", (200, 300), "#507060").save(picture)
        visual = {
            "exam": {"family": "oeif", "level": "A2"}, "branding": "DEUTSCHKOMPASS",
            "parts": [{}, {"picture": str(picture)}, {}],
            "promotion": {
                "cover": str(picture), "pointing_emoji": str(picture),
                "book_title": "ÖIF A2 Sprechen",
                "youtube": "Amazon: Link in der Beschreibung",
                "social": "Amazon: Link in der Bio",
                "cta": ["Jetzt selbst sprechen!", "Mehr Aufgaben und Modelldialoge",
                        "im ÖIF-A2-Buch Sprechen."],
            },
        }
        selected = [panel for panel in review_panels(self.turns)
                    if panel["id"] in ("contact_card", "picture_choice",
                                       "role_card", "personal_card", "12_final_cta")]
        for mode, size in (("youtube", (1920, 1080)), ("social", (1080, 1920))):
            box = FORMATS[mode]["scene"]
            source = Image.new("RGB", (box[2] - box[0], box[3] - box[1]), "#507060")
            for panel in selected:
                with self.subTest(mode=mode, panel=panel["id"]):
                    image, check = compose_panel(visual, panel, mode, source, [picture] * 3)
                    self.assertEqual(size, image.size)
                    self.assertFalse(check.get("highlight"))
                    if panel["id"] == "12_final_cta":
                        continue
                    expected = ["S1", "S2A", "S2B"]
                    expected[panel["part"] - 1] += " AKTIV"
                    self.assertEqual(expected, check["a2_navigation"])
                    self.assertEqual(panel["source_turn"], check["source_turn"])
                    if panel["id"] == "picture_choice":
                        self.assertEqual([] if mode == "social" else ["1", "2", "3"],
                                         check["picture_choice_labels"])
                        self.assertFalse(check["picture_choice_topics_revealed"])

    def test_social_picture_choices_are_large_stacked_and_fully_inside_the_board(self):
        if not font_path().is_file():
            self.skipTest("Project fonts not installed.")
        from unittest.mock import patch
        pictures = []
        for index, color in enumerate(("#b04040", "#40b040", "#4040b0")):
            picture = self.root / f"picture{index}.png"
            Image.new("RGB", (1408, 768), color).save(picture)
            pictures.append(picture)
        native = Image.new("RGB", (836, 505))
        canvas = Image.new("RGB", (1080, 1920))
        panel = next(p for p in review_panels(self.turns) if p["id"] == "picture_choice")
        with patch("long_speaking.compose", return_value=(canvas, {"text": []})):
            image, check = compose_panel({}, panel, "social", native, pictures)
        self.assertEqual([], check["picture_choice_labels"])
        self.assertEqual("vertical", check["picture_choice_layout"])
        self.assertNotIn("1", [line for text in check["text"] for line in text["lines"]])
        board = check["picture_choice_board"]
        previous_bottom = board[1]
        for picture in check["picture_choice_images"]:
            x0, y0, x1, y1 = picture["box"]
            self.assertGreaterEqual(x0, board[0])
            self.assertLessEqual(x1, board[2])
            self.assertGreaterEqual(y0, previous_bottom)
            self.assertLessEqual(y1, board[3])
            self.assertGreaterEqual(x1 - x0, 480)
            self.assertGreaterEqual(y1 - y0, 260)
            with Image.open(picture["file"]) as original:
                self.assertEqual(original.getpixel((0, 0)),
                                 image.getpixel(((x0 + x1) // 2, (y0 + y1) // 2)))
            previous_bottom = y1


if __name__ == "__main__":
    unittest.main()
