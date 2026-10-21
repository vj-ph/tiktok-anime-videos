import array
import copy
import json
import tempfile
import unittest
import wave
from pathlib import Path

from polish_exchange import MOUTH_POSES, exchange_inputs, mouth_pose, prepare, source_fingerprints
from render import captions, load_inputs, mux, scene_hash
from unittest.mock import patch


def fixture():
    lines = [
        {"id": "05", "speaker": "candidate_a", "name": "Lea", "text": "Passt dir zehn?", "camera": "candidates"},
        {"id": "06", "speaker": "candidate_b", "name": "Samir", "text": "Ja, das passt.", "camera": "candidate_b"},
    ]
    episode = {"fps": 24, "turns": lines, "label": "DTZ B1", "intro_seconds": 4, "outro_seconds": 4}
    turns = [
        {**line, "start_frame": start, "end_frame": end, "start": start / 24,
         "end": end / 24, "duration": (end - start) / 24, "wav_duration": (end - start) / 24,
         "mouth_cues": [{"start": 0, "end": (end - start) / 24, "value": "B"}]}
        for line, start, end in zip(lines, (10, 30), (20, 40))
    ]
    return episode, {"fps": 24, "duration": 12, "turns": turns}


class ExchangeTests(unittest.TestCase):
    def test_excerpt_is_ten_seconds_and_does_not_mutate_source(self):
        episode, timeline = fixture()
        before = copy.deepcopy((episode, timeline))
        result, clock, start, stop = exchange_inputs(episode, timeline)
        self.assertEqual((episode, timeline), before)
        self.assertEqual(stop - start, 240)
        self.assertEqual(clock["total_frames"], 240)
        self.assertEqual(clock["turns"][0]["start_frame"], 6)
        self.assertEqual(clock["turns"][0]["camera"], "candidate_a")
        self.assertEqual(result["presentation"], "exchange")
        self.assertEqual(result["turns"][0]["camera"], "candidate_a")

    def test_missing_or_out_of_bounds_dialogue_fails(self):
        episode, timeline = fixture()
        with self.assertRaises(ValueError):
            exchange_inputs(episode, {**timeline, "turns": timeline["turns"][:1]})
        timeline["turns"][0]["start_frame"] = 1
        with self.assertRaises(ValueError):
            exchange_inputs(episode, timeline)

    def test_closed_lips_remain_closed_at_short_cue_center(self):
        cues = [
            {"start": 0, "end": 0.1, "value": "D"},
            {"start": 0.1, "end": 0.15, "value": "A"},
            {"start": 0.15, "end": 0.3, "value": "B"},
        ]
        self.assertEqual(mouth_pose(cues, 0.125), MOUTH_POSES["A"])
        self.assertEqual(mouth_pose(cues, -0.1), MOUTH_POSES["X"])
        self.assertEqual(mouth_pose(cues, 0.31), MOUTH_POSES["X"])
        self.assertLess(mouth_pose(cues, 0.11)[0], MOUTH_POSES["D"][0])
        self.assertEqual(mouth_pose(cues, 3 / 24), MOUTH_POSES["A"])
        short_cues = [{"start": 0.41, "end": 0.46, "value": "A"}]
        self.assertEqual(mouth_pose(short_cues, 10 / 24), MOUTH_POSES["A"])

    def test_rounding_and_opening_have_distinct_native_targets(self):
        self.assertLess(MOUTH_POSES["F"][1], MOUTH_POSES["C"][1])
        self.assertGreater(MOUTH_POSES["F"][2], MOUTH_POSES["C"][2])
        self.assertGreater(MOUTH_POSES["D"][0], MOUTH_POSES["B"][0])
        for pose in MOUTH_POSES.values():
            self.assertTrue(0 <= pose[0] < 0.2)
            self.assertTrue(0.65 <= pose[1] <= 1.1)

    def test_compact_captions_have_no_promotion_or_end_card(self):
        episode, timeline, _, _ = exchange_inputs(*fixture())
        result = captions(episode, timeline)
        self.assertIn("Passt dir zehn?", result)
        self.assertIn("Snow Rig (CC)", result)
        self.assertIn("Rain Rig (CC)", result)
        self.assertIn("Es spricht: Samir", result)
        self.assertNotIn("JETZT SELBST", result)
        self.assertNotIn(",Card,", result)

    def test_prepare_crops_exact_samples_and_preserves_source(self):
        with tempfile.TemporaryDirectory() as directory:
            source, build = Path(directory) / "v2", Path(directory) / "v3"
            source.mkdir()
            episode, timeline = fixture()
            (source / "scene_manifest.json").write_text(json.dumps({"episode": episode, "timeline": timeline}))
            for name in ("studio.blend", "pilot.mp4", "pilot_clean.mp4"):
                (source / name).write_bytes(b"Explicit unit-test fixture, not a media file")
            pcm = array.array("h", (index % 30001 for index in range(12 * 48000))).tobytes()
            with wave.open(str(source / "dialogue.wav"), "wb") as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(48000)
                audio.writeframes(pcm)
            before = source_fingerprints(source)
            prepare(source, build)
            self.assertEqual(source_fingerprints(source), before)
            with wave.open(str(build / "dialogue.wav"), "rb") as audio:
                self.assertEqual(audio.getnframes(), 480000)
                self.assertEqual(audio.readframes(480000), pcm[4 * 2000 * 2:244 * 2000 * 2])
            actual_episode, actual_timeline = load_inputs(build, build / "episode.json")
            self.assertEqual(actual_episode["presentation"], "exchange")
            self.assertEqual(actual_timeline["duration"], 10)

    def test_presentation_rejects_unknown_modes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            episode, timeline = fixture()
            episode["presentation"] = "typo"
            (root / "episode.json").write_text(json.dumps(episode))
            (root / "timeline.json").write_text(json.dumps(timeline))
            with self.assertRaises(ValueError):
                load_inputs(root, root / "episode.json")

    def test_exchange_mux_does_not_require_a_book_cover(self):
        episode, timeline, _, _ = exchange_inputs(*fixture())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "studio.blend").write_bytes(b"Explicit synthetic fixture")
            (root / "scene_manifest.json").write_text(json.dumps({
                "episode": episode, "timeline": timeline, "motion_step": 1, "width": 720, "height": 1280,
            }))
            manifest = json.loads((root / "scene_manifest.json").read_text())
            (root / "frames_manifest.json").write_text(json.dumps({"scene": manifest, "blend_sha256": scene_hash(root)}))
            report = {"streams": [
                {"codec_type": "video", "nb_frames": "240", "width": 720, "height": 1280, "codec_name": "h264"},
                {"codec_type": "audio", "sample_rate": "48000", "channels": 1, "codec_name": "aac"},
            ], "format": {"duration": "10"}}
            with patch("render.load_inputs", return_value=(episode, timeline)), \
                 patch("render.valid_frame", return_value=True), \
                 patch("render.run") as run, \
                 patch("render.subprocess.run") as probe:
                probe.return_value.stdout = json.dumps(report)
                mux(root)
            self.assertEqual(run.call_count, 2)
            self.assertNotIn("-loop", run.call_args_list[0].args[0])


if __name__ == "__main__":
    unittest.main()
