"""Regression tests for in-place B2 answer markings and full pause retention."""

import copy
import re
import unittest

from audit_b2_sequence_r3 import compare_sequence
from compose_b2_r3 import scene_body, visual_plan
from prepare_b2 import EPISODE, read, schedule
from prepare_b2_r3 import plan


class B2InlineRevealTests(unittest.TestCase):
    def setUp(self):
        self.episode = read(EPISODE)
        self.planned = plan(self.episode)
        measured = {t["id"]: dict(**t, frames=48000, audio="fixture.wav", sha256="fixture")
                    for t in self.planned["turns"]}
        measured.update({k: dict(frames=12000, audio="cue.wav", sha256=k)
                         for k in ("chime_start", "chime_back", "chime_remove")})
        self.timeline = schedule(self.planned["events"], measured)
        self.content = {"episode": self.episode, "cards": self.planned["cards"]}

    def test_exact_pauses_and_two_complete_reveal_groups(self):
        self.assertTrue(compare_sequence(self.episode, self.timeline)["matches_requested_sequence"])
        self.assertEqual(len(self.timeline["events"]), 74)
        self.assertEqual([e["duration"] for e in self.timeline["events"] if e["kind"] == "silence"],
                         [30, 15, 60, 30, 15, 15, 15, 15, 15, 15])
        reveals = [e for e in self.timeline["events"] if e["part"] == 2 and e["kind"] == "reveal"]
        self.assertEqual([(e["duration"], e["reveal_group"]) for e in reveals], [(3, 1), (3, 2)])
        self.assertEqual(reveals[0]["end_frame"], reveals[1]["start_frame"])
        broken = copy.deepcopy(self.timeline)
        next(e for e in broken["events"] if e.get("reveal_group") == 2)["reveal_group"] = 1
        self.assertFalse(compare_sequence(self.episode, broken)["matches_requested_sequence"])

    def test_questions_remain_visible_and_keys_only_appear_in_reveal(self):
        for layout in ("landscape", "portrait"):
            for scene in visual_plan(self.timeline, layout):
                if scene["card"] not in self.content["cards"]:
                    continue
                body, _, classes = scene_body(scene, self.content, {})
                self.assertIn("statements", classes)
                self.assertNotIn("Deine Lösungen", body)
                self.assertNotIn("answer-board", body)
                questions = self.content["cards"][scene["card"]]["questions"]
                if scene.get("page"):
                    questions = questions[(scene["page"] - 1) * 5:scene["page"] * 5]
                self.assertEqual(re.findall(r'data-question="(\d+)"', body),
                                 [str(q["number"]) for q in questions])
                actual = re.findall(r'data-answer="([^"]+)"', body)
                keys = questions if scene["kind"] == "reveal" else []
                if layout == "landscape" and scene.get("reveal_group") == 1:
                    keys = keys[:5]
                self.assertEqual(actual, [f'{q["number"]}:{"richtig" if q["answer"] else "falsch"}'
                                          for q in keys])

    def test_portrait_reveal_pages_show_first_then_second_five(self):
        scenes = visual_plan(self.timeline, "portrait")
        reveals = [s for s in scenes if s["part"] == 2 and s["kind"] == "reveal"]
        self.assertEqual([s["page"] for s in reveals], [1, 2])
        self.assertEqual([s["duration"] for s in reveals], [3, 3])
        self.assertEqual(sum(s["end_frame"] - s["start_frame"] for s in scenes),
                         self.timeline["total_frames"])


if __name__ == "__main__":
    unittest.main()
