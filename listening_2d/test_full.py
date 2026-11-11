import copy
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

from compose_full import card_body, compose, visual_events
from compose_sample import instruction_intervals
from prepare_full import plan, ROOT
from validate_full import check_structure
from review_full import review as review_audio
from review_full_frames import frame_plan
from prepare_sample import sha256_file


class FullPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.episode = json.loads((ROOT / "episodes" / "oeif_b1_listening_01.json").read_text(encoding="utf-8"))
        cls.instructions = json.loads((ROOT / "instruction_templates.json").read_text(encoding="utf-8"))
        cls.plan = plan(cls.episode, cls.instructions)

    def test_each_task_and_example_has_complete_pause_then_reveal(self):
        events = self.plan["events"]
        for card, question in self.plan["cards"].items():
            if card == "p4_statements":
                continue
            part = question["part"]
            number = next((q.get("number") for q in question["questions"]), None)
            example = "example" in card
            expected_pre = (1 if part == 4 else 10) if example else (
                12 if part == 1 else 10 if part == 2 else
                (10 if number == 10 else 12) if part == 3 else 1)
            expected_post = 10 if example and part in (1, 3) else 12
            reading = next(e for e in events if e["id"] == card + "_read")
            answer = next(e for e in events if e["id"] == card + "_answer")
            self.assertEqual(reading["seconds"], expected_pre, card)
            self.assertEqual(answer["seconds"], expected_post, card)
            following = events[events.index(answer) + 1]
            self.assertEqual((following["kind"], following["card"], following["seconds"],
                              following["audio_id"]), ("reveal", card, 3, "chime_remove"))
        minute = next(e for e in events if e["id"] == "p4_statements_read")
        self.assertEqual(minute["seconds"], 60)
        self.assertEqual(events[events.index(minute) - 1]["id"], "instruction_4")

    def test_complete_numbering_keys_and_chime_cue_order(self):
        events, cards = self.plan["events"], self.plan["cards"]
        numbers = [q["number"] for card in cards.values() for q in card["questions"] if "number" in q]
        self.assertEqual(sorted(numbers), list(range(1, 21)))
        self.assertEqual(len([card for card in cards if "example" in card]), 3)
        for kind in ("turns", "events"):
            ids = [item["id"] for item in self.plan[kind]]
            self.assertEqual(len(ids), len(set(ids)))
        for index, event in enumerate(events):
            if event["kind"] == "chime" and event["id"] != "back_at_end":
                following = events[index + 1]
                self.assertEqual(following["kind"], "speech")
                self.assertTrue(following["id"].startswith(("cue_", "example_cue_")))
        actual = {str(q["number"]): q["answer"] for card in cards.values()
                  for q in card["questions"] if "number" in q}
        self.assertEqual(actual, self.episode["review"]["answer_key"])

    def test_pair_and_matching_keys_are_hidden_until_dedicated_reveal(self):
        for name in ("p3_task_10_11", "p3_example", "p4_task_18", "p4_statements"):
            card = self.plan["cards"][name]
            hidden = card_body(card)
            self.assertNotIn('option correct', hidden)
            self.assertNotIn('data-answer', hidden)
            self.assertNotIn('Richtige Antwort', hidden)
            if name == "p4_statements":
                self.assertEqual(hidden.count('class="option"'), 6)
                continue
            visible = card_body(card, reveal=True)
            self.assertEqual(re.findall(r'data-answer="([^"]+)"', visible),
                             [q["answer"] for q in card["questions"]])
            self.assertEqual(visible.count('class="solution"'), 1)

    def test_composition_covers_all_events_and_only_merges_contiguous_dialogue(self):
        measured = copy.deepcopy(self.plan["events"])
        for index, event in enumerate(measured):
            event.update(start=index, end=index + 1, duration=1,
                         start_frame=index * 24, end_frame=(index + 1) * 24)
        scenes = visual_events(measured)
        self.assertEqual([ident for scene in scenes for ident in scene["event_ids"]],
                         [event["id"] for event in measured])
        self.assertEqual(scenes[-1]["end_frame"], measured[-1]["end_frame"])
        for scene in scenes:
            if len(scene["event_ids"]) > 1:
                self.assertEqual(scene["kind"], "speech")
            self.assertEqual(scene["duration"], len(scene["event_ids"]))
        self.assertLess(len(scenes), len(measured))

    def test_independent_validator_rejects_shortened_pause_or_early_reveal(self):
        events = copy.deepcopy(self.plan["events"])
        cursor = 0
        for event in events:
            duration = event.get("seconds", 1)
            event.update(start=cursor, end=cursor + duration, duration=duration,
                         start_frame=cursor * 24, end_frame=(cursor + duration) * 24)
            cursor += duration
        content = {"cards": self.plan["cards"], "episode": self.episode}
        check_structure({"events": events}, content)
        shortened = copy.deepcopy(events)
        next(e for e in shortened if e["id"] == "p3_task_10_11_read")["duration"] = 12
        with self.assertRaises(AssertionError):
            check_structure({"events": shortened}, content)
        early = copy.deepcopy(events)
        index = next(i for i, e in enumerate(early) if e["id"] == "p4_task_18_answer")
        early[index], early[index + 1] = early[index + 1], early[index]
        with self.assertRaises(AssertionError):
            check_structure({"events": early}, content)

    def test_full_generated_layouts_have_all_cards_without_preview_or_removed_lines(self):
        measured = copy.deepcopy(self.plan["events"])
        for index, event in enumerate(measured):
            event.update(start=index, end=index + 1, duration=1,
                         start_frame=index * 24, end_frame=(index + 1) * 24)
        title = [{"index": i, "label": label, "start": 0, "end": 1}
                 for i, label in enumerate(["ÖIF", "B1", "Hören", "Unabhängige", "Prüfungssimulation"])]
        with tempfile.TemporaryDirectory() as directory:
            build = Path(directory)
            (build / "timeline.json").write_text(json.dumps({
                "scope": "full", "duration": len(measured), "events": measured}), encoding="utf-8")
            (build / "sample_content.json").write_text(json.dumps({
                "episode": self.episode, "instructions": self.instructions,
                "cards": self.plan["cards"]}), encoding="utf-8")
            with patch("compose_full.shutil.copyfile"), patch("compose_full.sha256_file", return_value="test"), \
                    patch("compose_full.title_intervals", return_value=title), \
                    patch("compose_full.instruction_intervals", return_value=[
                        {"index": 0, "label": "Hören", "start": 1, "end": 2}]):
                compose(build)
            for layout in ("landscape", "portrait"):
                document = (build / layout / "index.html").read_text(encoding="utf-8")
                for forbidden in ("VORSCHAU", "Geführte Hörübung", "Lösungen nach jeder Aufgabe",
                                  "von Deutsch Kompass", "{{"):
                    self.assertNotIn(forbidden, document)
                for part in range(1, 5):
                    self.assertIn(f'id="instruction-{part}-word-0"', document)
                self.assertIn('class="answer-grid"', document)
                self.assertEqual(document.count('class="answer-cell"'), 40)

    def test_review_frames_cover_every_reading_card_and_exact_reveal_boundary(self):
        events = copy.deepcopy(self.plan["events"])
        cursor = 0
        for event in events:
            duration = event.get("seconds", 1)
            event.update(start=cursor, end=cursor + duration, duration=duration,
                         start_frame=cursor * 24, end_frame=(cursor + duration) * 24)
            cursor += duration
        turns = [{"id": event["id"], "start": event["start"],
                  "words": [{"start": 0.2, "end": 0.6}]}
                 for event in events if event["id"] == "title" or event["id"].startswith("instruction_")]
        frames = frame_plan({"events": events, "turns": turns, "total_frames": cursor * 24})
        labels = [label for frame in frames for label in frame["labels"]]
        for event in events:
            if event["kind"] == "silence" and event["phase"] == "Lesen":
                self.assertIn(event["card"] + " reading", labels)
        answer = next(event for event in events if event["id"] == "p1_task_1_answer")
        first_reveal = next(frame for frame in frames if "task 1 first reveal frame" in frame["labels"])
        self.assertEqual(first_reveal["frame"], answer["end_frame"])

    def test_verified_asr_reuse_retains_disagreement_and_rejects_changed_input(self):
        with tempfile.TemporaryDirectory() as directory:
            build = Path(directory)
            source = build / "source"
            source.mkdir()
            audio = build / "speech.wav"
            audio.write_bytes(b"verified audio fixture")
            digest = sha256_file(audio)
            (build / "input_pin.json").write_text(json.dumps({"sample_build": str(source)}))
            (build / "audio_manifest.json").write_text(json.dumps({
                "instruction_1": {"audio": str(audio), "sha256": digest}}))
            (build / "timeline.json").write_text(json.dumps({"turns": [{
                "id": "instruction_1", "text": "Hören Sie bitte.", "start": 10, "end": 12,
                "speaker": "narrator"}]}))
            (source / "speech_review.json").write_text(json.dumps({
                "model": "faster-whisper-small", "turns": [{
                    "expected": "Hören Sie bitte.", "recognized": "Hören Sie.",
                    "audio_sha256": digest}]}))
            with patch.dict(sys.modules, {"faster_whisper": None}):
                review_audio(build)
                report = json.loads((build / "speech_review.json").read_text())
                self.assertTrue(report["complete"])
                self.assertTrue(report["turns"][0]["reused_verified_asr"])
                self.assertFalse(report["turns"][0]["matches"])
                self.assertEqual(report["turns"][0]["start"], 10)
                audio.write_bytes(b"changed audio")
                with self.assertRaisesRegex(ValueError, "Changed ASR input"):
                    review_audio(build)


class FullHighlightTests(unittest.TestCase):
    def test_instruction_identity_and_absolute_timing_are_part_specific(self):
        timeline = {"turns": [{"id": "instruction_4", "start": 123.5,
                    "wav_duration": 1, "text": "Hören.",
                    "words": [{"word": "Hören.", "start": 0.12, "end": 0.81, "score": 0.9}]}]}
        result = instruction_intervals(timeline, "Hören.", "instruction_4")
        self.assertEqual(result[0]["start"], 123.62)
        with self.assertRaisesRegex(ValueError, "differs"):
            instruction_intervals(timeline, "Lesen.", "instruction_4")


if __name__ == "__main__":
    unittest.main()
