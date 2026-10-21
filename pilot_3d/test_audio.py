"""Focused stdlib tests; no Qwen, torch, soundfile or numpy import is needed."""

import copy
import importlib.util
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import wave

import prepare_audio as audio


def episode():
    return {
        "fps": 24, "intro_seconds": 0.01, "outro_seconds": 0.02,
        "voices": {"a": {"audio": "voice.wav", "transcript": "voice.txt"}},
        "turns": [
            {"id": "01", "speaker": "a", "name": "Lea", "text": "Guten Tag.",
             "pause_after": 0.1, "camera": "wide"},
            {"id": "02", "speaker": "a", "name": "Lea", "text": "Bis morgen.",
             "pause_after": 0},
        ],
    }


class ValidationTests(unittest.TestCase):
    def test_valid_episode(self):
        audio.validate_episode(episode())

    def test_rejects_bad_fps(self):
        for value in (0, -1, True, 24.0, 29, float("inf")):
            with self.subTest(value=value):
                data = episode()
                data["fps"] = value
                with self.assertRaisesRegex(ValueError, "fps"):
                    audio.validate_episode(data)

    def test_rejects_unsafe_duplicate_ids_and_unknown_roles(self):
        for changes in ({"id": "../01"}, {"id": "02"}, {"speaker": "missing"},
                        {"id": 1}, {"role": "different"}, {"text": "a\n\nb"}):
            with self.subTest(changes=changes):
                data = episode()
                data["turns"][0].update(changes)
                with self.assertRaises(ValueError):
                    audio.validate_episode(data)

    def test_rejects_nonfinite_or_negative_pauses_and_intro(self):
        for value in (-0.1, float("nan"), float("inf"), True, "0.1"):
            for field in ("intro_seconds", "pause_after"):
                with self.subTest(value=value, field=field):
                    data = episode()
                    (data if field == "intro_seconds" else data["turns"][0])[field] = value
                    with self.assertRaises(ValueError):
                        audio.validate_episode(data)

    def test_rejects_malformed_objects(self):
        for value in (None, [], {"fps": 24}):
            with self.assertRaises(ValueError):
                audio.validate_episode(value)


class TimingTests(unittest.TestCase):
    def test_ceiling_uses_exact_decimal_and_sample_arithmetic(self):
        self.assertEqual(audio.ceil_frames(0.1, 30), 3)
        self.assertEqual(audio.ceil_frames(0.6, 24), 15)
        self.assertEqual(audio.ceil_frames(0, 24), 0)
        self.assertEqual(audio.wav_frames_to_video_frames(24_000, 24_000, 24), 24)
        self.assertEqual(audio.wav_frames_to_video_frames(24_001, 24_000, 24), 25)
        with self.assertRaises(ValueError):
            audio.wav_frames_to_video_frames(0, 24_000, 24)

    def test_timeline_pads_without_truncation_and_keeps_original_fields(self):
        data = episode()
        infos = [
            {"frames": 24_001, "sample_rate": 24_000, "audio": "one.wav"},
            {"frames": 24_000, "sample_rate": 24_000, "audio": "two.wav"},
        ]
        cues = [[{"start": 0, "end": 1, "value": "A"}]] * 2
        timeline = audio.build_timeline(data, infos, cues)
        one, two = timeline["turns"]
        self.assertEqual(one["start_frame"], 1)
        self.assertEqual(one["end_frame"], 26)
        self.assertEqual(one["pause_after_frames"], 3)
        self.assertEqual(two["start_frame"], 29)
        self.assertEqual(two["end_frame"], 53)
        self.assertEqual(timeline["total_frames"], 54)
        self.assertEqual(timeline["duration"], 54 / 24)
        self.assertEqual(one["camera"], "wide")
        self.assertEqual(one["pause_after"], 0.1)
        self.assertGreaterEqual(one["duration"], one["wav_duration"])
        self.assertEqual(one["mouth_cues"][0]["start"], 0)
        self.assertTrue(Path(one["audio"]).is_absolute())
        srt = audio.subtitles(timeline)
        self.assertIn("00:00:00,042 --> 00:00:01,042\nGuten Tag.", srt)
        self.assertIn("00:00:01,208 --> 00:00:02,208\nBis morgen.", srt)

    def test_turn_count_mismatch(self):
        with self.assertRaisesRegex(ValueError, "counts"):
            audio.build_timeline(episode(), [], [])

    def test_srt_carries_milliseconds(self):
        self.assertEqual(audio.srt_timestamp(59.9996), "00:01:00,000")
        self.assertEqual(audio.srt_timestamp(3661.2), "01:01:01,200")

    def test_subtitles_wrap_without_dropping_spoken_words(self):
        text = ("Planen Sie zusammen einen Tagesausflug. Wohin möchten Sie fahren, "
                "und was möchten Sie dort machen?")
        result = audio.subtitles({"turns": [{"text": text, "start": 4, "wav_duration": 5.28}]})
        lines = result.strip().splitlines()[2:]
        self.assertTrue(all(len(line) <= 42 for line in lines))
        self.assertEqual(" ".join(lines), text)


