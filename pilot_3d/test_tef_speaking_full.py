"""Complete TEF model coverage, long-form isolation and supplied promotion."""

import copy
from pathlib import Path
import unittest
from unittest.mock import patch

from PIL import Image, ImageChops

from episode_config import check_timeline
from social_captions import caption_pages
from tef_speaking_full import compile_episode, extract_dialogues
from tef_speaking_preview import compose, draw_words, notice_countdown
from test_tef_section_b import synthetic_timeline

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "episodes" / "tef_canada_mock1_full_preview.json"


class TefFullPreviewTests(unittest.TestCase):
    def test_both_model_dialogues_are_complete_and_verbatim(self):
        episode = compile_episode(CONFIG)
        source = Path(episode["source"]["book"]).read_text(encoding="utf-8")
        original = extract_dialogues(source, episode["source"]["exercise"])
        for section in ("A", "B"):
            actual = [t["text"] for t in episode["turns"]
                      if t.get("section") == section and t["kind"] == "model"]
            self.assertEqual(actual, [text for _, text in original[section]])
        self.assertEqual(len(episode["source"]["coverage"]), 48)
        self.assertEqual(episode["turns"][0]["text"], episode["title"])
        self.assertIn("expression orale et écrite", episode["turns"][-1]["text"])

    def test_missing_model_turn_is_rejected(self):
        episode = compile_episode(CONFIG)
        text = Path(episode["source"]["book"]).read_text(encoding="utf-8")
        text = text.replace("**Partner:** Elle est active dès sa remise et vous pouvez emprunter immédiatement.",
                            "", 1)
        with self.assertRaisesRegex(ValueError, "all 20 A and 28 B"):
            extract_dialogues(text, episode["source"]["exercise"])

    def test_long_form_duration_is_explicit_and_does_not_change_short_limit(self):
        episode = compile_episode(CONFIG)
        timeline = synthetic_timeline(episode)
        check_timeline(episode, timeline)
        self.assertGreater(timeline["duration"], 90)
        short = copy.deepcopy(episode)
        short["source"]["duration_limit_seconds"] = 90
        with self.assertRaisesRegex(ValueError, "strictly below"):
            check_timeline(short, timeline)

    def test_combined_cover_and_direct_amazon_url_stay_visible_in_both_sections_and_cta(self):
        episode = compile_episode(CONFIG)
        self.assertEqual(Path(episode["book_cover"]).name, "speaking_writing.jpg")
        self.assertEqual(episode["promotion"]["visible_url"], "a.co/d/01FdtRDW")
        self.assertEqual(episode["promotion"]["promotion"], "Livre disponible sur Amazon")
        without_hint = copy.deepcopy(episode)
        del without_hint["promotion"]["description_hint"]
        timeline = synthetic_timeline(episode)
        pages = caption_pages(episode, timeline)
        native = Image.new("RGB", (640, 320), "#617065")
        baseline = None
        for turn in timeline["turns"]:
            frame = turn["start_frame"] + 24
            image = compose(episode, timeline, pages, frame, native)
            panel = image.crop((704, 106, 928, 512)).tobytes()
            if baseline is None:
                baseline = panel
            self.assertEqual(panel, baseline)
        hinted = compose(episode, timeline, pages, 0, native)
        unhinted = compose(without_hint, timeline, pages, 0, native)
        changed = ImageChops.difference(hinted, unhinted).getbbox()
        self.assertIsNotNone(changed)
        self.assertGreaterEqual(changed[0], 720)
        self.assertLessEqual(changed[2], 928)
        self.assertGreaterEqual(changed[1], 449)
        self.assertLessEqual(changed[3], 476)

    def test_two_sections_are_spoken_and_shown_before_section_a(self):
        episode = compile_episode(CONFIG)
        setup = episode["turns"][1]
        self.assertEqual(setup["kind"], "setup")
        self.assertIn("comporte deux sections", setup["text"])
        self.assertLess(setup["text"].index("section A"), setup["text"].index("section B"))
        self.assertTrue(setup["text"].endswith("Commençons par la section A."))
        timeline = synthetic_timeline(episode)
        native = Image.new("RGB", (640, 320), "#617065")
        with patch("tef_speaking_preview.draw_words", wraps=draw_words) as draw:
            compose(episode, timeline, [], timeline["turns"][1]["start_frame"], native)
        texts = [" ".join(call.args[1]) for call in draw.call_args_list]
        for text in ("Deux sections", "A · Se renseigner", "B · Convaincre un ami"):
            self.assertIn(text, texts)

    def test_both_notice_countdowns_cover_only_the_complete_silent_pause(self):
        episode = compile_episode(CONFIG)
        timeline = synthetic_timeline(episode)
        pages = caption_pages(episode, timeline)
        native = Image.new("RGB", (640, 320), "#617065")
        for turn in timeline["turns"]:
            if turn.get("kind") != "notice":
                continue
            start, end = turn["end_frame"], turn["end_frame"] + 192
            self.assertIsNone(notice_countdown(turn, start - 1, 24))
            for second in range(8):
                self.assertEqual(notice_countdown(turn, start + second * 24, 24),
                                 (8 - second, (8 - second) / 8))
                self.assertEqual(notice_countdown(turn, start + second * 24 + 23, 24)[0], 8 - second)
            self.assertEqual(notice_countdown(turn, end - 1, 24), (1, 1 / 192))
            self.assertIsNone(notice_countdown(turn, end, 24))
            first = compose(episode, timeline, pages, start, native)
            last = compose(episode, timeline, pages, end - 1, native)
            self.assertEqual(first.crop((32, 106, 672, 426)).tobytes(),
                             last.crop((32, 106, 672, 426)).tobytes())
            self.assertEqual(first.getpixel((650, 497)), (244, 206, 114))
            self.assertEqual(last.getpixel((650, 497)), (56, 80, 90))
            self.assertEqual(last.getpixel((48, 497)), (244, 206, 114))
        self.assertIsNone(notice_countdown(timeline["turns"][1],
                                          timeline["turns"][1]["end_frame"], 24))


if __name__ == "__main__":
    unittest.main()
