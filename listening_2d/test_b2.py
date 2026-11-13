"""Focused B2 tests for the new sequence and full-interview paging."""

import copy
import unittest

from audit_b2_sequence import compare_sequence
from compose_b2 import visual_plan
from prepare_b2 import EPISODE, plan, read, schedule


class B2SequenceTests(unittest.TestCase):
    def setUp(self):
        self.episode = read(EPISODE)
        self.plan = plan(self.episode)
        self.measured = {
            t["id"]: dict(**t, frames=48000, audio="fixture.wav", sha256="fixture")
            for t in self.plan["turns"]}
        self.measured.update({key: dict(frames=12000, audio="cue.wav", sha256=key)
                              for key in ("chime_start", "chime_back", "chime_remove")})
        self.timeline = schedule(self.plan["events"], self.measured)

    def test_planner_matches_independent_user_sequence(self):
        self.assertTrue(compare_sequence(self.episode, self.timeline)["matches_requested_sequence"])
        self.assertEqual(len([e for e in self.timeline["events"] if e["kind"] == "reveal"]), 7)
        self.assertEqual([e["duration"] for e in self.timeline["events"]
                          if e["kind"] == "silence"], [30, 15, 60, 30, 15, 15, 15, 15, 15, 15])

    def test_wrong_pause_chime_and_early_reveal_fail(self):
        for mutation in ("pause", "chime", "reveal"):
            with self.subTest(mutation=mutation):
                planned = copy.deepcopy(self.plan["events"])
                if mutation == "pause":
                    next(e for e in planned if e["id"] == "part_2_read")["seconds"] = 59
                elif mutation == "chime":
                    next(e for e in planned if e["id"] == "part_1_start")["audio_id"] = "chime_back"
                else:
                    index = next(i for i, e in enumerate(planned) if e["kind"] == "reveal")
                    planned[index - 1:index + 1] = reversed(planned[index - 1:index + 1])
                timeline = schedule(planned, self.measured)
                self.assertFalse(compare_sequence(self.episode, timeline)["matches_requested_sequence"])

    def test_teil_3_has_no_invented_initial_read_or_chime(self):
        events = [e for e in self.timeline["events"] if e["part"] == 3]
        self.assertEqual([e["id"] for e in events[:3]],
                         ["instruction_3", "b2_p3_parcel_cue", "short_56"])
        self.assertEqual([e["kind"] for e in events[-4:]], ["silence", "reveal", "chime", "speech"])
        self.assertEqual(events[-1]["text"], "Ende des Subtests Hören.")

    def test_portrait_pages_preserve_audio_and_complete_pause_clocks(self):
        events = visual_plan(self.timeline, "portrait")
        for ident, expected in (("part_2_read", [30, 30]), ("b2_p2_learning_answer", [15, 15])):
            pages = [e for e in events if e["id"] == ident]
            self.assertEqual([e["duration"] for e in pages], expected)
            self.assertEqual([e["page"] for e in pages], [1, 2])
            self.assertEqual(pages[0]["end_frame"], pages[1]["start_frame"])
        switch = next(e["start_frame"] for e in self.timeline["events"] if e["id"] == "interview_q51")
        second = next(e for e in events if e["card"] == "b2_p2_learning"
                      and e["kind"] == "speech" and e.get("page") == 2)
        self.assertEqual(second["start_frame"], switch)
        self.assertEqual(sum(e["end_frame"] - e["start_frame"] for e in events),
                         self.timeline["total_frames"])
        reveal = next(e for e in events if e["id"] == "b2_p2_learning_reveal")
        self.assertNotIn("page", reveal)
        self.assertEqual(reveal["duration"], 3)

    def test_landscape_does_not_paginate_the_interview(self):
        events = visual_plan(self.timeline, "landscape")
        self.assertTrue(all("page" not in e for e in events))
        reading = [e for e in events if e["id"] == "part_2_read"]
        self.assertEqual(len(reading), 1)
        self.assertEqual(reading[0]["duration"], 60)


if __name__ == "__main__":
    unittest.main()