class CueTests(unittest.TestCase):
    def test_valid_relative_cues_and_rhubarb_rounding(self):
        cues = [{"start": 0, "end": 0.5, "value": "X"},
                {"start": 0.5, "end": 1.0, "value": "G"}]
        result = audio.validate_cues(cues, 0.996)
        self.assertEqual(result[-1]["end"], 0.996)
        self.assertEqual(cues[-1]["end"], 1.0)

    def test_invalid_intervals_shapes_and_nonfinite_numbers_fail(self):
        invalid = [
            [], None, [{"start": 0.5, "end": 0.4, "value": "A"}],
            [{"start": -0.1, "end": 0.4, "value": "A"}],
            [{"start": 0, "end": 0.4, "value": "Z"}],
            [{"start": 0, "end": 1.01, "value": "A"}],
            [{"start": 0, "end": float("nan"), "value": "A"}],
            [{"start": 0, "end": 0.6, "value": "A"},
             {"start": 0.5, "end": 0.8, "value": "B"}],
        ]
        for cues in invalid:
            with self.subTest(cues=cues), self.assertRaises(ValueError):
                audio.validate_cues(cues, 1)

    def test_rhubarb_invocation_is_checked_and_uses_phonetic_dialogue(self):
        turn = episode()["turns"][0]
        result = {"metadata": {"duration": 1.0},
                  "mouthCues": [{"start": 0, "end": 1, "value": "B"}]}
        info = {"audio": "/recording.wav", "wav_duration": 1.0079}
        with patch.object(Path, "is_file", return_value=False), \
                patch.object(audio, "sha256_file", return_value="audio-hash"), \
                patch.object(Path, "read_text", return_value=json.dumps(result)), \
                patch.object(audio, "atomic_text") as dialog, \
                patch.object(audio, "atomic_json") as save, \
                patch.object(audio.subprocess, "run") as run, \
                patch("builtins.print"):
            cues = audio.run_rhubarb(turn, info, Path("/audio"), Path("/rhubarb"), "binary-hash", 4)
        self.assertEqual(cues, result["mouthCues"])
        command = run.call_args.args[0]
        self.assertTrue(run.call_args.kwargs["check"])
        self.assertEqual(command[command.index("-r") + 1], "phonetic")
        self.assertEqual(command[command.index("-f") + 1], "json")
        self.assertEqual(command[command.index("--extendedShapes") + 1], "GHX")
        self.assertEqual(command[command.index("-d") + 1], "/audio/01.txt")
        self.assertEqual(command[-1], "/recording.wav")
        dialog.assert_called_once_with(Path("/audio/01.txt"), "Guten Tag.\n")
        self.assertEqual(save.call_count, 2)


