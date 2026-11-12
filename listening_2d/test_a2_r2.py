"""Regression checks for the separately versioned A2 production revision."""

import unittest

from audit_a2_sequence import compare_sequence
from prepare_a2_r2 import plan, revision_episode, schedule
from process_a2_r2 import short_plan
from publish_a2_assets_r2 import caption


class A2RevisionTests(unittest.TestCase):
    def setUp(self):
        self.episode = revision_episode()
        self.plan = plan(self.episode)
        self.manifest = {
            turn["id"]: {**turn, "frames": 96001, "audio": turn["id"] + ".wav",
                         "sha256": turn["id"]}
            for turn in self.plan["turns"]
        }
        self.manifest.update({
            name: {"frames": 24000, "audio": name + ".wav", "sha256": name}
            for name in ("chime_start", "chime_remove")
        })
        self.full = schedule(self.plan["events"], self.manifest)

    def test_real_revision_planner_passes_independent_sequence_and_opening_gate(self):
        result = compare_sequence(self.episode, self.full)
        self.assertTrue(result["matches_requested_sequence"], result["issues"])

    def test_every_short_preserves_read_chime_groups_and_complete_title(self):
        for section in self.episode["sections"]:
            with self.subTest(part=section["part"]):
                selected = section["groups"]
                numbers = [q["number"] for group in selected for q in group["questions"]]
                clock = schedule(short_plan(self.full, section, selected), self.manifest,
                                 "short", section["part"], numbers)
                events = clock["events"]
                reading = next(e for e in self.full["events"]
                               if e["id"] == f"part_{section['part']}_read")
                start = next(e for e in self.full["events"]
                             if e["id"] == f"part_{section['part']}_start")
                self.assertEqual(events[1]["duration"], reading["duration"])
                self.assertEqual(events[2]["id"], start["id"])
                self.assertEqual(events[2]["sha256"], start["sha256"])
                group_ids = {group["id"] for group in selected}
                original = [e for e in self.full["events"] if e["card"] in group_ids]
                fields = ("id", "kind", "duration", "audio_id", "sha256")
                self.assertEqual(
                    [[e.get(key) for key in fields] for e in events[3:-1]],
                    [[e.get(key) for key in fields] for e in original])
                self.assertEqual(events[-1]["audio_id"], "cta")
                padding = events[0]["end_frame"] * 2000 - events[0]["audio_samples"]
                self.assertGreaterEqual(padding, 24000)
                self.assertLess(padding, 26000)

    def test_revision_caption_uses_new_pauses_and_only_actual_sfx(self):
        section = self.episode["sections"][0]
        short = schedule(short_plan(self.full, section, section["groups"]), self.manifest,
                         "short", 1, list(range(1, 8)))
        for part, clock in ((None, None), (1, short)):
            with self.subTest(part=part):
                draft = caption("tiktok", part, self.full, clock, self.episode)
                self.assertIn("5 Sekunden zwischen Wiederholungen", draft)
                self.assertIn("10 Sekunden Antwortzeit", draft)
                self.assertNotIn("8 Sekunden zwischen Wiederholungen", draft)
                self.assertNotIn("12 Sekunden Antwortzeit", draft)
                self.assertIn("interface start/remove;", draft)
                self.assertNotIn("interface start/back", draft)


if __name__ == "__main__":
    unittest.main()
