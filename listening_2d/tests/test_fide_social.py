import copy
import unittest
from pathlib import Path

from listening_2d.preparation.prepare_fide import read
from listening_2d.shorts.split_fide_social import (
    PAIRS, PREFIX_WORDS, SOURCE, compare_sequence, document, event_ids,
    frame_plan, prefix_info, segments, selected_timeline,
)


class FideSocialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = read(SOURCE / "timeline.json")
        cls.plan = read(SOURCE / "speech_plan.json")
        cls.manifest = read(SOURCE / "audio_manifest.json")
        turns = {t["id"]: t for t in cls.original["turns"]}
        for ident, count in PREFIX_WORDS.items():
            cls.manifest[ident] = prefix_info(cls.manifest[ident], turns[ident], count, Path(ident + ".wav"))
        cls.timelines = [selected_timeline(cls.original, cls.plan, cls.manifest, part)
                         for part in range(1, 7)]

    def test_all_twelve_tasks_once_with_complete_pauses_and_chimes(self):
        covered = []
        for timeline in self.timelines:
            covered.extend(compare_sequence(timeline, self.original)["numbers"])
        self.assertEqual(covered, list(range(7, 19)))
        self.assertTrue(all(t["total_frames"] < 4320 for t in self.timelines))

    def test_context_switches_precede_the_correct_task(self):
        for numbers, expected in (((9, 10), "context_a2_tram"), ((15, 16), "context_b1_nachbarn")):
            ids = event_ids(numbers)
            self.assertEqual(ids[ids.index(expected) + 1], f"question_{numbers[1]}")
            self.assertGreater(ids.index(expected), ids.index(f"solution_padding_{numbers[0]}"))

    def test_rejects_truncated_pause_reveal_or_task_omission(self):
        for ident in ("answer_7", "solution_chime_7", "solution_7"):
            altered = copy.deepcopy(self.timelines[0])
            next(e for e in altered["events"] if e["id"] == ident)["end_frame"] -= 1
            with self.assertRaises(AssertionError):
                compare_sequence(altered, self.original)
        altered = copy.deepcopy(self.timelines[0])
        altered["events"] = [e for e in altered["events"] if e["id"] != "recording_8"]
        with self.assertRaises(AssertionError):
            compare_sequence(altered, self.original)

    def test_sentence_prefixes_keep_real_word_mapping_without_three_part_claim(self):
        for ident, count in PREFIX_WORDS.items():
            info = self.manifest[ident]
            self.assertEqual(len(info["words"]), count)
            self.assertTrue(info["text"].endswith("."))
            self.assertNotIn("drei", info["text"].split())
            self.assertLess(info["words"][-1]["end"], info["wav_duration"])
        self.assertEqual(self.manifest["title"]["display_text"], "fide A2-B1 Verstehen")

    def test_native_markup_preserves_both_link_forms_and_scope(self):
        source_html = (SOURCE / "portrait" / "index.html").read_text(encoding="utf-8")
        for timeline in self.timelines:
            content = read(SOURCE / "sample_content.json")
            content["episode"]["title"] = "fide A2-B1 Verstehen"
            markup, _ = document(source_html, timeline, content)
            self.assertEqual(markup.count("Link in der Bio / Beschreibung"), 3)
            self.assertEqual(markup.count("amzn.eu/d/0dDgJ1ZT"), 3)
            self.assertIn(f"Video {timeline['part']}/6", markup)
            self.assertIn("Ausgewählte Aufgaben · 2 von 12", markup)
            self.assertNotIn("Sie hören drei", markup)
            self.assertNotIn("Prüfungssimulation", markup)

    def test_render_segments_and_review_cover_exact_native_and_answer_boundaries(self):
        for timeline in self.timelines:
            pieces = segments(timeline)
            self.assertEqual(pieces[0]["start_frame"], 0)
            self.assertEqual(pieces[-1]["end_frame"], timeline["total_frames"])
            self.assertTrue(all(a["end_frame"] == b["start_frame"] for a, b in zip(pieces, pieces[1:])))
            frames = {p["frame"] for p in frame_plan(timeline)}
            for event in timeline["events"]:
                if event["id"].startswith("solution_chime_"):
                    for frame in (event["start_frame"] - 1, event["start_frame"],
                                  event["end_frame"] - 1, event["end_frame"]):
                        self.assertIn(frame, frames)
            for piece in pieces:
                for frame in (piece["start_frame"] - 1, piece["start_frame"],
                              piece["end_frame"] - 1, piece["end_frame"]):
                    if 0 <= frame < timeline["total_frames"]:
                        self.assertIn(frame, frames)


if __name__ == "__main__":
    unittest.main()
