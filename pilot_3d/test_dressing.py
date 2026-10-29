"""Portable configuration, provenance and frozen-asset regression checks."""

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from episode_config import read_episode, validate_template
from pipeline import SOURCES, freeze_delivery
from prepare_audio import sha256_file
from scene_dressing import ASSETS, asset_files, validate_dressing

ROOT = Path(__file__).resolve().parent


class DressingTests(unittest.TestCase):
    def setUp(self):
        self.episode = read_episode(ROOT / "episodes/lerntreffen_dtz.json")
        self.config = json.loads((ASSETS / "austria.json").read_text(encoding="utf-8"))

    def dressed(self):
        episode = copy.deepcopy(self.episode)
        episode["scene"]["dressing"] = copy.deepcopy(self.config)
        return episode

    def canadian(self):
        episode = read_episode(ROOT / "episodes/tef_canada_b1_short.json")
        episode["scene"]["dressing"] = json.loads((ASSETS / "canada.json").read_text(encoding="utf-8"))
        return episode

    def halloween(self):
        return read_episode(ROOT / "episodes/dtz_b1_halloween_fest.json")

    def test_legacy_episodes_need_no_dressing_assets_or_new_settings(self):
        for path in (ROOT / "episodes").glob("*.json"):
            episode = read_episode(path)
            if "dressing" not in episode.get("scene", {}):
                before = copy.deepcopy(episode)
                self.assertEqual(validate_dressing(episode, check_assets=True), {})
                self.assertEqual(asset_files(episode), [])
                self.assertEqual(episode, before)

    def test_opt_in_configuration_is_valid_and_not_mutated(self):
        episode = self.dressed()
        before = copy.deepcopy(episode)
        validate_template(episode)
        validate_dressing(episode, check_assets=True)
        self.assertEqual(episode, before)
        self.assertIn("scene_dressing.py", SOURCES)

    def test_rejects_malformed_unknown_and_misplaced_settings(self):
        invalid = [
            None, [], {"unknown": []}, {"props": None}, {"accessories": {}},
            {"props": [None]}, {"props": [{"type": []}]},
            {"props": [{"type": "strudel", "anchor": "table_corner"}]},
            {"props": [{"type": "coffee_set", "anchor": "table_corner"}]},
            {"props": [{"type": "flag", "anchor": "back_wall_left", "pattern": "unknown"}]},
            {"props": [{"type": "flag", "anchor": "back_wall_left", "pattern": "austria", "size": 99}]},
            {"accessories": [{"type": "hat", "style": "alpine", "actor": "missing"}]},
            {"accessories": [{"type": "hat", "style": "other", "actor": "candidate_b"}]},
        ]
        for config in invalid:
            with self.subTest(config=config):
                episode = self.dressed()
                episode["scene"]["dressing"] = config
                with self.assertRaises(ValueError):
                    validate_template(episode)

    def test_duplicate_anchors_and_accessories_are_rejected(self):
        for group in ("props", "accessories"):
            episode = self.dressed()
            episode["scene"]["dressing"][group].append(copy.deepcopy(self.config[group][0]))
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                validate_dressing(episode)

    def test_inactive_actor_and_backpack_anchor_are_rejected(self):
        episode = self.dressed()
        episode["scene"].update(layout="interview", observer=False)
        with self.assertRaisesRegex(ValueError, "active candidate_b"):
            validate_dressing(episode)
        episode["scene"]["dressing"]["props"] = []
        with self.assertRaisesRegex(ValueError, "active scene actor"):
            validate_dressing(episode)

    def test_selected_files_are_pinned_self_contained_and_commercially_reusable(self):
        files = asset_files(self.dressed(), verify=True)
        self.assertEqual({p.name for p in files},
                         {"provenance.json", "tea_set_01_1k.blend", "pixor-library-backpack.glb"})
        catalog = json.loads(files[0].read_text(encoding="utf-8"))
        self.assertTrue(all(record["license"] == "CC0-1.0" for record in catalog["assets"].values()))
        self.assertLess(sum(p.stat().st_size for p in files), 2_000_000)
        procedural = self.dressed()
        procedural["scene"]["dressing"]["props"] = [self.config["props"][0]]
        self.assertEqual(asset_files(procedural), [])

    def test_asset_modification_is_rejected_before_scene_building(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "provenance.json").write_bytes((ASSETS / "provenance.json").read_bytes())
            (root / "pixor-library-backpack.glb").write_bytes(b"changed")
            with patch("scene_dressing.ASSETS", root), self.assertRaisesRegex(ValueError, "checksum"):
                asset_files(self.dressed(), verify=True)

    def test_canadian_dressing_is_explicit_and_preserves_interview_cast_and_speech(self):
        config = self.canadian()["scene"]["dressing"]
        for name in ("tef_canada_a1", "tef_canada_a1_short", "tef_canada_b1_short"):
            episode = read_episode(ROOT / "episodes" / f"{name}.json")
            before = copy.deepcopy(episode)
            validate_template(episode)
            validate_dressing(episode, check_assets=True)
            self.assertEqual(episode, before)
            self.assertEqual(episode["scene"]["dressing"], config)
            self.assertEqual(episode["scene"]["layout"], "interview")
            self.assertEqual({turn["speaker"] for turn in episode["turns"]}, {"candidate_a", "examiner"})
        self.assertTrue(all(item["pattern"] == "austria" for item in self.config["props"]
                            if item["type"] == "flag"))

    def test_canadian_artwork_is_pinned_complete_and_correctly_proportioned(self):
        from PIL import Image
        import xml.etree.ElementTree as ET

        episode = self.canadian()
        files = asset_files(episode, verify=True)
        self.assertEqual({path.name for path in files},
                         {"canada.provenance.json", "canada-flag.png", "canada-flag.svg"})
        self.assertEqual(len(files), 3)
        self.assertLess(sum(path.stat().st_size for path in files), 20_000)
        record = json.loads((ASSETS / "canada.provenance.json").read_text(encoding="utf-8"))["assets"]["canada_flag"]
        self.assertEqual(record["license"], "Public domain (PD-ineligible)")
        self.assertIn("MapGrid", record["authors"])
        with Image.open(ASSETS / record["file"]) as image:
            self.assertEqual(image.size, (1280, 640))
            rgb = image.convert("RGB")
            self.assertEqual(rgb.getpixel((100, 320)), (213, 43, 30))
            self.assertEqual(rgb.getpixel((1180, 320)), (213, 43, 30))
            self.assertEqual(rgb.getpixel((350, 100)), (255, 255, 255))
            self.assertEqual(rgb.getpixel((640, 320)), (213, 43, 30))
        vector = ET.parse(ASSETS / record["source_file"]).getroot()
        self.assertEqual(vector.attrib["viewBox"], "0 0 9600 4800")
        self.assertEqual({element.tag.rsplit("}", 1)[-1] for element in vector.iter()}, {"svg", "path", "title"})

    def test_canadian_png_and_vector_tampering_are_rejected(self):
        files = asset_files(self.canadian(), verify=True)
        for damaged in ("canada-flag.png", "canada-flag.svg"):
            with self.subTest(damaged=damaged), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                for source in files:
                    (root / source.name).write_bytes(source.read_bytes())
                (root / damaged).write_bytes(b"changed")
                with patch("scene_dressing.ASSETS", root), self.assertRaisesRegex(ValueError, "checksum"):
                    asset_files(self.canadian(), verify=True)

    def test_canadian_and_original_props_select_only_their_own_assets(self):
        episode = self.dressed()
        episode["scene"]["dressing"]["props"][0]["pattern"] = "canada"
        files = asset_files(episode, verify=True)
        self.assertEqual({path.name for path in files},
                         {"provenance.json", "tea_set_01_1k.blend", "pixor-library-backpack.glb",
                          "canada.provenance.json", "canada-flag.png", "canada-flag.svg"})
        plain = copy.deepcopy(self.episode)
        plain["scene"].pop("dressing", None)
        with patch("scene_dressing.ASSETS", Path("missing-optional-assets")):
            self.assertEqual(asset_files(plain, verify=True), [])

    def test_dressing_assets_are_copied_and_hashed_in_frozen_delivery(self):
        episode = self.dressed()
        self.assert_frozen_assets(episode)

    def test_canadian_assets_are_copied_and_hashed_in_frozen_delivery(self):
        self.assert_frozen_assets(self.canadian())

    def test_halloween_assets_are_selected_verified_and_frozen(self):
        episode = self.halloween()
        validate_template(episode, check_assets=True)
        expected = {"halloween.provenance.json", "halloween-jackolantern.glb",
                    "halloween-candy-pail.glb", "halloween-sweets.glb",
                    "halloween-bat.glb", "halloween-witch-hat.glb"}
        self.assertEqual({path.name for path in asset_files(episode, verify=True)}, expected)
        self.assert_frozen_assets(episode)

    def test_halloween_rejects_missing_candidate_and_tampered_asset(self):
        episode = self.halloween()
        episode["scene"].update(layout="interview", observer=False)
        with self.assertRaisesRegex(ValueError, "active candidate"):
            validate_dressing(episode)
        episode = self.halloween()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for path in asset_files(episode):
                (root / path.name).write_bytes(path.read_bytes())
            (root / "halloween-witch-hat.glb").write_bytes(b"damaged")
            with patch("scene_dressing.ASSETS", root), self.assertRaisesRegex(ValueError, "checksum"):
                asset_files(episode, verify=True)

    def test_natural_hair_and_caption_clear_placement_are_explicit_and_scoped(self):
        episode = self.halloween()
        dressing = episode["scene"]["dressing"]
        hat = dressing["accessories"][0]
        sweets = next(item for item in dressing["props"] if item["type"] == "halloween_sweets")
        validate_dressing(episode, check_assets=True)
        legacy = copy.deepcopy(episode)
        del legacy["scene"]["dressing"]["accessories"][0]["fit"]
        del next(item for item in legacy["scene"]["dressing"]["props"]
                 if item["type"] == "halloween_sweets")["placement"]
        validate_dressing(legacy, check_assets=True)
        for value in ("unknown", None, 1):
            with self.subTest(fit=value):
                hat["fit"] = value
                with self.assertRaisesRegex(ValueError, "Natural-hair fit"):
                    validate_dressing(episode)
        hat["fit"] = "natural_hair"
        for field, value in (("actor", "candidate_a"), ("style", "alpine")):
            with self.subTest(field=field):
                old = hat[field]
                hat[field] = value
                with self.assertRaisesRegex(ValueError, "Natural-hair fit"):
                    validate_dressing(episode)
                hat[field] = old
        sweets["placement"] = "unknown"
        with self.assertRaisesRegex(ValueError, "Unsupported options"):
            validate_dressing(episode)

    def assert_frozen_assets(self, episode):
        with tempfile.TemporaryDirectory() as temp:
            build = Path(temp)
            for name in ("pilot.mp4", "pilot_clean.mp4", "captions.ass", "subtitles.srt", "dialogue.wav",
                         "timeline.json", "scene_manifest.json", "frames_manifest.json",
                         "publishing_caption.txt", "CREDITS.txt", "subtitle_timing_report.json",
                         "safe_zone_report.json", "delivery_checks.json", "picture_timing_report.json"):
                (build / name).write_bytes(b"synthetic freeze test")
            (build / "episode.json").write_text(json.dumps(episode), encoding="utf-8")
            freeze_delivery(build)
            manifest = json.loads((build / "export_manifest.json").read_text(encoding="utf-8"))
            for path in asset_files(episode):
                name = "dressing_assets/" + path.name
                self.assertEqual(sha256_file(build / name), sha256_file(path))
                self.assertEqual(manifest["files_sha256"][name], sha256_file(path))
            self.assertEqual(manifest["source_sha256"]["scene_dressing.py"],
                             sha256_file(build / "source_export/scene_dressing.py"))


if __name__ == "__main__":
    unittest.main()
