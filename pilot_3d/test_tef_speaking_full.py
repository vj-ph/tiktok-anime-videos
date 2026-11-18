"""Complete TEF model coverage, long-form isolation and supplied promotion."""

import copy
from pathlib import Path
import unittest

from PIL import Image

from episode_config import check_timeline
from social_captions import caption_pages
from tef_speaking_full import compile_episode, extract_dialogues
from tef_speaking_preview import compose
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


if __name__ == "__main__":
    unittest.main()
