import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from listening_2d.preparation.prepare_fide import EPISODE, atomic_json, plan, read, schedule
from listening_2d.publishing.publication_assets import timestamp
from listening_2d.rendering.revise_fide_inline import BOOK_LINK, CUT_WORDS, SOURCE, compare_sequence, document, publish, revised_plan
from listening_2d.checks.review_fide_inline import frame_plan


class FideInlineTests(unittest.TestCase):
    def setUp(self):
        episode = read(EPISODE)
        self.source = plan(episode)
        for ident, count in CUT_WORDS.items():
            episode[ident] = " ".join(episode[ident].split()[:count])
        episode.pop("solutions_instruction")
        self.episode = episode
        self.revised = revised_plan(self.source, episode)
        measured = {t["id"]: {**t, "frames": 48000, "audio": "unused.wav",
                             "sha256": "fixture"} for t in self.revised["turns"]}
        self.timeline = schedule(self.revised["events"], measured)

    def test_every_answer_follows_complete_pause_with_two_second_hold(self):
        self.assertTrue(compare_sequence(self.timeline)["ok"])
        events = {e["id"]: e for e in self.timeline["events"]}
        for number in range(7, 19):
            self.assertEqual(events[f"solution_{number}"]["start"], events[f"answer_{number}"]["end"])
            self.assertEqual(events[f"solution_padding_{number}"]["duration"], 2)

    def test_wrong_b1_pause_or_early_reveal_is_rejected(self):
        for ident in ("answer_13", "answer_7"):
            changed = copy.deepcopy(self.timeline)
            next(e for e in changed["events"] if e["id"] == ident)["duration"] = 3
            with self.assertRaises(AssertionError):
                compare_sequence(changed)
        changed = copy.deepcopy(self.timeline)
        i = next(i for i, e in enumerate(changed["events"]) if e["id"] == "solution_8")
        changed["events"][i - 1], changed["events"][i] = changed["events"][i], changed["events"][i - 1]
        with self.assertRaises(AssertionError):
            compare_sequence(changed)

    def test_exercise_text_and_source_plan_are_unchanged(self):
        self.assertEqual(self.source["cards"], self.revised["cards"])
        original = {t["id"]: t for t in self.source["turns"]}
        for turn in self.revised["turns"]:
            if turn["id"] not in CUT_WORDS:
                self.assertEqual(turn, original[turn["id"]])
        self.assertIn("solutions_instruction", original)
        self.assertNotIn("solutions_instruction", {t["id"] for t in self.revised["turns"]})

    def test_review_includes_every_exact_response_reveal_and_hold_boundary(self):
        # The production frame planner also samples measured narration highlights.
        timeline = copy.deepcopy(self.timeline)
        for event in timeline["events"]:
            event["visible"] = False
        selected = {p["frame"] for p in frame_plan(timeline)}
        for event in timeline["events"]:
            if event["id"].startswith("solution_"):
                for frame in (event["start_frame"] - 1, event["start_frame"],
                              event["end_frame"] - 1, event["end_frame"]):
                    self.assertIn(frame, selected)

    def test_book_link_is_visible_beside_amazon_and_in_both_cta_phases(self):
        timeline = read(SOURCE / "timeline.json")
        content = read(SOURCE / "sample_content.json")
        for layout in ("landscape", "portrait"):
            result, _ = document((SOURCE / layout / "index.html").read_text(encoding="utf-8"),
                                 timeline, content)
            self.assertIn(f'class="amazon-url">{BOOK_LINK}</span>', result)
            self.assertEqual(result.count(f'class="cta-book-url">{BOOK_LINK}</span>'), 2)
            self.assertNotIn("Amazon: Link in der", result)

    def test_revised_captions_use_inline_answers_new_link_and_retimed_chapters(self):
        def covers_only(build, output):
            output.mkdir()
            atomic_json(output / "publication_manifest.json", {"inputs": {}, "assets": {}})

        with tempfile.TemporaryDirectory() as temporary, patch("listening_2d.publishing.publish_fide_assets.publish", covers_only):
            build = Path(temporary)
            output = build / "posts"
            content = read(SOURCE / "sample_content.json")
            content["episode"]["promotion"]["amazon_url"] = "https://" + BOOK_LINK
            atomic_json(build / "sample_content.json", content)
            atomic_json(build / "timeline.json", self.timeline)
            publish(build, output)
            events = {e["id"]: e for e in self.timeline["events"]}
            for platform in ("youtube", "tiktok", "instagram"):
                result = (output / f"{platform}.txt").read_text(encoding="utf-8")
                self.assertIn("Nach jeder Aufgabe folgt direkt die Lösung", result)
                self.assertIn(BOOK_LINK, result)
                self.assertNotIn("erst nach dem gesamten Test", result)
                self.assertNotIn("A2 · Lösungen", result)
                self.assertLessEqual(len(result), 5000 if platform == "youtube" else 2200)
                for number in range(7, 19):
                    self.assertIn(f'{timestamp(events[f"recording_{number}"]["start"])} · Aufgabe {number}', result)


if __name__ == "__main__":
    unittest.main()