class CacheTests(unittest.TestCase):
    def test_default_clone_model_is_the_requested_1_7b_base(self):
        self.assertEqual(audio.MODEL, "Qwen/Qwen3-TTS-12Hz-1.7B-Base")

    def test_explicit_synthesis_settings_and_conservative_token_budget(self):
        with patch.object(audio.importlib.metadata, "version", return_value="test-version"):
            settings = audio.synthesis_settings("qwen-base", "cpu", 4, "Guten Tag.")
        self.assertEqual(settings["dtype"], "float32")
        self.assertTrue(settings["do_sample"])
        self.assertTrue(settings["subtalker_dosample"])
        self.assertTrue(settings["non_streaming_mode"])
        self.assertEqual(settings["language"], "German")
        self.assertEqual(settings["seed"], 0)
        self.assertGreaterEqual(settings["max_new_tokens"], 256)
        self.assertEqual(settings["threads"], 4)

    def test_hash_includes_reference_bytes_transcript_model_and_settings(self):
        turn = episode()["turns"][0]
        settings = {"model": "qwen-base", "do_sample": False, "threads": 4}
        raw = {"voice.wav": b"original audio", "voice.txt": b"Guten Tag."}

        def read_bytes(path):
            return raw[path.name]

        def file_hash(path):
            import hashlib
            return hashlib.sha256(read_bytes(path)).hexdigest()

        with patch.object(audio, "sha256_file", side_effect=file_hash), \
                patch.object(Path, "read_text", lambda self, **kw: read_bytes(self).decode()):
            def key(current_settings=settings):
                return audio.content_hash(audio.make_cache_payload(
                    turn, Path("voice.wav"), Path("voice.txt"), current_settings))

            original = key()
            for filename in ("voice.wav", "voice.txt"):
                old = raw[filename]
                raw[filename] += b" changed"
                self.assertNotEqual(original, key())
                raw[filename] = old
            for name, value in (("model", "other"), ("do_sample", True), ("threads", 2)):
                changed = copy.deepcopy(settings)
                changed[name] = value
                self.assertNotEqual(original, key(changed))
            turn["text"] = "Neuer Text."
            self.assertNotEqual(original, key())

    def test_canonical_order_and_nan_rejection(self):
        self.assertEqual(audio.content_hash({"b": 2, "a": 1}), audio.content_hash({"a": 1, "b": 2}))
        with self.assertRaises(ValueError):
            audio.content_hash({"bad": float("nan")})

    def test_cache_hit_and_malformed_metadata_regeneration(self):
        payload = {"test": 1}
        info = {"frames": 24_000, "sample_rate": 24_000, "wav_duration": 1.0}
        metadata = {
            "cache_key": audio.content_hash(payload), "payload": payload,
            "audio_info": info, "wav_sha256": "abc",
        }
        with patch.object(Path, "exists", return_value=True), \
                patch.object(Path, "is_file", return_value=True), \
                patch.object(audio, "inspect_wav", return_value=info), \
                patch.object(audio, "sha256_file", return_value="abc"), \
                patch.object(Path, "read_text", return_value=json.dumps(metadata)):
            self.assertEqual(audio.load_audio_cache(Path("speech.wav"), payload), info)
            with patch.object(Path, "read_text", return_value="{broken"), \
                    patch("builtins.print") as notify:
                self.assertIsNone(audio.load_audio_cache(Path("speech.wav"), payload))
                notify.assert_called_once()
            with patch.object(audio, "sha256_file", return_value="changed"):
                with patch("builtins.print"):
                    self.assertIsNone(audio.load_audio_cache(Path("speech.wav"), payload))
            with patch.object(audio, "inspect_wav", side_effect=wave.Error("truncated")):
                with patch("builtins.print"):
                    self.assertIsNone(audio.load_audio_cache(Path("speech.wav"), payload))

    def test_partial_cache_is_not_reused(self):
        with patch.object(Path, "exists", return_value=True), \
                patch.object(Path, "is_file", return_value=False), \
                patch("builtins.print") as notify:
            self.assertIsNone(audio.load_audio_cache(Path("speech.wav"), {}))
            notify.assert_called_once()

    def test_speech_import_is_verified_read_only_and_rejects_another_model(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source_dir, target_dir = root / "source", root / "target"
            source_dir.mkdir()
            target_dir.mkdir()
            source = source_dir / "01-voice.wav"
            source.write_bytes(WavTests.recording())
            payload = {"model": audio.MODEL, "reference_sha256": "reference", "text": "Guten Tag."}
            info = audio.inspect_wav(source)
            metadata = source.with_suffix(".cache.json")
            audio.atomic_json(metadata, {
                "cache_key": audio.content_hash(payload), "payload": payload, "audio_info": info,
                "wav_sha256": audio.sha256_file(source)})
            before = (source.read_bytes(), metadata.read_bytes())
            target = target_dir / source.name
            with patch("builtins.print"):
                self.assertIsNone(audio.import_audio_cache(source_dir, target, {**payload, "model": "other"}))
            self.assertFalse(target.exists())
            self.assertEqual(audio.import_audio_cache(source_dir, target, payload), info)
            self.assertEqual(audio.load_audio_cache(target, payload), info)
            self.assertEqual((source.read_bytes(), metadata.read_bytes()), before)
            self.assertEqual(target.read_bytes(), source.read_bytes())

    def test_import_does_not_require_torch(self):
        spec = importlib.util.spec_from_file_location("audio_pure_test", audio.__file__)
        module = importlib.util.module_from_spec(spec)
        original_import = __import__

        def guarded_import(name, *args, **kwargs):
            if name.split(".")[0] in {"torch", "qwen_tts", "numpy", "soundfile"}:
                raise AssertionError(f"Heavy import during pure tests: {name}")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=guarded_import):
            spec.loader.exec_module(module)
            module.validate_episode(episode())


