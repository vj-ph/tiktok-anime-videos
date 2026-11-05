import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from long_speaking import (ACCENT, FORMATS, THUMBNAILS, build_contacts, caption_excerpt, compile_script,
                           compose, compose_thumbnail, load_episode, panels, text_box)
from runtime_config import font_path

ROOT = Path(__file__).resolve().parent
EPISODE = ROOT / "episodes" / "oeif_b1_speaking_long.json"


class LongSpeakingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        picture = self.root / "image.png"
        Image.new("RGB", (200, 300), "#bb8b55").save(picture)
        (self.root / "scene.blend").write_bytes(b"fixture")
        (self.root / "book.md").write_text("Book fixture.", encoding="utf-8")
        episode = json.loads(EPISODE.read_text(encoding="utf-8"))
        episode["source"].update(book="book.md", manifest="manifest.jsonl")
        episode["scene"].update(base_scene="scene.blend", wall_logo="image.png")
        episode["promotion"]["cover"] = "image.png"
        episode["promotion"]["pointing_emoji"] = "image.png"
        episode["parts"][1]["picture"] = "image.png"
        tracks = []
        for part in episode["parts"]:
            for selection in part["tracks"]:
                segments = []
                roles = list(selection["roles"])
                if part["number"] == 3 and roles == ["A", "B"]:
                    roles *= 2
                for index, role in enumerate(roles):
                    segments.append({
                        "segment_id": f"{selection['id']}_{index}", "speaker_label": role,
                        "text_original": f"Original sentence {index}.",
                        "text_tts": f"Spoken sentence {index}.", "voice_id": "original_voice",
                    })
                tracks.append({"track_id": selection["id"], "source_line": 20,
                               "section": f"Teil {part['number']}: Fixture", "segments": segments})
        (self.root / "manifest.jsonl").write_text(
            "\n".join(json.dumps(track) for track in tracks), encoding="utf-8")
        self.path = self.root / "episode.json"
        self.path.write_text(json.dumps(episode), encoding="utf-8")
        self.episode = load_episode(self.path)

    def test_complete_source_segments_are_retained_without_invented_timestamps(self):
        script = compile_script(self.episode)
        tracks = [json.loads(line) for line in Path(self.episode["source"]["manifest"]).read_text().splitlines()]
        expected = [s for track in tracks for s in track["segments"]]
        actual = [t for t in script["turns"] if "source_track" in t]
        self.assertEqual([s["segment_id"] for s in expected], [t["id"] for t in actual])
        self.assertEqual([s["text_original"] for s in expected], [t["text"] for t in actual])
        self.assertEqual([s["text_tts"] for s in expected], [t["text_tts"] for t in actual])
        self.assertEqual("candidate_b", actual[0]["speaker"])
        self.assertEqual(self.episode["title"], script["turns"][0]["text"])
        self.assertTrue(all("start" not in turn and "words" not in turn for turn in script["turns"]))
        self.assertEqual("cta", script["turns"][-1]["kind"])

    def test_wrong_part_track_and_unmapped_speaker_fail(self):
        for mutation in ("wrong_part", "unmapped"):
            episode = copy.deepcopy(self.episode)
            if mutation == "wrong_part":
                episode["parts"][0]["tracks"][0]["id"] = episode["parts"][1]["tracks"][0]["id"]
            else:
                episode["parts"][0]["tracks"][0]["roles"] = {}
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                compile_script(episode)

    def test_caption_samples_end_at_sentence_boundaries_and_keep_full_script(self):
        text = "This is the first sentence. This is the longer second sentence."
        self.assertEqual("This is the first sentence.", caption_excerpt(text, 35))
        self.assertEqual(text, caption_excerpt(text, 100))

    def test_opening_overview_uses_the_configured_part_labels(self):
        review = panels(self.episode, compile_script(self.episode))
        self.assertIn("2 · Bildbeschreibung", review[0]["body"])
        self.episode["parts"][1]["title"] = "Bildbeschreibung und Nachfragen"
        review = panels(self.episode, compile_script(self.episode))
        self.assertIn("2 · Bildbeschreibung und Nachfragen", review[0]["body"])

    def test_user_short_link_is_preserved_and_untrusted_hosts_are_rejected(self):
        self.assertEqual("https://amzn.eu/d/0ctWX9v4", self.episode["promotion"]["amazon_url"])
        episode = json.loads(self.path.read_text())
        episode["promotion"]["amazon_url"] = "https://amazon.example/dp/B0H3NWBWKW"
        self.path.write_text(json.dumps(episode), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Amazon product link"):
            load_episode(self.path)

    def test_two_layouts_keep_promotion_outside_speaker_and_caption_panels(self):
        if not font_path().is_file():
            self.skipTest("Project fonts not installed.")
        script = compile_script(self.episode)
        review = panels(self.episode, script)
        self.assertEqual(12, len(review))
        for mode, layout in FORMATS.items():
            box = layout["scene"]
            native = self.root / f"{mode}.png"
            Image.new("RGB", (box[2] - box[0], box[3] - box[1]), "#407050").save(native)
            crops = []
            for panel in review:
                with self.subTest(mode=mode, panel=panel["id"]):
                    image, check = compose(self.episode, panel, mode, native)
                    self.assertEqual(layout["size"], image.size)
                    self.assertEqual(self.episode["promotion"][mode], check["persistent_cta"])
                    self.assertEqual(1, check["cover_count"])
                    if check["promo_group"]:
                        crops.append(image.crop(layout["cover"]).tobytes() + image.crop(layout["cta"]).tobytes())
                        if mode == "social":
                            self.assertGreaterEqual(image.height - layout["promo"][3], 370)
                            for text in check["text"]:
                                if text["box"][1] < layout["promo"][1]:
                                    self.assertLess(text["box"][3], layout["promo"][1])
                    else:
                        self.assertEqual("12_final_cta", panel["id"])
                    safe = layout["safe"]
                    for text in check["text"]:
                        x0, y0, x1, y1 = text["box"]
                        self.assertTrue(safe[0] <= x0 < x1 <= safe[2])
                        self.assertTrue(safe[1] <= y0 < y1 <= safe[3])
            self.assertTrue(all(crop == crops[0] for crop in crops))

    def test_disclaimers_are_not_drawn_and_final_cta_has_no_duplicate_promo(self):
        if not font_path().is_file():
            self.skipTest("Project fonts not installed.")
        for mode, layout in FORMATS.items():
            episode = copy.deepcopy(self.episode)
            if mode == "social":
                episode["promotion"]["pointing_emoji"] = str(self.root / "must_not_be_opened.png")
            box = layout["scene"]
            native = Image.new("RGB", (box[2] - box[0], box[3] - box[1]))
            for panel in panels(episode, compile_script(episode)):
                image, check = compose(episode, panel, mode, native)
                drawn = " ".join(line for text in check["text"] for line in text["lines"])
                self.assertNotIn("Werbung", drawn)
                self.assertNotIn("keine offizielle", drawn)
                self.assertNotIn("Unabhängige", drawn)
                self.assertEqual(int(mode == "youtube"), sum("emoji" in text for text in check["text"]))
                for text in check["text"]:
                    if "emoji" in text:
                        icon = text["emoji"]["box"]
                        self.assertEqual(10, text["box"][0] - icon[2])
                        self.assertEqual(check["cta_box"][0], icon[0])
                        self.assertTrue(check["cta_box"][1] <= icon[1] < icon[3] <= check["cta_box"][3])
                        self.assertEqual((187, 139, 85), image.getpixel(
                            ((icon[0] + icon[2]) // 2, (icon[1] + icon[3]) // 2)))
                if panel["id"] == "12_final_cta":
                    self.assertFalse(check["promo_group"])
                    self.assertIn("Mehr Aufgaben und Modelldialoge", drawn)
                    self.assertIn(self.episode["promotion"][mode], drawn)
                    self.assertNotIn("DEIN NÄCHSTER", drawn)
                    self.assertEqual(1, check["cover_count"])

    def test_highlight_sample_draws_an_active_word_without_inventing_timing(self):
        if not font_path().is_file():
            self.skipTest("Project fonts not installed.")
        layout = FORMATS["youtube"]
        box = layout["scene"]
        native = Image.new("RGB", (box[2] - box[0], box[3] - box[1]))
        panel = panels(self.episode, compile_script(self.episode))[2]
        image, check = compose(self.episode, panel, "youtube", native)
        highlighted = next(text for text in check["text"] if "highlighted_word" in text)
        self.assertEqual("sentence", highlighted["highlighted_word"])
        self.assertEqual("illustrative_unmeasured", highlighted["highlight_kind"])
        colors = image.crop(highlighted["box"]).getcolors(maxcolors=1_000_000)
        self.assertTrue(any(color == tuple(bytes.fromhex(ACCENT[1:])) for _, color in colors))
        self.assertEqual("forced_alignment", compile_script(self.episode)["subtitle_alignment"]["timing"])

    def test_group_thumbnail_layout_uses_all_four_characters_and_original_logo(self):
        if not font_path().is_file():
            self.skipTest("Project fonts not installed.")
        for mode, layout in THUMBNAILS.items():
            box = layout["scene"]
            native = self.root / f"group_{mode}.png"
            Image.new("RGB", (box[2] - box[0], box[3] - box[1]), "#407050").save(native)
            image, check = compose_thumbnail(self.episode, mode, native)
            self.assertEqual(FORMATS[mode]["size"], image.size)
            self.assertEqual(4, len(check["cast"]))
            self.assertEqual((187, 139, 85), image.getpixel(
                ((layout["logo"][0] + layout["logo"][2]) // 2,
                 (layout["logo"][1] + layout["logo"][3]) // 2)))
            self.assertEqual([self.episode["thumbnail"]["subtitle"], self.episode["thumbnail"]["title"]],
                             [" ".join(text["lines"]) for text in check["text"]])

    def test_overflow_is_rejected_not_silently_truncated(self):
        from PIL import ImageDraw
        if not font_path().is_file():
            self.skipTest("Project fonts not installed.")
        draw = ImageDraw.Draw(Image.new("RGB", (100, 100)))
        with self.assertRaises(ValueError):
            text_box(draw, "This will not fit in the reserved area.", (0, 0, 20, 20))

    def test_contacts_never_overwrite_an_existing_build(self):
        output = self.root / "existing"
        output.mkdir()
        sentinel = output / "pilot.mp4"
        sentinel.write_bytes(b"preserve")
        with self.assertRaisesRegex(ValueError, "fresh dedicated"):
            build_contacts(self.path, output)
        self.assertEqual(b"preserve", sentinel.read_bytes())

    def test_pipeline_routes_contacts_without_short_video_preflight_or_synthesis(self):
        import pipeline
        with patch("sys.argv", ["pipeline.py", "contacts", "--episode", str(self.path),
                                "--build", str(self.root / "review"),
                                "--qwen-python", pipeline.sys.executable]), \
                patch("long_speaking.build_contacts") as contacts, \
                patch("pipeline.preflight", side_effect=AssertionError("short-video preflight")), \
                patch("pipeline.build_episode", side_effect=AssertionError("video build")):
            pipeline.main()
        contacts.assert_called_once()


if __name__ == "__main__":
    unittest.main()
