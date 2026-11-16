import copy
import unittest

from audit_fide_sequence import compare_sequence
from compose_fide import scene_body
from prepare_fide import EPISODE, plan, read, schedule, validate_episode


class FideSequenceTests(unittest.TestCase):
    def setUp(self):
        self.episode = read(EPISODE)
        self.planned = plan(self.episode)
        self.measured = {
            turn["id"]: {**turn, "frames": 96001, "wav_duration": 96001 / 48000,
                         "sample_rate": 48000, "audio": turn["id"] + ".wav", "sha256": turn["id"]}
            for turn in self.planned["turns"]}
        self.timeline = schedule(self.planned["events"], self.measured)

    def test_complete_plan_passes_independent_sequence(self):
        result = compare_sequence(self.timeline)
        self.assertTrue(result["ok"], result["issues"])

    def test_shortened_pause_is_rejected(self):
        timeline = copy.deepcopy(self.timeline)
        event = next(e for e in timeline["events"] if e["id"] == "answer_18")
        event["end_frame"] -= 1
        self.assertFalse(compare_sequence(timeline)["ok"])

    def test_question_and_recording_cannot_swap(self):
        timeline = copy.deepcopy(self.timeline)
        first = next(i for i, e in enumerate(timeline["events"]) if e["id"] == "recording_13")
        timeline["events"][first:first + 2] = reversed(timeline["events"][first:first + 2])
        self.assertFalse(compare_sequence(timeline)["ok"])

    def test_repeated_question_must_reuse_whole_audio(self):
        timeline = copy.deepcopy(self.timeline)
        next(e for e in timeline["events"] if e["id"] == "repeat_question_7")["sha256"] = "different"
        self.assertFalse(compare_sequence(timeline)["ok"])

    def test_automatic_second_playback_is_rejected(self):
        timeline = copy.deepcopy(self.timeline)
        recording = copy.deepcopy(next(e for e in timeline["events"] if e["id"] == "recording_8"))
        timeline["events"].insert(10, recording)
        self.assertFalse(compare_sequence(timeline)["ok"])

    def test_question_subtitles_are_rejected(self):
        timeline = copy.deepcopy(self.timeline)
        next(e for e in timeline["events"] if e["id"] == "question_18")["visible"] = True
        self.assertFalse(compare_sequence(timeline)["ok"])

    def test_missing_transition_is_rejected(self):
        timeline = copy.deepcopy(self.timeline)
        timeline["events"] = [e for e in timeline["events"] if e["id"] != "transition"]
        self.assertFalse(compare_sequence(timeline)["ok"])

    def test_early_solution_is_rejected(self):
        timeline = copy.deepcopy(self.timeline)
        solution = next(e for e in timeline["events"] if e["id"] == "solution_7")
        timeline["events"].remove(solution)
        timeline["events"].insert(10, solution)
        self.assertFalse(compare_sequence(timeline)["ok"])

    def test_invalid_display_mapping_is_rejected(self):
        self.episode["transition"]["display_word_groups"][-1] = [999]
        with self.assertRaises(ValueError):
            validate_episode(self.episode)

    def test_oral_level_cannot_become_multiple_choice(self):
        self.episode["situations"][2]["items"][0]["options"] = ["A", "B", "C"]
        with self.assertRaises(ValueError):
            validate_episode(self.episode)

    def test_every_event_has_a_card_and_exam_items_hide_text(self):
        mappings = {
            turn["id"]: [{"index": i, "label": word}
                         for i, word in enumerate(turn.get("display_text", turn["text"]).split())]
            for turn in self.planned["turns"] if turn["visible"]}
        for event in self.planned["events"]:
            with self.subTest(event=event["id"]):
                body, heading = scene_body(event, self.episode, self.planned["cards"], mappings)
                self.assertTrue(body and heading)
                if event["card"].startswith("item_"):
                    item = self.planned["cards"][event["card"]]
                    self.assertNotIn(item["question"], body)
                    self.assertNotIn(item["recording"], body)
                    self.assertNotIn("data-answer=", body)
                    self.assertEqual(body.count('class="picture-option"'), 3 if item["level"] == "A2" else 0)


if __name__ == "__main__":
    unittest.main()
