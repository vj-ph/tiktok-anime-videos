import copy
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from prepare_full import plan
from prepare_sample import ROOT
from reduce_full import INTRO_FRAMES, NOTICE, SELECTIONS, compose, review_plan, selected_timeline, source_ranges
from revise_reduced import revised_document, revised_timeline, title_text
from trim_reduced_intro import retimed_document, shortened_timeline


class ReducedPracticeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.episode = json.loads((ROOT / "episodes" / "oeif_b1_listening_01.json").read_text(encoding="utf-8"))
        instructions = json.loads((ROOT / "instruction_templates.json").read_text(encoding="utf-8"))
        cls.source = plan(cls.episode, instructions)
        cursor = 0
        for event in cls.source["events"]:
            frames = event.get("seconds", 1) * 24
            event.update(start_frame=cursor, end_frame=cursor + frames,
                         start=cursor / 24, end=(cursor + frames) / 24, duration=frames / 24)
            cursor += frames

    def test_selected_pairs_numbering_and_all_original_pauses_remain(self):
        original = copy.deepcopy(self.source)
        expected_numbers = {1: [1, 2], 2: [5, 6], 3: [10, 11, 12, 13], 4: [18, 19]}
        for part, cards in SELECTIONS.items():
            timeline = selected_timeline(self.source, part)
            numbers = [q["number"] for name in cards for q in self.source["cards"][name]["questions"]]
            self.assertEqual(numbers, expected_numbers[part])
            originals = {event["id"]: event for event in self.source["events"]}
            for event in timeline["events"][1:]:
                source = originals[event["id"]]
                self.assertEqual(event["duration"], source["duration"])
                self.assertEqual(event["source_start_frame"], source["start_frame"])
            pauses = [event for event in timeline["events"] if event["kind"] == "silence"]
            if part == 4:
                self.assertEqual(pauses[1]["id"], "p4_statements_read")
                self.assertEqual(pauses[1]["duration"], 60)
            self.assertFalse(any("example" in e["id"] or e["id"].startswith("instruction_")
                                 or e["card"] == "end" for e in timeline["events"]))
            self.assertEqual(timeline["events"][-1]["id"], "cta")
            self.assertLess(timeline["duration"], 180)
        self.assertEqual(self.source, original)

    def test_no_missing_or_extra_video_frames_when_source_ranges_merge(self):
        for part in SELECTIONS:
            timeline = selected_timeline(self.source, part)
            ranges = source_ranges(timeline)
            self.assertEqual(sum(end - start for start, end in ranges) + INTRO_FRAMES,
                             timeline["total_frames"])
            self.assertEqual(len(ranges), 3 if part == 4 else 2)
            cursor = 0
            for event in timeline["events"]:
                self.assertEqual(event["start_frame"], cursor)
                cursor = event["end_frame"]

    def test_strict_duration_cap_rejects_long_source_without_shortening_it(self):
        source = copy.deepcopy(self.source)
        event = next(e for e in source["events"] if e["id"] == "p1_task_1_audio_1")
        event["end_frame"] += 180 * 24
        with self.assertRaisesRegex(ValueError, "strictly under"):
            selected_timeline(source, 1)

    def test_persistent_notice_and_only_dedicated_reveals_show_answers(self):
        for part in SELECTIONS:
            timeline = selected_timeline(self.source, part)
            cards = {name: self.source["cards"][name] for name in SELECTIONS[part]}
            if part == 4:
                cards["p4_statements"] = self.source["cards"]["p4_statements"]
            with tempfile.TemporaryDirectory() as directory:
                build = Path(directory)
                with patch("reduce_full.shutil.copyfile"), patch("reduce_full.sha256_file", return_value="test"):
                    compose(build, timeline, {"episode": self.episode, "cards": cards})
                document = (build / "portrait" / "index.html").read_text(encoding="utf-8")
                self.assertIn(f'<div id="reduced-notice">{NOTICE}</div>', document)
                self.assertIn("Amazon: Bio / Beschreibung", document)
                self.assertNotIn("20 Aufgaben", document)
                self.assertNotIn("{{", document)
                bodies = re.findall(r'<section .*?>(.*?)</section>', document, re.S)
                receipt = json.loads((build / "composition_receipt.json").read_text(encoding="utf-8"))
                for body, event in zip(bodies, receipt["scenes"]):
                    answers = re.findall(r'data-answer="([^"]+)"', body)
                    expected = ([q["answer"] for q in cards[event["card"]]["questions"]]
                                if event["kind"] == "reveal" else [])
                    self.assertEqual(answers, expected)

    def test_review_samples_every_answer_boundary_and_final_cta(self):
        for part in SELECTIONS:
            timeline = selected_timeline(self.source, part)
            frames = {item["frame"] for item in review_plan(timeline)}
            for event in timeline["events"]:
                if event["kind"] == "reveal":
                    self.assertIn(event["start_frame"] - 1, frames)
                    self.assertIn(event["start_frame"], frames)
            cta = timeline["events"][-1]
            self.assertIn((cta["start_frame"] + cta["end_frame"]) // 2, frames)


class RevisedReducedTests(unittest.TestCase):
    def test_only_opening_paragraphs_are_removed_and_mobile_styles_are_added(self):
        opening = ('<section id="scene-0"><h1>ÖIF B1 Hören<br>Teil 1</h1>'
                   '<p>Verkürzte Übung</p><p>Aufgaben 1–2<br>2 von 4 Aufgaben</p>'
                   '<p>Die ursprünglichen Lese- und Antwortpausen bleiben erhalten.</p></section>')
        rest = '<section id="scene-1"><h2>Aufgabe 1</h2><p>Unchanged task</p></section>'
        document = "  </style>" + opening + rest + "<footer>2 von 4</footer>"
        result = revised_document(document)
        first = result.split('<section id="scene-0">')[1].split("</section>")[0]
        self.assertIn("<p>Verkürzte Übung</p>", first)
        self.assertNotIn("Aufgaben", first)
        self.assertNotIn("bleiben erhalten", first)
        self.assertIn(rest + "<footer>2 von 4</footer>", result)
        self.assertIn("font-size: 48px", result)
        self.assertIn("font-size: 40px", result)
        with self.assertRaisesRegex(ValueError, "revision source"):
            revised_document(result)

    def test_voiced_intro_preserves_all_frames_and_non_intro_events(self):
        source = {"part": 1, "total_frames": 200, "duration": 200 / 24, "events": [
            {"id": "reduced_intro", "kind": "silence", "end_frame": INTRO_FRAMES},
            {"id": "question", "kind": "speech", "audio": "original.wav",
             "start_frame": INTRO_FRAMES, "end_frame": 200}]}
        before = copy.deepcopy(source)
        title = {"part": 1, "text": title_text(1), "frames": 100000, "sha256": "title"}
        revised = revised_timeline(source, Path("new_audio"), title)
        self.assertEqual(source, before)
        self.assertEqual(revised["events"][0]["kind"], "speech")
        self.assertEqual(revised["events"][0]["end_frame"], INTRO_FRAMES)
        self.assertEqual(revised["total_frames"], source["total_frames"])
        self.assertEqual(revised["duration"], source["duration"])
        revised["events"][1]["audio"] = source["events"][1]["audio"]
        self.assertEqual(revised["events"][1:], source["events"][1:])

    def test_wrong_section_or_oversized_speech_is_rejected_without_truncation(self):
        source = {"part": 2, "events": [{"kind": "silence", "end_frame": INTRO_FRAMES}]}
        title = {"part": 1, "text": title_text(1), "frames": 100000, "sha256": "title"}
        with self.assertRaisesRegex(ValueError, "binding"):
            revised_timeline(source, Path("audio"), title)
        title.update(part=2, text=title_text(2), frames=INTRO_FRAMES * 2000 + 1)
        with self.assertRaisesRegex(ValueError, "fit"):
            revised_timeline(source, Path("audio"), title)


class ShortenedIntroTests(unittest.TestCase):
    def source(self, samples):
        return {"part": 1, "total_frames": 200, "duration": 200 / 24, "events": [
            {"id": "reduced_intro", "card": "reduced_intro", "kind": "speech",
             "phase": "Start", "part": 1, "start_frame": 0, "end_frame": 144,
             "start": 0, "end": 6, "duration": 6, "seconds": 6,
             "audio_samples": samples, "audio": "old_title.wav"},
            {"id": "read", "card": "question", "kind": "silence", "phase": "Lesen",
             "part": 1, "start_frame": 144, "end_frame": 168,
             "start": 6, "end": 7, "duration": 1, "seconds": 1},
            {"id": "task", "card": "question", "kind": "speech", "phase": "Jetzt hören",
             "part": 1, "start_frame": 168, "end_frame": 200, "start": 7,
             "end": 200 / 24, "duration": 32 / 24, "audio": "old_task.wav"}]}

    def test_padding_rounds_up_without_changing_later_durations_or_source(self):
        for samples, frames in ((143108, 84), (133502, 79), (133600, 79),
                                (143270, 84), (144000, 84), (144001, 85)):
            original = self.source(samples)
            before = copy.deepcopy(original)
            result = shortened_timeline(original, Path("new_audio"))
            self.assertEqual(original, before)
            self.assertEqual(result["events"][0]["end_frame"], frames)
            self.assertGreaterEqual(frames * 2000 - samples, 24000)
            self.assertLess(frames * 2000 - samples, 26000)
            self.assertEqual(result["events"][1]["start_frame"], frames)
            for old, new in zip(original["events"][1:], result["events"][1:]):
                self.assertEqual(old["duration"], new["duration"])
                self.assertEqual(old["end_frame"] - old["start_frame"],
                                 new["end_frame"] - new["start_frame"])
            self.assertEqual(result["total_frames"], 200 - (144 - frames))
        with self.assertRaisesRegex(ValueError, "shorten"):
            shortened_timeline(self.source(288000), Path("new_audio"))

    def test_browser_scene_clock_audio_and_countdown_move_together(self):
        original = self.source(143108)
        timeline = shortened_timeline(original, Path("new_audio"))
        document = (
            '<div id="root" data-start="0" data-duration="8.333333333333334">'
            '<section id="scene-0" data-start="0" data-duration="6">Intro</section>'
            '<section id="scene-1" data-start="6" data-duration="1">Question</section>'
            '<section id="scene-2" data-start="7" data-duration="1.3333333333333333">Audio</section>'
            '<audio id="sample-audio" data-start="0" data-duration="8.333333333333334">'
            'tl.to(clock, { value: 8.333333333333334, duration: 8.333333333333334 }, 0);'
            'const pauses = [{"index": 1, "start": 6, "duration": 1}];')
        result = retimed_document(document, original, timeline)
        self.assertIn('data-start="3.5" data-duration="1"', result)
        self.assertIn('data-start="4.5" data-duration="1.3333333333333333"', result)
        self.assertIn('"index": 1, "start": 3.5, "duration": 1', result)
        self.assertEqual(result.count('data-duration="5.833333333333333"'), 2)
        self.assertIn('value: 5.833333333333333, duration: 5.833333333333333', result)
        self.assertIn(">Question</section>", result)


if __name__ == "__main__":
    unittest.main()
