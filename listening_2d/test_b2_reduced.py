import copy
import html
from pathlib import Path
import re
import tempfile
import unittest

from compose_b2_reduced import document_for
from deliver_b2_reduced import independent_sequence
from prepare_b2 import EPISODE, plan, read, schedule
from prepare_b2_reduced import READING_TEXT, SELECTIONS, TOTALS, planned_events, title_text
from prepare_sample import atomic_json


class B2ReducedTests(unittest.TestCase):
    def setUp(self):
        self.episode = read(EPISODE)
        self.source = plan(self.episode)
        self.original = {"events": self.source["events"]}

    def timeline(self, part, title_samples=130001):
        events = planned_events(part, self.original, title_samples)
        measured = {}
        for event in events:
            if "audio_id" in event:
                ident = event["audio_id"]
                measured[ident] = dict(
                    audio=f"{ident}.wav", sha256="fixture", frames=title_samples if ident == "reduced_intro" else 48000,
                    text=READING_TEXT if ident == "reading_instruction" else title_text(part)
                    if ident == "reduced_intro" else ident, speaker="narrator",
                )
        timeline = schedule(events, measured)
        timeline.update(part=part, selected_numbers=SELECTIONS[part])
        return timeline

    def test_selected_complete_recordings_and_independent_pause_contract(self):
        expected_speech = {
            1: ["reduced_intro", "reading_instruction", "news_theatre", "news_corrections", "cta"],
            2: ["reduced_intro", "reading_instruction", "interview_q49", "interview_49", "cta"],
            3: ["reduced_intro", "b2_p3_parcel_cue", "short_56", "b2_p3_stage_cue", "short_57", "cta"],
        }
        for part in (1, 2, 3):
            with self.subTest(part=part):
                timeline = self.timeline(part)
                independent_sequence(part, timeline)
                self.assertEqual([e["id"] for e in timeline["events"] if e["kind"] == "speech"],
                                 expected_speech[part])
                self.assertNotIn("news_intro", [e["id"] for e in timeline["events"]])
                self.assertNotIn("checking_instruction", [e["id"] for e in timeline["events"]])
                self.assertTrue(all(e["kind"] != "reveal" or e["duration"] == 3 for e in timeline["events"]))

    def test_reading_instruction_finishes_before_fifteen_silent_seconds(self):
        for part in (1, 2):
            timeline = self.timeline(part)
            cue, reading, chime = timeline["events"][1:4]
            self.assertEqual(cue["text"], READING_TEXT)
            self.assertEqual(cue["end_frame"], reading["start_frame"])
            self.assertEqual(reading["end_frame"] - reading["start_frame"], 360)
            self.assertEqual(reading["end_frame"], chime["start_frame"])
            broken = copy.deepcopy(timeline)
            broken["events"][2]["duration"] = 10
            with self.assertRaises(AssertionError):
                independent_sequence(part, broken)
        self.assertNotIn("reading_instruction", [e["id"] for e in self.timeline(3)["events"]])

    def test_complete_title_plus_half_second_rounded_up(self):
        for samples in (16000, 130001, 144000):
            event = self.timeline(1, samples)["events"][0]
            self.assertGreaterEqual(event["end_frame"] * 2000 - samples, 24000)
            self.assertLess(event["end_frame"] * 2000 - samples, 26000)

    def test_native_boards_keep_original_selected_questions_and_only_reveal_selected_keys(self):
        for part in (1, 2, 3):
            with tempfile.TemporaryDirectory() as temporary:
                clip = Path(temporary)
                timeline = self.timeline(part)
                used = {e["card"] for e in timeline["events"]}
                cards = copy.deepcopy(self.source["cards"])
                cards = {key: value for key, value in cards.items() if key in used}
                for card in cards.values():
                    card["questions"] = [q for q in card["questions"] if q["number"] in SELECTIONS[part]]
                atomic_json(clip / "timeline.json", timeline)
                atomic_json(clip / "sample_content.json", {"episode": self.episode, "cards": cards})
                document, scenes = document_for(clip)
                bodies = re.findall(r'<section id="scene-\d+"[^>]*>(.*?)</section>', document, re.S)
                self.assertEqual(len(bodies), len(scenes))
                for scene, body in zip(scenes, bodies):
                    questions = cards.get(scene["card"], {}).get("questions", [])
                    self.assertEqual(
                        [html.unescape(s) for s in re.findall(r'class="statement-text">([^<]+)</span>', body)],
                        [q["question"] for q in questions])
                    keys = [f'{q["number"]}:{"richtig" if q["answer"] else "falsch"}'
                            for q in questions] if scene["kind"] == "reveal" else []
                    self.assertEqual(re.findall(r'data-answer="([^"]+)"', body), keys)
                    self.assertNotIn("answer-board", body)
                self.assertIn(f"{len(SELECTIONS[part])} von {TOTALS[part]}", document)
                self.assertIn("Verkürzte Übung · Ausgewählte Aufgaben", document)


if __name__ == "__main__":
    unittest.main()
