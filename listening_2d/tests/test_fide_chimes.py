import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from listening_2d.preparation.prepare_fide import atomic_json, read, schedule
from listening_2d.publishing.publication_assets import timestamp
from listening_2d.checks.review_fide_inline import frame_plan
from listening_2d.rendering.revise_fide_chimes import CHIME_SOURCE, CUES, SOURCE, compare_sequence, document, publish, revised_plan


class FideChimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = read(SOURCE / "timeline.json")
        cls.plan = revised_plan(read(SOURCE / "speech_plan.json"))
        cls.manifest = read(SOURCE / "audio_manifest.json")
        cls.chime = {**read(CHIME_SOURCE)["chime_remove"], "text": "", "speaker": "sfx"}
        cls.manifest["chime_remove"] = cls.chime
        cls.timeline = schedule(cls.plan["events"], cls.manifest)
        originals = {t["id"]: t for t in cls.original["turns"]}
        for turn in cls.timeline["turns"]:
            if turn["visible"]:
                turn.update(words=originals[turn["id"]]["words"],
                            alignment_key=originals[turn["id"]]["alignment_key"])

    def test_complete_chimes_follow_full_pauses_and_precede_unchanged_tts(self):
        report = compare_sequence(self.timeline, self.original, self.chime["frames"])
        self.assertEqual(report["reveal_chimes"], 12)
        self.assertEqual(len(self.timeline["turns"]), len(self.original["turns"]))

    def test_rejects_chime_overlapping_speech_or_shortened_response(self):
        for ident in ("solution_7", "answer_13"):
            altered = copy.deepcopy(self.timeline)
            event = next(e for e in altered["events"] if e["id"] == ident)
            event["end_frame"] -= 1
            with self.assertRaises(AssertionError):
                compare_sequence(altered, self.original, self.chime["frames"])

    def test_native_markup_contains_both_cue_and_direct_url(self):
        content = read(SOURCE / "sample_content.json")
        for layout, cue in CUES.items():
            with self.subTest(layout=layout):
                markup, _ = document((SOURCE / layout / "index.html").read_text(encoding="utf-8"),
                                      self.timeline, content, layout)
                self.assertEqual(markup.count(cue), 3)
                self.assertEqual(markup.count("amzn.eu/d/0dDgJ1ZT"), 3)
                self.assertIn('data-event-id="solution_chime_7"', markup)

    def test_review_includes_every_pause_chime_and_speech_boundary(self):
        frames = {p["frame"] for p in frame_plan(self.timeline)}
        for event in self.timeline["events"]:
            if event["id"].startswith("solution_chime_"):
                for frame in (event["start_frame"] - 1, event["start_frame"],
                              event["end_frame"] - 1, event["end_frame"]):
                    self.assertIn(frame, frames)

    def test_publishing_retains_both_link_forms_credits_and_retimed_replays(self):
        def covers_only(build, output):
            output.mkdir()
            atomic_json(output / "publication_manifest.json", {"inputs": {}, "assets": {}})

        with tempfile.TemporaryDirectory() as temporary, patch("listening_2d.publishing.publish_fide_assets.publish", covers_only):
            build = Path(temporary)
            output = build / "posts"
            atomic_json(build / "sample_content.json", read(SOURCE / "sample_content.json"))
            atomic_json(build / "timeline.json", self.timeline)
            publish(build, output)
            events = {e["id"]: e for e in self.timeline["events"]}
            for platform in ("youtube", "tiktok", "instagram"):
                text = (output / f"{platform}.txt").read_text(encoding="utf-8")
                self.assertIn(CUES["landscape" if platform == "youtube" else "portrait"], text)
                self.assertIn("https://amzn.eu/d/0dDgJ1ZT", text)
                self.assertIn("Mixkit Software interface remove", text)
                self.assertIn("Lösungsklang, dann die vollständige gesprochene Lösung", text)
                self.assertNotIn("keine Musik oder Soundeffekte", text)
                self.assertLessEqual(len(text), 5000 if platform == "youtube" else 2200)
                for number in range(7, 19):
                    self.assertIn(f'{timestamp(events[f"recording_{number}"]["start"])} · Aufgabe {number}', text)


if __name__ == "__main__":
    unittest.main()
