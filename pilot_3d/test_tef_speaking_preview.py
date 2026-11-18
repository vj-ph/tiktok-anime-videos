"""Focused tests for the separate landscape TEF A+B rehearsal."""

import copy
from pathlib import Path
import unittest

from PIL import Image

from episode_config import check_timeline, validate_template
from tef_speaking_preview import active_on_frame, compose, current_turn, load_preview
from test_tef_section_b import synthetic_timeline
from social_captions import caption_pages

ROOT = Path(__file__).resolve().parent
EPISODE = ROOT / "episodes" / "tef_canada_mock1_youtube_preview.json"


class TefLandscapePreviewTests(unittest.TestCase):
    def test_subframe_word_uses_measured_overlap_without_extending_alignment(self):
        words = [{"word": "B", "start": 2.938, "end": 2.958}]
        before = copy.deepcopy(words)
        self.assertEqual(active_on_frame(words, 0, 70, 24), 0)
        self.assertIsNone(active_on_frame(words, 0, 69, 24))
        self.assertIsNone(active_on_frame(words, 0, 71, 24))
        self.assertEqual(words, before)

    def test_both_sections_and_complete_spoken_title_validate_without_changing_short_defaults(self):
        episode = load_preview(EPISODE)
        validate_template(episode)
        timeline = synthetic_timeline(episode)
        check_timeline(episode, timeline)
        timeline["total_frames"] = 2160
        with self.assertRaisesRegex(ValueError, "strictly below"):
            check_timeline(episode, timeline)
        from episode_config import PROFILES
        self.assertEqual((PROFILES["preview"]["width"], PROFILES["preview"]["height"]), (360, 640))

    def test_section_change_occurs_on_the_exact_authored_frame(self):
        episode = load_preview(EPISODE)
        timeline = synthetic_timeline(episode)
        turn = timeline["turns"][4]
        self.assertEqual(current_turn(timeline, turn["start_frame"] - 1)["section"], "A")
        self.assertEqual(current_turn(timeline, turn["start_frame"])["section"], "B")

    def test_landscape_layout_fits_all_words_and_keeps_book_panel_unchanged(self):
        episode = load_preview(EPISODE)
        timeline = synthetic_timeline(episode)
        pages = caption_pages(episode, timeline)
        native = Image.new("RGB", (640, 320), "#617065")
        baseline = None
        for turn in timeline["turns"]:
            for word in turn["words"]:
                frame = turn["start_frame"] + round((word["start"] + word["end"]) * 12)
                image = compose(episode, timeline, pages, frame, native)
                self.assertEqual(image.size, (960, 540))
                panel = image.crop((704, 106, 928, 512)).tobytes()
                if baseline is None:
                    baseline = panel
                self.assertEqual(panel, baseline)
        with self.assertRaisesRegex(ValueError, "native landscape"):
            compose(episode, timeline, pages, 0, Image.new("RGB", (360, 640)))


if __name__ == "__main__":
    unittest.main()
