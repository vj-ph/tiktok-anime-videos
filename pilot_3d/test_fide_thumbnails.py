import json
import unittest

from PIL import Image

from fide_thumbnails import CLIPS, ROOT, SOCIAL_CROPS, SOCIAL_SAFE, SOURCE, contains, head_boxes, render, source_still


class FideThumbnailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (SOURCE / "timeline.json").is_file():
            raise unittest.SkipTest("Local verified fide source stills are required.")
        cls.timeline = json.loads((SOURCE / "timeline.json").read_text(encoding="utf-8"))
        cls.receipts = json.loads((SOURCE / "native_reuse.json").read_text(encoding="utf-8"))
        with Image.open(ROOT / "assets" / "flags" / "switzerland.png") as image:
            cls.flag = image.convert("RGB")

    def test_youtube_complete_title_flag_and_all_native_faces(self):
        native, receipt, _ = source_still("fide_01", self.timeline, self.receipts)
        image, check = render(native, receipt, self.flag)
        self.assertEqual((1920, 1080), image.size)
        text = " ".join(" ".join(c["lines"]) for c in check["text"][1:])
        self.assertEqual("fide A2-B1 Sprechen Prüfungssimulation", text)
        self.assertEqual({h["actor"] for h in receipt["head_bounds"]},
                         {h["actor"] for h in check["heads"]})
        x0, y0, x1, y1 = check["swiss_flag_box"]
        self.assertEqual((255, 255, 255), image.getpixel(((x0 + x1) // 2, (y0 + y1) // 2)))
        self.assertGreater(image.getpixel((x0 + 10, y0 + 10))[0], 200)

    def test_three_social_designs_survive_all_crops_without_face_or_title_clipping(self):
        for index, (_, turn_id, title, hooks) in enumerate(CLIPS, 1):
            native, receipt, _ = source_still(turn_id, self.timeline, self.receipts)
            image, check = render(native, receipt, self.flag, index=index, title=title, hooks=hooks)
            self.assertEqual((1080, 1920), image.size)
            for box in check["critical_boxes"]:
                self.assertTrue(contains(SOCIAL_SAFE, box))
                self.assertTrue(all(contains(crop, box) for crop in SOCIAL_CROPS.values()))
            self.assertEqual(["candidate_a"], [h["actor"] for h in check["heads"]])
            self.assertIn(f"Video {index}/3", [" ".join(c["lines"]) for c in check["text"]])
            badge, heading = check["text"][1:3]
            self.assertEqual([f"Video {index}/3"], badge["lines"])
            self.assertGreaterEqual(badge["font_size"], .8 * heading["font_size"])
            self.assertLessEqual(badge["box"][3], heading["box"][1])
            self.assertTrue(all(c["box"][3] <= check["scene_box"][1]
                                for c in check["text"]))

    def test_rejects_a_crop_that_would_clip_native_hair(self):
        native, receipt, _ = source_still("fide_31", self.timeline, self.receipts)
        with self.assertRaisesRegex(ValueError, "clips a head or hair"):
            head_boxes(receipt, native.size, (280, 200, 920, 580), (112, 750, 884, 1224))


if __name__ == "__main__":
    unittest.main()
