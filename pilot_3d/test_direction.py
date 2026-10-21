import copy
import unittest

from scene_direction import blink_at, conversation_turn, envelope, gaze_at, performance_at, performance_plan
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

    def test_eyes_lead_without_snapping_or_excessive_head_relative_rotation(self):
        start = self.timeline["turns"][0]["start"]
        self.assertEqual(gaze_at(self.plan, "candidate_a", start), {"head": 0.0, "eyes": 0.0})
        lead = gaze_at(self.plan, "candidate_a", start + .12)
        self.assertGreater(lead["eyes"], lead["head"])
        for actor in ("candidate_a", "candidate_b", "examiner", "observer"):
            previous = gaze_at(self.plan, actor, 0)
            for frame in range(1, self.timeline["total_frames"]):
                current = gaze_at(self.plan, actor, frame / self.timeline["fps"])
                self.assertLessEqual(abs(current["eyes"] - current["head"]), .1600001)
                self.assertLess(abs(current["eyes"] - previous["eyes"]), .085)
                self.assertLess(abs(current["head"] - previous["head"]), .055)
                previous = current

    def test_attention_holds_during_partner_turns_and_gaps(self):
        for turn in self.timeline["turns"]:
            for actor, sign in (("candidate_a", 1), ("candidate_b", -1)):
                for seconds in (turn["end"], turn["end"] + .05):
                    self.assertAlmostEqual(gaze_at(self.plan, actor, seconds)["head"], sign * .48)

    def test_gaze_retargeting_is_continuous_even_with_rapid_interruptions(self):
        plan = {"attention": {"candidate_a": [
            {"start": 1, "yaw": .48}, {"start": 1.15, "yaw": 0},
            {"start": 1.22, "yaw": -.48}, {"start": 1.3, "yaw": .48},
        ]}}
        for event in plan["attention"]["candidate_a"]:
            before = gaze_at(plan, "candidate_a", event["start"] - .000001)
            after = gaze_at(plan, "candidate_a", event["start"] + .000001)
            for field in ("head", "eyes"):
                self.assertLess(abs(before[field] - after[field]), .00001)

    def test_gaze_does_not_depend_on_bake_step_or_sampling_history(self):
        actor = "candidate_a"
        for frame in range(0, self.timeline["total_frames"], 2):
            seconds = frame / self.timeline["fps"]
            sampled = gaze_at(self.plan, actor, seconds)
            gaze_at(self.plan, actor, seconds + .5)
            self.assertEqual(sampled, gaze_at(self.plan, actor, seconds))

    def test_blinks_reach_full_closure_on_both_bake_grids_and_have_varied_spacing(self):
        for actor, peaks in self.plan["blinks"].items():
            self.assertTrue(any(0 < peak < 4.7 for peak in peaks))
            for step in (1, 2):
                for peak in peaks:
                    seconds = round(peak * self.timeline["fps"] / step) * step / self.timeline["fps"]
                    self.assertAlmostEqual(blink_at(self.plan, actor, seconds, self.timeline["fps"], step), 1)
                    self.assertEqual(blink_at(self.plan, actor, seconds + .15, self.timeline["fps"], step), 0)
            spacings = {round(right - left, 2) for left, right in zip(peaks, peaks[1:])}
            self.assertGreater(len(spacings), 1)

    def test_listener_responses_finish_before_the_listener_speaks(self):
        responses = [event for event in self.plan["nods"] if event.get("kind") == "listener"]
        self.assertTrue(responses)
        for event in responses:
            turn_index = next(i for i, turn in enumerate(self.timeline["turns"]) if turn["id"] == event["turn_id"])
            following = self.timeline["turns"][turn_index + 1]
            self.assertEqual(event["actor"], following["speaker"])
            self.assertLessEqual(event["peak"] + .32, following["start"])
            self.assertLessEqual(event["amount"], .034)
            self.assertGreaterEqual(event["peak"] - .19, self.timeline["turns"][turn_index]["start"])

    def test_listener_does_not_acknowledge_every_turn_or_address_the_wrong_actor(self):
        timeline = copy.deepcopy(self.timeline)
        for turn in timeline["turns"]:
            turn["action"] = "propose"
        timeline["turns"] += [
            {**copy.deepcopy(turn), "id": turn["id"] + "-again",
             "start": turn["start"] + self.timeline["duration"],
             "end": turn["end"] + self.timeline["duration"]}
            for turn in self.timeline["turns"]
        ]
        timeline["duration"] *= 2
        plan = performance_plan(timeline)
        responses = [event for event in plan["nods"] if event.get("kind") == "listener"]
        self.assertGreater(len(responses), 0)
        self.assertLess(len(responses), len(timeline["turns"]) - 1)
        for turn in timeline["turns"]:
            turn["look_at"] = "examiner"
        plan = performance_plan(timeline)
        self.assertFalse(any(event.get("kind") == "listener" for event in plan["nods"]))

    def test_attention_returns_smoothly_to_examiner_without_losing_partner_gap_hold(self):
        timeline = copy.deepcopy(self.timeline)
        timeline["turns"][1]["speaker"] = "examiner"
        timeline["turns"][1]["look_at"] = "candidate_b"
        plan = performance_plan(timeline)
        first, instruction, last = timeline["turns"]
        self.assertAlmostEqual(gaze_at(plan, "candidate_a", first["end"] + .05)["head"], .48)
        self.assertAlmostEqual(gaze_at(plan, "candidate_a", instruction["start"] + .8)["head"], 0)
        self.assertAlmostEqual(gaze_at(plan, "candidate_b", instruction["start"] + .8)["head"], 0)
        self.assertAlmostEqual(gaze_at(plan, "examiner", instruction["start"] + .8)["head"], -.10)
        for event in plan["attention"]["candidate_a"]:
            before = gaze_at(plan, "candidate_a", event["start"] - .000001)
            after = gaze_at(plan, "candidate_a", event["start"] + .000001)
            self.assertLess(abs(before["eyes"] - after["eyes"]), .00001)
        self.assertAlmostEqual(gaze_at(plan, "candidate_a", last["end"])["head"], .48)

    def test_gesture_spacing_and_variation_are_bounded_and_not_identical(self):
        self.assertGreater(len({event["reach"] for event in self.plan["gestures"]}), 1)
        for turn in self.timeline["turns"]:
            events = [event for event in self.plan["gestures"] if event["turn_id"] == turn["id"]]
            self.assertLessEqual(len(events), 2 if turn["action"] in ("propose", "explain") else 1)
            for left, right in zip(events, events[1:]):
                self.assertGreaterEqual(right["peak"] - left["peak"], 2.15)


if __name__ == "__main__":
    unittest.main()
