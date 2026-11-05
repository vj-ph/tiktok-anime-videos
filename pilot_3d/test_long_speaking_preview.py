import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from long_speaking import FORMATS, compose
from long_speaking_preview import (caption_pages, display_state, encoded_highlight_fraction,
                                   caption_words, load_preview, native_plan, native_sample)
import test_long_speaking as fixtures


class PreviewTimingTests(unittest.TestCase):
    def setUp(self):
        self.episode = json.loads((Path(__file__).parent / "episodes" /
                                  "oeif_b1_speaking_long_preview.json").read_text(encoding="utf-8"))
        self.turn = {
            **self.episode["turns"][0], "start": 0, "start_frame": 0, "wav_duration": 5,
            "words": [{"word": token, "start": i * .4 + .05, "end": i * .4 + .3, "score": .9}
                      for i, token in enumerate(self.episode["turns"][0]["text"].split())],
        }
        self.timeline = {"fps": 24, "total_frames": 144, "turns": [self.turn]}

    def test_title_maps_only_actual_aligned_tokens_including_abbreviations(self):
        for frame, expected in ((0, None), (2, 0), (23, 0), (28, None), (31, 1), (119, None)):
            with self.subTest(frame=frame):
                self.assertEqual(expected, display_state(self.episode, self.timeline, frame)[3])
        self.turn["words"][0]["word"] = "invented"
        with self.assertRaisesRegex(ValueError, "changed transcript"):
            display_state(self.episode, self.timeline, 2)

    def test_pages_preserve_all_words_and_switch_on_measured_boundaries(self):
        text = self.episode["turns"][4]["text"]
        pages = caption_pages({"text": text})
        self.assertEqual(list(range(len(text.split()))), [i for start, end in pages for i in range(start, end)])
        self.assertEqual(10, pages[0][1])
        turn = {**self.turn, "kind": "model", "text": text, "wav_duration": 10,
                "words": [{"word": token, "start": i * .4 + .05, "end": i * .4 + .3, "score": .9}
                          for i, token in enumerate(text.split())]}
        timeline = {**self.timeline, "turns": [turn]}
        self.assertEqual((0, 10), display_state(self.episode, timeline, 97)[1:3])
        self.assertEqual((10, len(text.split())), display_state(self.episode, timeline, 98)[1:3])

    def test_motion_samples_restart_at_camera_cuts_not_global_frame_zero(self):
        turn = {"start_frame": 7}
        self.assertEqual(7, native_sample(turn, 7, 3))
        self.assertEqual(7, native_sample(turn, 9, 3))
        self.assertEqual(10, native_sample(turn, 10, 3))

    def test_native_plan_skips_photo_and_cta_but_covers_both_formats(self):
        storyboard = {}
        timeline = {"total_frames": 20, "turns": [
            {"start_frame": 0, "panel_id": "01_opening"},
            {"start_frame": 7, "panel_id": "05_teil2_picture"},
            {"start_frame": 12, "panel_id": "12_final_cta"},
        ]}
        with patch("long_speaking_preview.compile_script"), patch("long_speaking_preview.panels",
                return_value=[{"id": "01_opening", "camera": "wide"}]):
            plan = native_plan(self.episode, storyboard, timeline)
        self.assertEqual(6, len(plan))
        self.assertEqual({"youtube", "social"}, {p["format"] for p in plan})
        self.assertEqual({0, 3, 6}, {p["frame"] for p in plan})

    def test_pipeline_routes_preview_without_standard_short_template(self):
        import pipeline
        import sys
        with patch("sys.argv", ["pipeline.py", "build", "--episode", "preview.json",
                                "--build", "review", "--qwen-python", sys.executable]), \
                patch("pathlib.Path.read_text", return_value='{"template":"long_speaking_preview"}'), \
                patch("long_speaking_preview.load_preview", return_value=(self.episode, {})), \
                patch("long_speaking_preview.build_preview") as build, \
                patch("pipeline.build_episode", side_effect=AssertionError("wrong template")):
            pipeline.main()
        build.assert_called_once()


class PreviewOverlayTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg not installed.")
    def test_compressed_small_word_passes_but_unhighlighted_word_is_rejected(self):
        from PIL import Image, ImageDraw, ImageFont
        from runtime_config import font_path

        frames, cases = [], []
        for word, size, x in (("Teil", 17, 32), ("Auf", 14, 0), ("Wer", 14, 1),
                              ("Wie", 14, 0), ("Die", 14, 1), ("Nach", 14, 0)):
            font = ImageFont.truetype(str(font_path()), size)
            for color in ("#e7bb67", "#f7f4e9"):
                image = Image.new("RGB", (640, 80), "#101e27")
                draw = ImageDraw.Draw(image)
                draw.text((x, 20), word, fill=color, font=font)
                draw.text((x + draw.textlength(word + " ", font=font), 20),
                          "dem Bild sehe ich eine Familie in der Küche.",
                          fill="#f7f4e9", font=font)
                frames.append(image)
            cases.append(word)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "words.mp4"
            subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                            "-s", "640x80", "-r", "24", "-i", "pipe:0", "-c:v", "libx264",
                            "-crf", "22", "-g", "1", "-pix_fmt", "yuv420p", str(path)],
                           input=b"".join(frame.tobytes() for frame in frames), check=True)
            decoded = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(path),
                                      "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
                                     capture_output=True, check=True).stdout
        stride = 640 * 80 * 3
        for index, word in enumerate(cases):
            with self.subTest(word=word):
                start = index * 2 * stride
                positive = Image.frombytes("RGB", (640, 80), decoded[start:start + stride])
                negative = Image.frombytes("RGB", (640, 80),
                                           decoded[start + stride:start + 2 * stride])
                self.assertGreaterEqual(encoded_highlight_fraction(frames[index * 2], positive), .6)
                self.assertLess(encoded_highlight_fraction(frames[index * 2], negative), .1)

    def test_real_highlight_is_not_marked_as_an_illustrative_style_sample(self):
        from PIL import Image
        fixture = fixtures.LongSpeakingTests()
        fixture.setUp()
        try:
            from long_speaking import compile_script, panels
            panel = panels(fixture.episode, compile_script(fixture.episode))[2]
            box = FORMATS["youtube"]["scene"]
            native = Image.new("RGB", (box[2] - box[0], box[3] - box[1]))
            _, check = compose(fixture.episode, panel, "youtube", native,
                               sample_highlights=False, active_word=0)
            marked = next(t for t in check["text"] if "highlighted_word" in t)
            self.assertEqual("Original", marked["highlighted_word"])
            self.assertEqual("forced_alignment", marked["highlight_kind"])
            _, check = compose(fixture.episode, panel, "youtube", native,
                               sample_highlights=False, active_word=None)
            self.assertFalse(any("highlighted_word" in t for t in check["text"]))
        finally:
            fixture.doCleanups()


