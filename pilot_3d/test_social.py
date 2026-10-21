import json
import math
import os
import shutil
import struct
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from align_words import validate_words
from produce_v4 import ROOT, camera_at_frame, camera_shots, path_at, promo, verify_speaker_cameras
from social_captions import (MAX_PAGE_CPS, MIN_PAGE_SECONDS, SAFE, active_word, audit_ass,
                             caption_pages, chunks, editorial_rows, hook_bounds, make_ass, measured_lines, readable_pages,
                             write_caption_timing, write_publication)


class SocialTests(unittest.TestCase):
    def setUp(self):
        self.words = [
            {"word": "Gute", "start": 0.1, "end": 0.4, "score": 0.9},
            {"word": "Idee.", "start": 0.6, "end": 0.9, "score": 0.9},
        ]
        self.episode = {"presentation": "social", "social_kind": "exchange",
                        "credit_policy": "publishing_caption", "title": "Ein Ausflug",
                        "branding": "TEST",
                        "cta": ["Mehr Aufgaben und Dialoge", "im DTZ-B1-Sprechbuch", "Amazon-Buchlink im Profil"]}
        self.timeline = {"duration": 1.25, "turns": [
            {"name": "Lea", "text": "Gute Idee.", "start": 0.0, "end": 1.0,
             "wav_duration": 1.0, "words": self.words}
        ]}

    def test_missing_or_interpolated_words_are_rejected(self):
        for words in (self.words[:1], [{**self.words[0], "word": "Andere"}, self.words[1]],
                      [{**self.words[0], "start": math.nan}, self.words[1]],
                      [self.words[0], {**self.words[1], "start": 0.3}]):
            with self.assertRaises(ValueError):
                validate_words(words, "Gute Idee.", 1.0)

    def test_gaps_never_highlight_a_word(self):
        self.assertEqual(active_word(self.words, 0.2), 0)
        self.assertIsNone(active_word(self.words, 0.5))
        self.assertEqual(active_word(self.words, 0.65), 1)
        self.assertIsNone(active_word(self.words, 0.9))

    def test_shared_rectangle_is_inside_the_official_template_gutters(self):
        self.assertGreaterEqual(SAFE[0], 80)
        self.assertGreaterEqual(SAFE[1], 160)
        self.assertLessEqual(SAFE[2], 520)
        self.assertLessEqual(SAFE[3], 840)

    def test_chunks_preserve_every_word_and_never_exceed_two_measured_lines(self):
        text = "Dann nehmen wir Essen von zu Hause mit. Passt dir die Abfahrt um zehn?"
        words = [{"word": token} for token in text.split()]
        result = chunks(words)
        self.assertEqual([word for chunk in result for word in chunk], words)
        for chunk in result:
            self.assertLessEqual(len(measured_lines(" ".join(item["word"] for item in chunk), 31)), 2)

    def test_oversize_unbreakable_word_fails(self):
        with self.assertRaises(ValueError):
            measured_lines("W" * 80, 31)

    def test_opening_hook_is_compact_bottom_anchored_and_dtz_specific(self):
        episode = json.loads((ROOT / "episode_v4.json").read_text())
        for text in (episode["hook"], episode["promo"]["hook"]):
            with self.subTest(text=text):
                self.assertIn("DTZ B1", text)
                data = {**self.episode, "social_kind": "promo", "outro_seconds": 0, "hook": text}
                bounds = hook_bounds(data)
                self.assertEqual(bounds[3], 742)
                self.assertGreaterEqual(bounds[1], 650)
                row = editorial_rows(data)["hook"][0]
                self.assertEqual(row[1], bounds[1] + 10)
                ass = make_ass(data, {**self.timeline, "duration": 4, "turns": [
                    {**self.timeline["turns"][0], "start": 2.5, "end": 3.5}]})
                self.assertIn(f"m 96 {bounds[1]} l 504 {bounds[1]} 504 742 96 742", ass)
                self.assertNotIn("m 96 350", ass)
        with self.assertRaisesRegex(ValueError, "four lines"):
            hook_bounds({"hook": "Noch mehr Text " * 10})

    def test_readable_page_holds_text_without_highlighting_pauses(self):
        episode = {**self.episode, "subtitle_mode": "readable"}
        timeline = {**self.timeline, "duration": 2.5}
        pages = caption_pages(episode, timeline)
        self.assertEqual([(page["start"], page["end"]) for page in pages], [(0, 2.5)])
        ass = make_ass(episode, timeline)
        for interval in ("0:00:00.00,0:00:00.10", "0:00:00.40,0:00:00.60", "0:00:00.90,0:00:02.50"):
            held = [line for line in ass.splitlines() if interval in line and "\\fs31" in line]
            self.assertTrue(held)
            self.assertNotIn("50E5FF", "".join(held))
            self.assertIn("Gute", "".join(held))
            self.assertIn("Idee.", "".join(held))
        self.assertIn("50E5FF", ass)
        with tempfile.TemporaryDirectory() as directory:
            build = Path(directory)
            write_caption_timing(build, episode, timeline)
            self.assertIn("00:00:00,000 --> 00:00:02,500", (build / "subtitles.srt").read_text())

    def test_readable_pages_preserve_words_and_enforce_actual_dwell_and_rate(self):
        text = "Dann nehmen wir Essen von zu Hause mit. Passt dir die Abfahrt um zehn?"
        words = [{"word": word, "start": index * 0.45 + 0.1, "end": index * 0.45 + 0.4}
                 for index, word in enumerate(text.split())]
        pages = readable_pages(words, 10, 18)
        self.assertEqual([word for page in pages for word in page["words"]], words)
        for page in pages:
            dwell = page["end"] - page["start"]
            self.assertGreaterEqual(dwell + 1e-9, MIN_PAGE_SECONDS)
            self.assertLessEqual(len(page["text"]) / dwell, MAX_PAGE_CPS)
            self.assertLessEqual(len(measured_lines(page["text"], 31)), 3)
        for a, b in zip(pages, pages[1:]):
            self.assertEqual(a["end"], b["start"])

    def test_readable_pages_never_relax_limits_or_truncate_audio(self):
        with self.assertRaisesRegex(ValueError, "minimum"):
            readable_pages(self.words, 0, 1.25)
        with self.assertRaisesRegex(ValueError, "minimum"):
            readable_pages(self.words, 0.02, 1.82)
        with self.assertRaisesRegex(ValueError, "truncate"):
            readable_pages(self.words, 0, 0.8)

    def test_amazon_cta_has_no_extra_heading_or_sample_copy(self):
        episode = {**self.episode, "social_kind": "promo", "outro_seconds": 6}
        ass = make_ass(episode, {**self.timeline, "duration": 10})
        self.assertIn("Amazon-Buchlink im Profil", ass)
        self.assertNotIn("DEIN NÄCHSTER SCHRITT", ass)
        self.assertNotIn("Leseprobe", ass)

    def test_examiner_caption_panel_does_not_cover_the_lower_framed_mouth(self):
        episode = {**self.episode, "subtitle_mode": "readable"}
        timeline = {**self.timeline, "duration": 2.5,
                    "turns": [{**self.timeline["turns"][0], "camera": "examiner"}]}
        ass = make_ass(episode, timeline)
        self.assertIn("m 96 612 l 504 612 504 746 96 746", ass)
        self.assertIn("\\pos(104,650)\\fs29", ass)

    def test_speaker_camera_holds_until_next_turn_and_rejects_early_reactions(self):
        turns = [{"id": str(index + 1).zfill(2), "name": name, "camera": camera,
                  "start": start, "end": end, "start_frame": round(start * 24), "end_frame": round(end * 24)}
                 for index, (name, camera, start, end) in enumerate((
                     ("Examiner", "wide", 1, 4), ("Examiner", "examiner", 5, 10),
                     ("Lea", "candidate_a", 12, 18), ("Samir", "candidate_b", 19, 26)))]
        timeline = {"turns": turns, "fps": 24, "duration": 30}
        shots = camera_shots({"outro_seconds": 2}, timeline)
        names = {"wide": "01 Wide", "examiner": "02 Examiner", "candidates": "03 Two-shot",
                 "candidate_a": "04 Lea", "candidate_b": "05 Samir"}
        markers = [{"frame": 1 + round(t * 24), "camera": names[name]} for t, name in shots]
        self.assertTrue(verify_speaker_cameras(markers, timeline)["all_turns_hold_their_camera"])
        self.assertEqual(camera_at_frame(markers, 1 + round(18.9 * 24)), "04 Lea")
        self.assertEqual(camera_at_frame(markers, 1 + 19 * 24), "05 Samir")
        with self.assertRaisesRegex(ValueError, "Camera leaves"):
            verify_speaker_cameras(markers + [{"frame": 1 + round(17.2 * 24), "camera": "05 Samir"}], timeline)

    def test_social_credit_policy_must_be_explicit(self):
        with self.assertRaises(ValueError):
            make_ass({**self.episode, "credit_policy": "none"}, self.timeline)
        ass = make_ass(self.episode, self.timeline)
        self.assertIn("50E5FF", ass)
        self.assertNotIn("Snow Rig", ass)
        self.assertNotIn("Rain Rig", ass)

    def test_publication_retains_sources_license_and_modifications(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            write_publication(path, self.episode)
            text = (path / "publishing_caption.txt").read_text()
            for phrase in ("Snow Rig", "Rain Rig", "CC BY 4.0", "umgefärbt",
                           "https://creativecommons.org/licenses/by/4.0/"):
                self.assertIn(phrase, text)

    def test_entrance_path_has_exact_endpoints(self):
        points = [(0, 0, 0), (0, -2, 0), (1, -2, 0)]
        self.assertEqual(path_at(points, 0)[0], points[0])
        self.assertEqual(path_at(points, 1)[0], points[-1])

    def test_promo_keeps_exact_audio_with_odd_source_frame_boundaries(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, build = root / "build_v4", root / "promo"
            (source / "frames").mkdir(parents=True)
            starts, length, total = (51, 252, 453), 192, 960
            turns = []
            screenplay = []
            for index, start in enumerate(starts):
                line = {"id": str(index + 3).zfill(2), "speaker": "candidate_a",
                        "name": "Lea", "text": "Gute Idee.", "pause_after": 0.375}
                screenplay.append(line)
                turns.append({**line, "start_frame": start, "end_frame": start + length,
                              "start": start / 24, "end": (start + length) / 24,
                              "wav_duration": 8.0, "words": self.words, "alignment_key": "synthetic"})
            timeline = {"turns": turns, "fps": 24, "total_frames": total, "duration": total / 24,
                        "word_alignment": {"test_fixture": True}}
            episode = json.loads((ROOT / "episode_v4.json").read_text())
            episode["turns"] = screenplay
            (root / "episode_v4.json").write_text(json.dumps(episode))
            (source / "timeline.json").write_text(json.dumps(timeline))
            manifest = {"motion_step": 2, "episode": episode, "timeline": timeline}
            (source / "scene_manifest.json").write_text(json.dumps(manifest))
            (source / "studio.blend").write_bytes(b"Explicit synthetic fixture, not a scene")
            from render import scene_hash
            (source / "frames_manifest.json").write_text(json.dumps(
                {"scene": manifest, "blend_sha256": scene_hash(source)}))
            image = source / "plate.png"
            Image.new("RGB", (90, 160), "gray").save(image)
            for frame in range(1, total + 1, 2):
                os.link(image, source / "frames" / f"frame_{frame:04d}.png")
            samples = (b"\x01\x00\x02\x00" * (total * 1000))
            with wave.open(str(source / "dialogue.wav"), "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(48000)
                output.writeframes(samples)
            with patch("produce_v4.ROOT", root), patch("render.mux"):
                promo(build)
            with wave.open(str(build / "dialogue.wav"), "rb") as excerpt:
                self.assertEqual(excerpt.getnframes(), 798 * 2000)
                self.assertFalse(any(excerpt.readframes(60 * 2000)))
                self.assertEqual(excerpt.readframes(594 * 2000), samples[51 * 4000:645 * 4000])
                self.assertFalse(any(excerpt.readframes(144 * 2000)))
            manifest = json.loads((build / "scene_manifest.json").read_text())
            self.assertEqual(manifest["derived_edit"]["source_start_frame_zero_based"], 51)
            self.assertEqual(manifest["derived_edit"]["source_stop_frame_exclusive"], 645)
            self.assertTrue((build / "frames" / "frame_0061.png").exists())

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
    def test_low_resolution_social_mux_upscales_and_delivers_credits_separately(self):
        from PIL import Image
        from render import mux, scene_hash

        with tempfile.TemporaryDirectory() as directory:
            build = Path(directory)
            (build / "frames").mkdir()
            screenplay = {"name": "Lea", "text": "Gute Idee."}
            episode = {**self.episode, "fps": 24, "turns": [screenplay]}
            timeline = {**self.timeline, "fps": 24, "total_frames": 30}
            manifest = {"episode": episode, "timeline": timeline,
                        "width": 90, "height": 160, "motion_step": 2}
            for name, value in (("episode.json", episode), ("timeline.json", timeline),
                                ("scene_manifest.json", manifest)):
                (build / name).write_text(json.dumps(value))
            (build / "studio.blend").write_bytes(b"Synthetic social mux fixture, not a Blender scene")
            (build / "frames_manifest.json").write_text(json.dumps(
                {"scene": manifest, "blend_sha256": scene_hash(build)}))
            image = build / "plate.png"
            Image.new("RGB", (90, 160), "gray").save(image)
            for frame in range(1, 31, 2):
                os.link(image, build / "frames" / f"frame_{frame:04d}.png")
            with wave.open(str(build / "dialogue.wav"), "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(48000)
                output.writeframes(b"".join(struct.pack("<h", round(2000 * math.sin(index / 30)))
                                            for index in range(60000)))
            mux(build, build / "episode.json")
            report = json.loads((build / "media_report.json").read_text())
            video = next(stream for stream in report["streams"] if stream["codec_type"] == "video")
            self.assertEqual((video["width"], video["height"], int(video["nb_frames"])), (720, 1280, 30))
            self.assertTrue((build / "publishing_caption.txt").is_file())
            self.assertFalse((build / "credits.ass").exists())
            self.assertNotIn("Snow Rig", (build / "captions.ass").read_text())

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg required")
    def test_every_actual_caption_raster_fits_and_unsafe_state_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            build = Path(directory)
            ass = make_ass(self.episode, self.timeline)
            report = audit_ass(build, ass)
            self.assertTrue(report["all_inside"])
            self.assertGreater(report["states_checked"], 5)
            self.assertEqual(tuple(report["safe_rectangle"]), SAFE)
            unsafe = ass + "Dialogue: 0,0:00:00.00,0:00:01.00,Text,,0,0,0,,{\\pos(0,0)}Unsafe\n"
            with self.assertRaisesRegex(ValueError, "Unsafe rendered"):
                audit_ass(build, unsafe)
            overlapping = ass + "Dialogue: 0,0:00:00.00,0:00:01.00,Text,,0,0,0,,{\\pos(104,212)\\fs18}Overlap\n"
            with self.assertRaisesRegex(ValueError, "Simultaneously visible text overlaps"):
                audit_ass(build, overlapping)


if __name__ == "__main__":
    unittest.main()
