import copy
from pathlib import Path
import tempfile
import unittest

from episode_config import (check_timeline, read_episode, section_windows, task_window,
                            turn_phase, validate_template)
from render import ass_time
from scene_direction import VERSION, gaze_at, performance_plan
from social_captions import (caption_pages, frame_safe_time, make_ass, validate_layout,
                             write_publication)
from test_episode_config import clock

ROOT = Path(__file__).resolve().parent


class Teil1EpisodeTests(unittest.TestCase):
    def setUp(self):
        self.episode = read_episode(ROOT / "episodes/teil1_vorstellung.json")

    def test_complete_book_based_episode_validates_with_real_assets(self):
        validate_template(self.episode, check_assets=True)
        validate_layout(self.episode)
        self.assertEqual(self.episode["exam_part"], 1)
        self.assertEqual(self.episode["visual_version"], VERSION)
        self.assertEqual(len(self.episode["turns"]), 10)
        self.assertIn("speaking_dtz_gpt_v1/book_no_toc.md", self.episode["source"]["book"])
        self.assertEqual(len(self.episode["source"]["exercises"]), 3)
        self.assertIn("keine vollständige", self.episode["disclaimer"])

    def test_shared_voices_and_welcome_remain_reusable_without_speech_changes(self):
        previous = read_episode(ROOT / "episodes/lerntreffen_dtz.json")
        self.assertEqual(self.episode["voices"], previous["voices"])
        self.assertEqual(self.episode["turns"][0], previous["turns"][0])
        self.assertEqual(self.episode["intro_seconds"], previous["intro_seconds"])
        self.assertEqual(self.episode["scene"], previous["scene"])

    def test_each_candidate_introduces_themself_and_answers_a_linked_question(self):
        turns = self.episode["turns"]
        for start, role, profile, question, answer in (
            (2, "candidate_a", "Verkäuferin", "Beruf", "Kunden"),
            (6, "candidate_b", "Kinder", "Üben", "Schule"),
        ):
            introduction, examiner, response = turns[start:start + 3]
            self.assertEqual([turn["speaker"] for turn in (introduction, examiner, response)],
                             [role, "examiner", role])
            self.assertEqual([turn["action"] for turn in (introduction, examiner, response)],
                             ["introduce", "ask", "answer"])
            self.assertEqual([turn["section"] for turn in (introduction, examiner, response)],
                             ["1A", "1B", "1B"])
            self.assertIn(profile, introduction["text"])
            self.assertIn(question, examiner["text"])
            self.assertIn(answer, response["text"])
            self.assertEqual(examiner["look_at"], role)
            for turn in (introduction, response):
                self.assertEqual(turn["look_at"], "examiner")
                self.assertEqual(turn["camera"], role)
        self.assertEqual(turns[5]["look_at"], "candidate_b")
        self.assertIn("erste Teil", turns[-1]["text"])

    def test_both_introductions_cover_all_six_profile_points(self):
        self.assertEqual(self.episode["task_card"],
                         ["Name", "Geburtsort", "Wohnort", "Arbeit / Beruf", "Familie", "Sprachen"])
        for point in self.episode["task_card"]:
            self.assertEqual(self.episode["source"]["coverage"][point], ["03", "07"])
        for turn, required in (
            (self.episode["turns"][2], ("Lea", "Warschau", "Köln", "Verkäuferin", "Schwester", "Polnisch")),
            (self.episode["turns"][6], ("Samir", "Casablanca", "Dortmund", "arbeite", "Kindern", "Arabisch")),
        ):
            for word in required:
                self.assertIn(word, turn["text"])
        ids = {turn["id"] for turn in self.episode["turns"]}
        self.assertTrue(all(set(values) <= ids for values in self.episode["source"]["coverage"].values()))

    def test_repeated_exam_sections_do_not_restart_entrance_or_instruction(self):
        self.assertEqual([turn_phase(turn) for turn in self.episode["turns"]],
                         ["welcome", "instruction"] + ["dialogue"] * 8)
        timeline = clock(self.episode, seconds=30)
        check_timeline(self.episode, timeline)
        start, end = task_window(timeline)
        self.assertEqual(round((start - timeline["turns"][1]["end"]) * 24), 29)
        self.assertAlmostEqual(end - start, 8)
        self.assertEqual(end, timeline["turns"][2]["start"])
        self.assertEqual(self.episode["outro_seconds"], 6)
        self.assertEqual(self.episode["takeaway"], [])
        self.assertTrue(all(turn["pause_after"] == 1.2 for turn in self.episode["turns"][2:]))

    def test_timed_headers_cover_both_candidates_and_reset_for_closing(self):
        timeline = clock(self.episode, seconds=30)
        windows = section_windows(self.episode, timeline)
        self.assertEqual([window["section"] for window in windows], [None, "1A", "1B", "1A", "1B", None])
        self.assertEqual([window["start"] for window in windows],
                         [0] + [timeline["turns"][i]["start"] for i in (2, 3, 5, 7, 9)])
        self.assertEqual(windows[-1]["end"], timeline["duration"])
        for left, right in zip(windows, windows[1:]):
            self.assertEqual(left["end"], right["start"])
        ass = make_ass(self.episode, timeline)
        headers = [line for line in ass.splitlines() if r"\pos(104,241)" in line]
        self.assertEqual(len(headers), len(windows))
        for window, line in zip(windows, headers):
            self.assertIn(window["label"], line)
            self.assertTrue(line.startswith(
                f"Dialogue: 0,{ass_time(frame_safe_time(window['start'], 24))},"
                f"{ass_time(frame_safe_time(window['end'], 24))},"))
        self.assertEqual(sum("DEUTSCHKOMPASS · B1 SPRECHEN" in line for line in ass.splitlines()), 1)
        self.assertNotIn("TIPPS FÜR EUREN DIALOG", ass)

    def test_six_second_cta_includes_every_encoded_frame_on_an_odd_frame_timeline(self):
        import math

        timeline = clock(self.episode, seconds=30)
        self.assertEqual(timeline["total_frames"] % 6, 3)
        ass = make_ass(self.episode, timeline)
        event = next(line.split(",", 9) for line in ass.splitlines() if "Amazon-Buchlink" in line)

        def frame_at(timestamp):
            hours, minutes, seconds = timestamp.split(":")
            return math.ceil((int(hours) * 3600 + int(minutes) * 60 + float(seconds)) * 24 - 1e-7)

        self.assertEqual(frame_at(event[1]), timeline["total_frames"] - 144)
        self.assertEqual(frame_at(event[2]), timeline["total_frames"])
        self.assertEqual(frame_at(event[2]) - frame_at(event[1]), 144)

    def test_section_header_resets_at_cta_without_an_unlabelled_closing_turn(self):
        self.episode["turns"][-1]["section"] = "1B"
        timeline = clock(self.episode)
        windows = section_windows(self.episode, timeline)
        self.assertEqual(windows[-1]["section"], None)
        self.assertEqual(windows[-1]["start"], timeline["duration"] - 6)
        self.assertEqual(windows[-2]["end"], windows[-1]["start"])

    def test_first_section_can_start_at_frame_zero_without_an_empty_header_event(self):
        self.episode.update(intro_seconds=0, task_card=[], outro_seconds=0)
        self.episode["scene"]["entrance"] = False
        self.episode["turns"] = self.episode["turns"][2:5]
        validate_template(self.episode)
        timeline = clock(self.episode, seconds=30)
        windows = section_windows(self.episode, timeline)
        self.assertEqual(windows[0]["start"], 0)
        self.assertEqual(windows[0]["section"], "1A")
        self.assertTrue(all(window["end"] > window["start"] for window in windows))
        make_ass(self.episode, timeline)

    def test_sections_are_optional_and_unused_labels_do_not_change_legacy_ass(self):
        episode = read_episode(ROOT / "episodes/lerntreffen_dtz.json")
        timeline = clock(episode, seconds=10)
        original = make_ass(episode, timeline)
        self.assertEqual(section_windows(episode, timeline), [
            {"start": 0, "end": timeline["duration"], "section": None, "label": episode["header"]["topic"]}])
        episode.update(exam_part=3, sections={"3": "Teil 3 · Gemeinsam planen"})
        validate_template(episode)
        self.assertEqual(make_ass(episode, timeline), original)

    def test_section_metadata_rejects_bad_shapes_labels_and_unknown_references(self):
        for sections in ([], None, "1A", {"bad id": "Vorstellung"}, {"1A": ""}, {"1A": 1}):
            with self.subTest(sections=sections):
                episode = copy.deepcopy(self.episode)
                episode["sections"] = sections
                with self.assertRaises(ValueError):
                    validate_template(episode)
        for section in ("2A", "", None, True, ["1A"]):
            with self.subTest(section=section):
                episode = copy.deepcopy(self.episode)
                episode["turns"][2]["section"] = section
                with self.assertRaisesRegex(ValueError, "declared section"):
                    validate_template(episode)
        for part in (0, 4, True, "1", 1.0, None):
            with self.subTest(exam_part=part):
                episode = copy.deepcopy(self.episode)
                episode["exam_part"] = part
                with self.assertRaisesRegex(ValueError, "exam_part"):
                    validate_template(episode)

    def test_dynamic_headers_are_checked_before_synthesis_even_when_unused(self):
        self.episode["sections"]["unused"] = "Diese viel zu lange Abschnittsüberschrift " * 4
        with self.assertRaisesRegex(ValueError, "Section header"):
            validate_layout(self.episode)

    def test_new_actions_are_supported_but_unknown_actions_fail(self):
        self.assertEqual({turn["action"] for turn in self.episode["turns"]},
                         {"welcome", "explain", "introduce", "ask", "answer"})
        self.episode["turns"][2]["action"] = "unsupported"
        with self.assertRaisesRegex(ValueError, "unsupported acting"):
            validate_template(self.episode)

    def test_introduction_gestures_are_restrained_and_span_the_monologue(self):
        timeline = clock(self.episode, seconds=30)
        plan = performance_plan(timeline)
        for turn in timeline["turns"]:
            gestures = [event for event in plan["gestures"] if event["turn_id"] == turn["id"]]
            if turn["action"] == "introduce":
                self.assertEqual(len(gestures), 3)
                self.assertGreater(gestures[-1]["peak"] - gestures[0]["peak"], turn["duration"] / 2)
            if turn["action"] in ("introduce", "ask", "answer"):
                self.assertTrue(gestures)
                self.assertLessEqual(max(event["strength"] for event in gestures), .75)

    def test_examiner_acknowledges_answers_before_the_next_question(self):
        timeline = clock(self.episode, seconds=30)
        plan = performance_plan(timeline)
        responses = [event for event in plan["nods"] if event.get("kind") == "listener"]
        self.assertEqual([event["turn_id"] for event in responses], ["03", "05", "07", "09"])
        for event in responses:
            index = next(i for i, turn in enumerate(timeline["turns"]) if turn["id"] == event["turn_id"])
            self.assertEqual(event["actor"], "examiner")
            self.assertLessEqual(event["peak"] + .32, timeline["turns"][index + 1]["start"])
        for turn in timeline["turns"]:
            if turn["action"] in ("introduce", "answer"):
                self.assertAlmostEqual(gaze_at(plan, turn["speaker"], turn["end"])["head"], 0)
        self.assertAlmostEqual(gaze_at(plan, "examiner", timeline["turns"][3]["end"])["head"], .1)
        self.assertAlmostEqual(gaze_at(plan, "examiner", timeline["turns"][7]["end"])["head"], -.1)

    def test_captions_keep_every_word_and_publication_has_disclosure_and_credits(self):
        timeline = clock(self.episode, seconds=30)
        pages = caption_pages(self.episode, timeline)
        for turn in timeline["turns"]:
            displayed = " ".join(page["text"] for page in pages if page["turn_id"] == turn["id"])
            self.assertEqual(displayed, turn["text"])
        with tempfile.TemporaryDirectory() as directory:
            build = Path(directory)
            write_publication(build, self.episode)
            caption = (build / "publishing_caption.txt").read_text()
            for required in ("Teil 1", "KI-generierte", "keine vollständige Prüfung",
                             "Snow Rig", "Rain Rig", "CC BY 4.0", "Amazon-Buchlink im Profil"):
                self.assertIn(required, caption)


if __name__ == "__main__":
    unittest.main()
