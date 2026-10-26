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

    def test_dressing_assets_are_copied_and_hashed_in_frozen_delivery(self):
        episode = self.dressed()
        with tempfile.TemporaryDirectory() as temp:
            build = Path(temp)
            for name in ("pilot.mp4", "pilot_clean.mp4", "captions.ass", "subtitles.srt", "dialogue.wav",
                         "timeline.json", "scene_manifest.json", "frames_manifest.json",
                         "publishing_caption.txt", "CREDITS.txt", "subtitle_timing_report.json",
                         "safe_zone_report.json", "delivery_checks.json"):
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
