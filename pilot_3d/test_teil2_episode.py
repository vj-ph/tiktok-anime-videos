import copy
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import wave
from unittest.mock import patch

from episode_config import check_timeline, read_episode, section_windows, validate_template
from picture_presentation import (COMPACT_BOX, FACE_BOX, REVEAL_BOX, picture_bounds,
                                  picture_filters, picture_windows)
from prepare_audio import atomic_json, sha256_file
from pipeline import build_episode, freeze_delivery
from produce_v4 import camera_shots
from render import mux, scene_hash
from review_social import review_pictures
from scene_direction import performance_plan
from social_captions import caption_pages, make_ass, validate_layout, write_publication
from test_episode_config import clock

ROOT = Path(__file__).resolve().parent


class Teil2EpisodeTests(unittest.TestCase):
    def setUp(self):
        self.episode = read_episode(ROOT / "episodes/teil2_einkaufen.json")

    def test_complete_script_and_real_assets_validate(self):
        validate_template(self.episode, check_assets=True)
        validate_layout(self.episode)
        self.assertEqual(self.episode["exam_part"], 2)
        self.assertEqual(len(self.episode["turns"]), 14)
        self.assertEqual(len(self.episode["source"]["exercises"]), 2)
        self.assertEqual(len(self.episode["pictures"]), 2)
        self.assertIn("zweite Teil", self.episode["turns"][-1]["text"])
        previous = read_episode(ROOT / "episodes/teil1_vorstellung.json")
        self.assertEqual(self.episode["voices"], previous["voices"])
        self.assertEqual(self.episode["turns"][0], previous["turns"][0])

    def test_images_are_byte_identical_to_the_cleared_book_stimuli(self):
        for key, source in self.episode["source"]["images"].items():
            path = (ROOT / "episodes" / source).resolve()
            picture = self.episode["pictures"][key]
            self.assertEqual(sha256_file(path), sha256_file(Path(picture["path"])))
            self.assertIn("user confirmed", picture["permission"])
            self.assertIn("2026-10-22", picture["permission"])
        self.assertEqual({p["candidate"] for p in self.episode["pictures"].values()},
                         {"candidate_a", "candidate_b"})

    def test_both_candidates_describe_then_answer_two_personal_questions(self):
        turns = self.episode["turns"]
        for index, role, key in ((2, "candidate_a", "wochenmarkt"), (8, "candidate_b", "supermarkt")):
            sequence = turns[index:index+5]
            self.assertEqual([t["speaker"] for t in sequence], [role, "examiner", role, "examiner", role])
            self.assertEqual([t["action"] for t in sequence], ["describe", "ask", "answer", "ask", "answer"])
            self.assertEqual([t["section"] for t in sequence], ["2A", "2B", "2B", "2B", "2B"])
            self.assertEqual(sequence[0]["picture"], key)
            for turn in sequence:
                self.assertEqual(turn["look_at"], role if turn["speaker"] == "examiner" else "examiner")
        self.assertIn("Vielleicht", turns[2]["text"])
        self.assertIn("Vielleicht", turns[8]["text"])
        for word in ("Markt", "Einkaufskorb", "Obst", "Gemüse", "Stände"):
            self.assertIn(word, turns[2]["text"])
        for word in ("Kühlregal", "zwei Becher", "Einkaufswagen", "Angeboten"):
            self.assertIn(word, turns[8]["text"])
        for word, index in (("Schwester", 4), ("Köln", 6), ("Meine Frau", 10), ("Seitdem", 12)):
            self.assertIn(word, turns[index]["text"])

    def test_two_reading_cards_have_the_approved_hold_and_eight_seconds(self):
        timeline = clock(self.episode, seconds=30)
        check_timeline(self.episode, timeline)
        windows = picture_windows(self.episode, timeline)
        self.assertEqual([w["mode"] for w in windows], ["reveal", "compact"]*2)
        for index in (0, 2):
            reveal, compact = windows[index:index+2]
            prompt = next(t for t in timeline["turns"] if t["id"] == reveal["turn"])
            self.assertEqual(reveal["start_frame"]-prompt["end_frame"], 29)
            self.assertEqual(reveal["end_frame"]-reveal["start_frame"], 192)
            self.assertEqual(reveal["end_frame"], compact["start_frame"])
            self.assertEqual(reveal["picture"], compact["picture"])
            shot = (reveal["start"], "candidates")
            self.assertIn(shot, camera_shots(self.episode, timeline))
        self.assertEqual(self.episode["outro_seconds"], 6)
        self.assertEqual(self.episode["takeaway"], [])
        self.assertTrue(all(t["pause_after"] == 1.2 for t in self.episode["turns"]
                            if "picture_card_delay_seconds" not in t and t["action"] != "welcome"))

    def test_prompt_captions_stop_before_each_picture_card_and_all_words_survive(self):
        timeline = clock(self.episode, seconds=30)
        pages = caption_pages(self.episode, timeline)
        for turn in timeline["turns"]:
            selected = [p for p in pages if p["turn_id"] == turn["id"]]
            self.assertEqual(" ".join(p["text"] for p in selected), turn["text"])
        for window in picture_windows(self.episode, timeline):
            if window["mode"] == "reveal":
                page = [p for p in pages if p["turn_id"] == window["turn"]][-1]
                self.assertLessEqual(page["end"], window["start"])
                self.assertLess(window["start"]-page["end"], .011)
        ass = make_ass(self.episode, timeline)
        self.assertEqual(ass.count("Beschreibe das Bild."), 2)
        self.assertEqual(ass.count("Lernpause · Video anhalten."), 2)
        self.assertNotIn("TIPPS FÜR EUREN DIALOG", ass)
        self.assertEqual([w["section"] for w in section_windows(self.episode, timeline)],
                         [None, "2A", "2B", "2A", "2B", None])

    def test_picture_bounds_fit_whole_landscape_and_portrait_images_without_cropping(self):
        from PIL import Image
        for picture in self.episode["pictures"].values():
            for mode, expected in (("reveal", REVEAL_BOX), ("compact", COMPACT_BOX)):
                self.assertEqual(picture_bounds(picture["path"], mode), expected)
        self.assertLess(COMPACT_BOX[2], FACE_BOX[0])
        self.assertLess(FACE_BOX[3], 578)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "portrait.png"
            Image.new("RGB", (600, 900)).save(path)
            x, y, right, bottom = picture_bounds(path, "reveal")
            self.assertGreater(x, REVEAL_BOX[0])
            self.assertLess(right, REVEAL_BOX[2])
            self.assertEqual((y, bottom), (REVEAL_BOX[1], REVEAL_BOX[3]))
            self.assertLess(abs((right-x)/(bottom-y)-2/3), .01)

    def test_description_gestures_span_the_monologue_and_examiner_acknowledges(self):
        timeline = clock(self.episode, seconds=30)
        plan = performance_plan(timeline)
        for turn in timeline["turns"]:
            if turn["action"] != "describe":
                continue
            beats = [g for g in plan["gestures"] if g["turn_id"] == turn["id"]]
            self.assertEqual(len(beats), 3)
            self.assertGreater(beats[-1]["peak"]-beats[0]["peak"], turn["duration"]/2)
            self.assertLessEqual(max(g["strength"] for g in beats), .72)
            self.assertTrue(any(n.get("turn_id") == turn["id"] and n["actor"] == "examiner"
                                for n in plan["nods"]))

    def test_bad_picture_shapes_references_and_permissions_fail_before_synthesis(self):
        variants = [
            lambda e: e.update(pictures=[]),
            lambda e: e["pictures"]["wochenmarkt"].update(permission=""),
            lambda e: e["pictures"]["wochenmarkt"].update(candidate="observer"),
            lambda e: e["pictures"]["supermarkt"].update(candidate="candidate_a"),
            lambda e: e["turns"][2].update(picture="missing"),
            lambda e: e["turns"][2].update(camera="candidate_a"),
            lambda e: e["turns"][1].update(picture_card_delay_seconds=9.2),
            lambda e: e["turns"][1].update(picture_card_delay_seconds=True),
            lambda e: e["turns"][1].update(picture_card_delay_seconds=-1),
            lambda e: e["turns"][1].pop("picture"),
            lambda e: e["turns"][2].pop("picture"),
            lambda e: e["turns"][2].update(picture="supermarkt"),
            lambda e: e["turns"][1].update(look_at="candidate_b"),
            lambda e: e["pictures"].update(unused=copy.deepcopy(e["pictures"]["wochenmarkt"])),
        ]
        for mutate in variants:
            episode = copy.deepcopy(self.episode)
            mutate(episode)
            with self.subTest(episode=episode), self.assertRaises(ValueError):
                validate_template(episode)

    def test_missing_corrupt_and_low_resolution_assets_are_not_silently_accepted(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad.jpg"
            self.episode["pictures"]["wochenmarkt"]["path"] = str(path)
            with self.assertRaises(FileNotFoundError):
                validate_template(self.episode, check_assets=True)
            path.write_bytes(b"not an image")
            with self.assertRaises(OSError):
                validate_template(self.episode, check_assets=True)
            Image.new("RGB", (80, 60)).save(path)
            with self.assertRaisesRegex(ValueError, "too small"):
                validate_template(self.episode, check_assets=True)

    def test_picture_labels_are_measured_before_synthesis(self):
        self.episode["pictures"]["wochenmarkt"]["label"] = "Ein sehr langer Name für ein Bild"
        with self.assertRaisesRegex(ValueError, "labels"):
            validate_layout(self.episode)

    def test_picture_paths_follow_external_episode_and_survive_snapshot_roundtrip(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "external.json"
            raw = copy.deepcopy(self.episode)
            raw["pictures"]["wochenmarkt"]["path"] = "media/market.jpg"
            atomic_json(path, raw)
            loaded = read_episode(path)
            self.assertEqual(loaded["pictures"]["wochenmarkt"]["path"], str(Path(folder)/"media/market.jpg"))
            snapshot = Path(folder) / "snapshot.json"
            atomic_json(snapshot, loaded)
            self.assertEqual(read_episode(snapshot), loaded)

    def test_publication_keeps_image_and_rig_credits_without_inventing_a_license(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            write_publication(path, self.episode)
            caption = (path / "publishing_caption.txt").read_text()
            self.assertEqual(caption.count("Bildimpulse: DeutschKompass"), 1)
            for required in ("Übungen 1 und 7", "Snow Rig", "Rain Rig", "CC BY 4.0",
                             "KI-generierte", "keine vollständige Prüfung", "Lernpausen"):
                self.assertIn(required, caption)
            credits = (path / "CREDITS.txt").read_text()
            self.assertIn("Bildimpulse: DeutschKompass", credits)
            self.assertNotIn("CC BY 4.0", self.episode["pictures"]["wochenmarkt"]["credit"])

    def test_picture_bytes_are_part_of_the_immutable_build_spec(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            picture = self.episode["pictures"]["wochenmarkt"]
            copy = root / "market.jpg"
            shutil.copy2(picture["path"], copy)
            picture["path"] = str(copy)
            build = root / "run"
            with patch("pipeline.preflight", return_value=self.episode):
                with patch("pipeline.run_command", side_effect=RuntimeError("explicit synthesis stop")):
                    with self.assertRaisesRegex(RuntimeError, "explicit synthesis stop"):
                        build_episode(ROOT / "episodes/teil2_einkaufen.json", build, until="audio")
                state = json.loads((build / "pipeline_state.json").read_text())
                self.assertEqual(state["spec"]["asset_sha256"][str(copy)], sha256_file(copy))
                self.assertIn("picture_presentation.py", state["spec"]["code_sha256"])
                copy.write_bytes(copy.read_bytes()+b"changed")
                with self.assertRaisesRegex(ValueError, "different episode/settings/source"):
                    build_episode(ROOT / "episodes/teil2_einkaufen.json", build, until="audio")

    def test_frozen_delivery_preserves_and_hashes_picture_bytes_and_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            build = Path(folder)
            atomic_json(build / "episode.json", self.episode)
            names = ("pilot.mp4", "pilot_clean.mp4", "captions.ass", "subtitles.srt",
                     "dialogue.wav", "timeline.json", "scene_manifest.json", "frames_manifest.json",
                     "publishing_caption.txt", "CREDITS.txt", "subtitle_timing_report.json",
                     "safe_zone_report.json", "delivery_checks.json", "picture_timing_report.json")
            for name in names:
                (build / name).write_text("Explicit synthetic freeze fixture")
            freeze_delivery(build)
            receipt = json.loads((build / "export_manifest.json").read_text())
            for key, picture in self.episode["pictures"].items():
                relative = f"picture_assets/{key}.jpg"
                self.assertEqual(receipt["files_sha256"][relative], sha256_file(Path(picture["path"])))
                self.assertEqual(sha256_file(build / relative), sha256_file(Path(picture["path"])))
            self.assertIn("picture_timing_report.json", receipt["files_sha256"])
            self.assertIn("picture_presentation.py", receipt["source_sha256"])

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
    def test_real_encoded_picture_changes_on_odd_frames_and_clears_at_both_edges(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as folder:
            build = Path(folder)
            (build / "frames").mkdir()
            turns = []
            for index, (source, start, stop) in enumerate(((1, 0, 5), (2, 17, 30), (7, 35, 45),
                                                         (8, 61, 77), (13, 83, 88))):
                turn = {**self.episode["turns"][source], "id": f"t{index}", "text": "Ein Bild."}
                if "picture_card_delay_seconds" in turn:
                    turn["picture_card_delay_seconds"] = 4/24
                turns.append({**turn, "start": start/24, "end": stop/24,
                              "start_frame": start, "end_frame": stop,
                              "wav_duration": (stop-start)/24, "duration": (stop-start)/24,
                              "words": [{"word": "Ein", "start": .01, "end": .04, "score": .9},
                                        {"word": "Bild.", "start": .06, "end": .09, "score": .9}]})
            episode = {**self.episode, "intro_seconds": 0, "outro_seconds": 0,
                       "subtitle_mode": "legacy", "turns": [
                           {k: v for k, v in t.items() if k not in (
                               "start", "end", "start_frame", "end_frame", "wav_duration", "duration", "words")}
                           for t in turns]}
            timeline = {"fps": 24, "total_frames": 100, "duration": 100/24, "turns": turns}
            manifest = {"episode": episode, "timeline": timeline,
                        "width": 90, "height": 160, "motion_step": 2}
            for name, data in (("episode.json", episode), ("timeline.json", timeline),
                               ("scene_manifest.json", manifest)):
                atomic_json(build / name, data)
            (build / "studio.blend").write_bytes(b"Explicit synthetic picture-clock fixture, not a scene")
            atomic_json(build / "frames_manifest.json", {"scene": manifest, "blend_sha256": scene_hash(build)})
            image = build / "plate.png"
            Image.new("RGB", (90, 160), "#888888").save(image)
            for frame in range(1, 101, 2):
                os.link(image, build / "frames" / f"frame_{frame:04d}.png")
            with wave.open(str(build / "dialogue.wav"), "wb") as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(48000)
                audio.writeframes(b"\x00\x00"*200000)
            mux(build, build / "episode.json")
            report = review_pictures(build, episode, timeline)
            self.assertEqual(len(report["windows"]), 4)
            self.assertEqual([w["start_frame"] for w in report["windows"]], [9, 17, 49, 61])
            self.assertTrue(all(len(w["decoded_checks"]) == 5 for w in report["windows"]))
            receipt = json.loads((build / "picture_timing_report.json").read_text())
            receipt["windows"][0]["sha256"] = "tampered"
            atomic_json(build / "picture_timing_report.json", receipt)
            with self.assertRaisesRegex(ValueError, "receipt differs"):
                review_pictures(build, episode, timeline)


if __name__ == "__main__":
    unittest.main()
