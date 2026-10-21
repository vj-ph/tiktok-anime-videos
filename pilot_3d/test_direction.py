import copy
import unittest

from scene_direction import conversation_turn, envelope, performance_at, performance_plan
from test_episode_config import clock, example


class DirectionTests(unittest.TestCase):
    def setUp(self):
        self.timeline = clock(example())
        self.plan = performance_plan(self.timeline)

    def test_envelope_anticipates_holds_and_releases_without_jumps(self):
        self.assertEqual(envelope(0, 2), 0)
        self.assertAlmostEqual(envelope(1.65, 2), 0)
        self.assertEqual(envelope(2, 2), 1)
        self.assertEqual(envelope(2.1, 2), 1)
        self.assertEqual(envelope(2.8, 2), 0)
        for boundary in (1.65, 2, 2.1, 2.75):
            self.assertLess(abs(envelope(boundary - .001, 2) - envelope(boundary + .001, 2)), .0001)

    def test_gestures_follow_measured_content_words_and_vary_hands(self):
        self.assertTrue(self.plan["gestures"])
        observed = set()
        for gesture in self.plan["gestures"]:
            turn = next(t for t in self.timeline["turns"] if t["id"] == gesture["turn_id"])
            focus = next(w for w in turn["words"] if
                         abs(turn["start"] + (w["start"] + w["end"]) / 2 - gesture["peak"]) < .000001)
            self.assertEqual(focus["word"], gesture["word"])
            observed.add(gesture["hand"])
            at_peak = performance_at(self.plan, gesture["actor"], gesture["peak"])
            self.assertGreater(at_peak["hands"][gesture["hand"]], .4)
        self.assertEqual(observed, {"L", "R"})

    def test_attention_survives_silent_turn_gaps(self):
        for turn in self.timeline["turns"][:-1]:
            self.assertIs(conversation_turn(self.timeline, turn["end"] + .05), turn)
        self.assertIsNone(conversation_turn(self.timeline, 0))

    def test_agreement_nod_and_listener_response_are_timed_not_periodic(self):
        final = self.timeline["turns"][-1]
        nods = [n for n in self.plan["nods"] if n["actor"] == final["speaker"]]
        self.assertTrue(any(final["start"] < n["peak"] < final["end"] for n in nods))
        self.assertGreater(performance_at(self.plan, nods[0]["actor"], nods[0]["peak"])["nod"], 0)
        resting = performance_at(self.plan, final["speaker"], self.timeline["duration"] - 1)
        self.assertEqual(resting["accent"], 0)
        self.assertEqual(resting["nod"], 0)

    def test_direction_is_deterministic_and_independent_of_frame_sampling(self):
        self.assertEqual(performance_plan(self.timeline), self.plan)
        full_rate = copy.deepcopy(self.timeline)
        full_rate["fps"] *= 2
        full_rate["total_frames"] *= 2
        for turn in full_rate["turns"]:
            turn["start_frame"] *= 2
            turn["end_frame"] *= 2
        self.assertEqual(performance_plan(full_rate), self.plan)


if __name__ == "__main__":
    unittest.main()
