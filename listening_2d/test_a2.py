"""Focused tests for the new A2 shared-recording/repeat and compact layouts."""

import copy
from pathlib import Path
import tempfile
import unittest

from audit_a2_sequence import audit, compare_sequence
from compose_a2 import card_body
from prepare_a2 import EPISODE, plan, read, schedule
from process_a2 import short_plan
from publish_a2_assets import caption
from prepare_sample import atomic_json


class A2Tests(unittest.TestCase):
    def setUp(self):
        self.episode = read(EPISODE)
        self.plan = plan(self.episode)
        self.manifest = {
            t["id"]: {**t, "frames": 96000, "audio": t["id"] + ".wav", "sha256": "test"}
            for t in self.plan["turns"]
        }
        self.manifest.update({name: {"frames": 24000, "audio": name + ".wav", "sha256": "test"}
                              for name in ("chime_start", "chime_back", "chime_remove")})

    def test_shared_message_reuses_one_recording_before_joint_reveal(self):
        group = self.episode["sections"][0]["groups"][0]
        events = [e for e in self.plan["events"] if e["card"] == group["id"]]
        recordings = [e for e in events if "_play" in e["id"]]
        self.assertEqual(len(recordings), 2)
        self.assertEqual(recordings[0]["audio_id"], recordings[1]["audio_id"])
        self.assertEqual([e["kind"] for e in events][-2:], ["silence", "reveal"])
        self.assertEqual(len(self.plan["cards"][group["id"]]["questions"]), 7)
        self.assertFalse(any("reveal" in e["id"] for e in events[:-1]))

    def test_part_two_repeats_each_message_not_the_whole_section(self):
        recordings = [e["audio_id"] for e in self.plan["events"]
                      if e["part"] == 2 and "_play" in e["id"]]
        self.assertEqual(recordings, ["a2_p2_cooking_audio_1"] * 2 + ["a2_p2_library_audio_1"] * 2)

    def test_short_preserves_reading_repeats_response_and_final_cta(self):
        full = schedule(self.plan["events"], self.manifest)
        section = self.episode["sections"][0]
        shortened = short_plan(full, section, section["groups"])
        clock = schedule(shortened, self.manifest, "short", 1, list(range(1, 8)))
        self.assertEqual(clock["events"][1]["duration"], 30)
        for expected in [e for e in full["events"] if e["card"] == section["groups"][0]["id"]]:
            actual = next(e for e in clock["events"] if e["id"] == expected["id"])
            self.assertEqual(actual["duration"], expected["duration"])
            self.assertEqual(actual.get("sha256"), expected.get("sha256"))
        self.assertEqual(clock["events"][-1]["audio_id"], "cta")
        self.assertFalse(any(e["id"].startswith("instruction") for e in clock["events"]))

    def test_intro_rounding_preserves_complete_title_and_half_second(self):
        for samples in (96000, 96001, 97999):
            self.manifest["short_title_1"]["frames"] = samples
            event = {"id": "intro", "kind": "speech", "audio_id": "short_title_1",
                     "title_padding": True}
            result = schedule([event], self.manifest)
            padding = result["total_frames"] * 2000 - samples
            self.assertGreaterEqual(padding, 24000)
            self.assertLess(padding, 26000)

    def test_reveal_cannot_truncate_chime_tail(self):
        self.manifest["chime_remove"]["frames"] = 144001
        with self.assertRaisesRegex(ValueError, "Audio tail"):
            schedule(self.plan["events"], self.manifest)

    def test_compact_card_hides_all_keys_until_joint_reveal(self):
        card = self.plan["cards"]["a2_p1_bicycle"]
        self.assertNotIn("data-answer=", card_body(card, False))
        revealed = card_body(card, True)
        self.assertEqual(revealed.count("data-answer="), 7)
        for question in card["questions"]:
            self.assertIn(question["question"], revealed)

    def test_short_caption_distinguishes_all_tasks_from_selected_subset(self):
        events = [{"kind": "silence"}, {"audio_id": "chime_remove"}]
        complete = {"selected": list(range(1, 8)), "events": events}
        draft = caption("tiktok", 1, {}, complete, self.episode)
        self.assertIn("alle 7 Aufgaben", draft)
        self.assertIn("Aufgabenzahl ist nicht reduziert", draft)
        self.assertIn("interface remove;", draft)
        subset = {"selected": [8], "events": events}
        draft = caption("instagram", 2, {}, subset, self.episode)
        self.assertIn("1 von 2 Aufgaben", draft)
        self.assertIn("0afqgrGT", draft)
        self.assertNotIn("ÖIF B1", draft)

    def test_youtube_chapters_merge_sub_ten_second_opening_and_cta(self):
        full = {"duration": 697.166667, "events": [
            {"id": "instruction_1", "start": 8.708333},
            {"id": "instruction_2", "start": 156},
            {"id": "instruction_3", "start": 340},
            {"id": "instruction_4", "start": 500},
            {"id": "summary_read", "start": 678.291667},
            {"id": "cta", "start": 688.291667, "audio_id": "cta"},
        ]}
        draft = caption("youtube", None, full, None, self.episode)
        self.assertIn("00:00 Start und Teil 1", draft)
        self.assertIn("11:18 Lösungen und Buch", draft)
        self.assertNotIn("00:08", draft)
        self.assertNotIn("11:28", draft)

    def revised_events(self):
        self.episode["opening"].update(display="ÖIF A2 Hören", text="Ö I F A zwei Hören.")
        self.manifest["title"]["text"] = "Ö I F A zwei Hören."
        chimes = {e["part"]: e for e in self.plan["events"]
                  if e["id"] == f"part_{e['part']}_start"}
        revised = []
        for source in self.plan["events"]:
            event = copy.deepcopy(source)
            ident, part = event["id"], event["part"]
            if ident == f"part_{part}_start" or ident.endswith("_back"):
                continue
            if ident.endswith("_replay_gap"):
                event["seconds"] = 5
            if ident.endswith("_answer"):
                event["seconds"] = 10
            if ident == "end_part_4":
                event.update(id="end_test", audio_id="end_test")
            revised.append(event)
            if ident == f"part_{part}_read":
                revised.append(copy.deepcopy(chimes[part]))
            if part == 1 and ident.endswith("_replay_gap"):
                revised.append(dict(id=ident.replace("_gap", "_chime"), kind="chime",
                                    part=1, audio_id="chime_start"))
            if ident in ("end_part_1", "end_part_2", "end_part_3"):
                revised.append(dict(id=f"after_part_{part}", kind="silence",
                                    part=part, seconds=5))
        self.manifest["end_test"] = {
            **self.manifest["end_part_4"], "id": "end_test", "text": "Ende des Testteils Hören."}
        return revised

    def test_revised_sequence_passes_with_separate_guided_reveals(self):
        timeline = schedule(self.revised_events(), self.manifest)
        self.assertTrue(compare_sequence(self.episode, timeline)["matches_requested_sequence"])

    def test_sequence_gate_rejects_legacy_production_settings(self):
        report = compare_sequence(self.episode, schedule(self.plan["events"], self.manifest))
        issues = {(i["code"], i["event"]) for i in report["issues"]}
        self.assertIn(("event_duration", "a2_p1_bicycle_replay_gap"), issues)
        self.assertIn(("event_duration", "a2_p4_payment_answer"), issues)
        self.assertIn(("event_order", "part_1_start"), issues)
        self.assertIn(("missing_event", "after_part_1"), issues)
        self.assertIn(("missing_event", "a2_p1_bicycle_replay_chime"), issues)
        self.assertIn(("missing_event", "end_test"), issues)
        self.assertIn(("unexpected_event", "a2_p2_library_back"), issues)

    def test_sequence_gate_rejects_chime_before_reading(self):
        events = self.revised_events()
        read_index = next(i for i, e in enumerate(events) if e["id"] == "part_3_read")
        events[read_index:read_index + 2] = reversed(events[read_index:read_index + 2])
        report = compare_sequence(self.episode, schedule(events, self.manifest))
        self.assertTrue(any(i["code"] == "event_order" for i in report["issues"]))

    def test_sequence_gate_measures_frames_not_declared_pause_seconds(self):
        timeline = schedule(self.revised_events(), self.manifest)
        gap = next(e for e in timeline["events"] if e["id"] == "a2_p1_bicycle_replay_gap")
        gap["end_frame"] += 72
        report = compare_sequence(self.episode, timeline)
        self.assertTrue(any(i["code"] == "event_duration" and i["actual_seconds"] == 8
                            for i in report["issues"]))

    def test_sequence_gate_rejects_missing_break_chime_or_reveal(self):
        for ident in ("after_part_2", "a2_p1_bicycle_replay_chime", "a2_p2_cooking_reveal"):
            with self.subTest(event=ident):
                events = [e for e in self.revised_events() if e["id"] != ident]
                report = compare_sequence(self.episode, schedule(events, self.manifest))
                self.assertTrue(any(i["code"] == "missing_event" and i["event"] == ident
                                    for i in report["issues"]))

    def test_sequence_gate_rejects_reveal_before_complete_answer_pause(self):
        events = self.revised_events()
        answer = next(i for i, e in enumerate(events) if e["id"] == "a2_p3_pool_answer")
        events[answer:answer + 2] = reversed(events[answer:answer + 2])
        report = compare_sequence(self.episode, schedule(events, self.manifest))
        self.assertTrue(any(i["code"] == "event_order" for i in report["issues"]))

    def test_sequence_gate_rejects_changed_second_recording(self):
        timeline = schedule(self.revised_events(), self.manifest)
        repeat = next(e for e in timeline["events"] if e["id"] == "a2_p2_library_play2_turn1")
        repeat["sha256"] = "different-take"
        report = compare_sequence(self.episode, timeline)
        self.assertTrue(any(i["code"] == "changed_repeat_audio" for i in report["issues"]))

    def test_revision_requires_title_only_display_and_speech(self):
        timeline = schedule(self.revised_events(), self.manifest)
        self.episode["opening"]["display"] = "ÖIF A2 Hören · 15 Aufgaben"
        timeline["events"][0]["text"] += " Fünfzehn Aufgaben aus dem Alltag."
        report = compare_sequence(self.episode, timeline)
        self.assertTrue(any(i["code"] == "opening_content" for i in report["issues"]))
        self.assertTrue(any(i["code"] == "opening_speech" for i in report["issues"]))

    def test_revision_requires_test_ending_not_just_part_four_ending(self):
        timeline = schedule(self.revised_events(), self.manifest)
        ending = next(e for e in timeline["events"] if e["id"] == "end_test")
        ending["text"] = "Ende von Teil vier."
        report = compare_sequence(self.episode, timeline)
        self.assertTrue(any(i["code"] == "event_field" and i["field"] == "text"
                            for i in report["issues"]))

    def test_revision_checks_actual_title_html_not_just_episode_metadata(self):
        for extra in ("", "<h2>Wie viel verstehst du?</h2><p>15 Aufgaben aus dem Alltag</p>"):
            with self.subTest(extra=extra), tempfile.TemporaryDirectory() as directory:
                build = Path(directory)
                timeline = schedule(self.revised_events(), self.manifest)
                atomic_json(build / "timeline.json", timeline)
                atomic_json(build / "sample_content.json", {"episode": self.episode})
                atomic_json(build / "composition_receipt.json", {"layouts": ["landscape", "portrait"]})
                for layout in ("landscape", "portrait"):
                    (build / layout).mkdir()
                    (build / layout / "index.html").write_text(
                        f'<section id="scene-0"><h1>ÖIF A2 Hören</h1>{extra}</section>',
                        encoding="utf-8")
                report_path = build / "sequence_review.json"
                self.assertEqual(audit(build, report_path), not bool(extra))
                if extra:
                    self.assertTrue(any(i["code"] == "opening_visual"
                                        for i in read(report_path)["issues"]))


if __name__ == "__main__":
    unittest.main()