class WavTests(unittest.TestCase):
    @staticmethod
    def recording(*, channels=1, samples=b"\x01\x00" * 100):
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as output:
            output.setnchannels(channels)
            output.setsampwidth(2)
            output.setframerate(24_000)
            output.writeframes(samples)
        return buffer.getvalue()

    def inspect_bytes(self, data):
        original_open = wave.open
        with patch.object(audio.wave, "open", side_effect=lambda path, mode: original_open(io.BytesIO(data), mode)):
            return audio.inspect_wav(Path("virtual.wav"))

    def test_measures_sample_count(self):
        info = self.inspect_bytes(self.recording())
        self.assertEqual(info["frames"], 100)
        self.assertEqual(info["sample_rate"], 24_000)
        self.assertEqual(info["wav_duration"], 100 / 24_000)

    def test_rejects_silence_stereo_and_truncation(self):
        for data in (
            self.recording(samples=bytes(200)),
            self.recording(channels=2),
            self.recording()[:-4],
        ):
            with self.subTest(length=len(data)), self.assertRaises(ValueError):
                self.inspect_bytes(data)


class EdgeQuietTests(unittest.TestCase):
    @staticmethod
    def pcm(values):
        return struct.pack("<" + "h" * len(values), *values)

    def bounds(self, values, settings=None):
        return audio.quiet_trim_bounds(self.pcm(values), 1000, settings or audio.preprocessing_settings())

    def test_trims_only_excessive_edges_with_180ms_padding(self):
        values = [0] * 1000 + [1000] * 100 + [0] * 2000 + [-1000] * 100 + [0] * 1000
        result = self.bounds(values)
        self.assertEqual(result["start_sample"], 820)
        self.assertEqual(result["end_sample_exclusive"], 3380)
        kept = values[result["start_sample"]:result["end_sample_exclusive"]]
        self.assertEqual(kept, [0] * 180 + values[1000:3200] + [0] * 180)
        self.assertEqual(result["removed_lead_samples"], 820)
        self.assertEqual(result["removed_tail_samples"], 820)
        self.assertEqual(result["padding_samples"], 180)

    def test_lead_and_tail_limits_are_strict_not_inclusive(self):
        result = self.bounds([0] * 500 + [1000] * 100 + [0] * 800)
        self.assertEqual(result["start_sample"], 0)
        self.assertEqual(result["end_sample_exclusive"], 1400)
        result = self.bounds([0] * 501 + [1000] * 100 + [0] * 801)
        self.assertEqual(result["start_sample"], 321)
        self.assertEqual(result["end_sample_exclusive"], 781)

    def test_short_edges_and_signed_full_scale_samples_are_not_cropped(self):
        values = [0] * 100 + [-32768, 32767] + [0] * 200
        result = self.bounds(values)
        self.assertEqual(result["start_sample"], 0)
        self.assertEqual(result["end_sample_exclusive"], len(values))

    def test_threshold_is_sample_based_and_low_level_noise_is_quiet(self):
        result = self.bounds([184, -184] * 500 + [185, -185] + [0] * 100)
        self.assertEqual(result["quiet_threshold_pcm16"], 184)
        self.assertEqual(result["first_active_sample"], 1000)
        self.assertEqual(result["start_sample"], 820)
        self.assertEqual(result["last_active_sample_exclusive"], 1002)

    def test_rejects_all_quiet_incomplete_samples_and_invalid_settings(self):
        for pcm in (bytes(2000), b"", b"\x00"):
            with self.subTest(length=len(pcm)), self.assertRaises(ValueError):
                audio.quiet_trim_bounds(pcm, 1000, audio.preprocessing_settings())
        for threshold in (True, float("nan"), float("inf"), -10, -100):
            settings = audio.preprocessing_settings()
            settings["quiet_threshold_dbfs"] = threshold
            with self.subTest(threshold=threshold), self.assertRaises(ValueError):
                self.bounds([1000] * 100, settings)
        for rate in (0, -1, True):
            with self.assertRaises(ValueError):
                audio.quiet_trim_bounds(self.pcm([1000]), rate, audio.preprocessing_settings())

    def test_preprocessing_hash_changes_with_raw_source_and_each_setting(self):
        settings = audio.preprocessing_settings()
        values = [0] * 1000 + [1000] * 100 + [0] * 1000
        info = {"frames": len(values), "sample_rate": 1000, "wav_duration": len(values) / 1000}
        bounds = self.bounds(values)
        payload = audio.preprocessing_payload("raw-sha", info, settings, bounds)
        original = audio.content_hash(payload)
        altered = audio.preprocessing_payload("changed-raw-sha", info, settings, bounds)
        self.assertNotEqual(original, audio.content_hash(altered))
        for field in settings:
            changed = copy.deepcopy(payload)
            changed["settings"][field] = str(changed["settings"][field]) + "-changed"
            with self.subTest(field=field):
                self.assertNotEqual(original, audio.content_hash(changed))

    def test_refuses_repeated_trimming_of_prepared_audio(self):
        for raw in (
            {"audio": "already.prepared.wav"},
            {"audio": "already.wav", "preprocessing": {}},
        ):
            with self.assertRaisesRegex(ValueError, "raw synthesis"):
                audio.prepare_turn_audio("01", raw, Path("/audio"))

    def test_timeline_exposes_original_raw_provenance(self):
        data = episode()
        infos = [
            {"frames": 1000, "sample_rate": 1000, "audio": "prepared.wav",
             "raw_audio": "/raw.wav", "raw_sample_count": 2000, "raw_wav_duration": 2,
             "preprocessing": {"sample_bounds": {"start_sample": 1000}}},
        ] * 2
        cues = [[{"start": 0, "end": 1, "value": "A"}]] * 2
        timeline = audio.build_timeline(data, infos, cues)
        for turn in timeline["turns"]:
            self.assertEqual(turn["raw_audio"], "/raw.wav")
            self.assertEqual(turn["raw_wav_duration"], 2)
            self.assertEqual(turn["preprocessing"]["sample_bounds"]["start_sample"], 1000)
            self.assertEqual(turn["wav_duration"], 1)


if __name__ == "__main__":
    unittest.main()