class FullPreviewTests(unittest.TestCase):
    def test_times_and_numbers_map_only_to_their_actual_spoken_tokens(self):
        from long_speaking_full_preview import pronunciation
        display, text, groups = pronunciation("Treffen um 18:15.")
        self.assertEqual("Treffen um 18:15.", display)
        self.assertEqual("Treffen um achtzehn Uhr fünfzehn.", text)
        self.assertEqual([[0], [1], [2, 3, 4]], groups)
        turn = {"text": text, "display_text": display, "display_word_groups": groups,
                "kind": "model", "start_frame": 0, "start": 0, "wav_duration": 3,
                "words": [{"word": word, "start": i * .4 + .05, "end": i * .4 + .3, "score": .9}
                          for i, word in enumerate(text.split())]}
        timeline = {"fps": 24, "turns": [turn]}
        for frame, expected in ((20, None), (21, 2), (45, 2), (46, None)):
            self.assertEqual(expected, display_state({}, timeline, frame)[3])
        self.assertAlmostEqual(1.9, caption_words(turn)[-1]["end"])
        self.assertEqual([(0, 3)], caption_pages(turn))
        turn["display_word_groups"][-1] = [2, 4]
        with self.assertRaisesRegex(ValueError, "exactly"):
            caption_words(turn)
        with self.assertRaisesRegex(ValueError, "Unmapped"):
            pronunciation("Um 17:30.")

    def test_short_preview_cannot_inherit_the_long_duration_exception(self):
        episode = json.loads((Path(__file__).parent / "episodes" /
                              "oeif_b1_speaking_long_preview.json").read_text(encoding="utf-8"))
        episode["source"].update(duration_limit_seconds=900, duration_exception="Not applicable here.")
        with patch("long_speaking_preview.read_episode", return_value=episode):
            with self.assertRaisesRegex(ValueError, "strict 90-second"):
                load_preview(Path(__file__))

    def test_full_review_is_complete_hash_pinned_and_frames_lea_as_lea(self):
        from long_speaking_full_preview import resolve_full_episode
        from prepare_audio import sha256_file
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            script = {"voices": {"examiner": {}, "candidate_a": {}, "candidate_b": {}}, "turns": [
                {"id": "opening", "kind": "opening", "speaker": "examiner", "name": "Prüfer",
                 "text": "B1", "text_tts": "B eins", "display_word_groups": [[0, 1]], "sequence": 1},
                {"id": "teil1_samir_introduction", "part": 1, "kind": "model",
                 "speaker": "candidate_b", "name": "Samir", "text": "Ich bin 28 Jahre alt.", "sequence": 2},
                {"id": "teil1_lea_introduction", "part": 1, "kind": "model",
                 "speaker": "candidate_a", "name": "Lea", "text": "Ich bin 25 Jahre alt.", "sequence": 3},
                {"id": "final_cta", "kind": "cta", "speaker": "examiner", "name": "Prüfer",
                 "text": "Jetzt sprechen!", "sequence": 4}]}
            (root / "script.json").write_text(json.dumps(script), encoding="utf-8")
            (root / "teil1_revision.json").write_text("{}", encoding="utf-8")
            (root / "storyboard.json").write_text("{}", encoding="utf-8")
            digest = sha256_file(root / "script.json")
            (root / "manifest.json").write_text(json.dumps({"files_sha256": {
                "script.json": digest, "teil1_revision.json": sha256_file(root / "teil1_revision.json")}}),
                encoding="utf-8")
            episode = {"title": "B1", "storyboard": "storyboard.json", "review_script": "script.json",
                       "review_manifest": "manifest.json", "review_script_sha256": digest,
                       "source": {"duration_limit_seconds": 900, "duration_exception": "Explicit full request."}}
            resolved = resolve_full_episode(episode, root / "episode.json")
            self.assertEqual([t["id"] for t in script["turns"]], [t["id"] for t in resolved["turns"]])
            self.assertEqual("candidate_a", resolved["turns"][2]["camera"])
            self.assertEqual("Lea · Vorstellung", resolved["turns"][2]["heading"])
            episode["source"]["duration_exception"] = ""
            with self.assertRaisesRegex(ValueError, "authorization"):
                resolve_full_episode(episode, root / "episode.json")
            episode["source"]["duration_exception"] = "Explicit full request."
            (root / "script.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "text changed"):
                resolve_full_episode(episode, root / "episode.json")


if __name__ == "__main__":
    unittest.main()
