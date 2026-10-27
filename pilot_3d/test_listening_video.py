import json
import math
import shutil
import struct
import subprocess
import sys
import unittest
import wave
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import listening_video as listening
import pipeline
from listener_motion import listener_offsets
from PIL import Image, ImageDraw
from prepare_audio import atomic_json, content_hash, inspect_wav, make_cache_payload, sha256_file


def episode():
    return {
        "fps": 24,
        "scene": {},
        "question": "Warum ruft die Arztpraxis an?",
        "choices": ["Eine Bewertung", "Der Termin wurde verschoben", "Eine Rechnung"],
        "correct_choice": "B",
        "answer_text": "Richtig ist B. Der Termin wurde auf Freitag verschoben.",
        "key_detail": "Freitag, 11 Uhr",
        "timing": {"hook_seconds": 3, "reading_seconds": 7, "response_seconds": 6,
                   "reveal_seconds": 8, "cta_seconds": 6},
        "source": {"duration_limit_seconds": 90},
    }


def write_wav(path, frames=24000):
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(24000)
        audio.writeframes(b"\x01\x00" * frames)


def reuse_fixture(root):
    data = episode()
    files = {name: root / name for name in ("book_audio.wav", "voice.wav", "voice.txt", "book_cover.jpg")}
    write_wav(files["book_audio.wav"])
    write_wav(files["voice.wav"])
    files["voice.txt"].write_text("Reference text.", encoding="utf-8")
    Image.new("RGB", (4, 6), "white").save(files["book_cover.jpg"])
    sources = {name: {"path": str(path), "sha256": sha256_file(path)} for name, path in files.items()}
    source = root / "preview"
    (source / "inputs").mkdir(parents=True)
    (source / "audio").mkdir()
    for name, path in files.items():
        shutil.copyfile(path, source / "inputs" / name)
    for name, text in (("answer", data["answer_text"]), ("hook", data["question"])):
        recording = source / "audio" / f"{name}-fixture.wav"
        write_wav(recording)
        payload = make_cache_payload({"speaker": "narrator", "text": text},
                                     files["voice.wav"], files["voice.txt"], {"model": "fixture"})
        atomic_json(recording.with_suffix(".cache.json"),
                    {"payload": payload, "cache_key": content_hash(payload),
                     "wav_sha256": sha256_file(recording), "audio_info": inspect_wav(recording)})
    answer, hook = (source / "audio" / f"{name}-fixture.wav" for name in ("answer", "hook"))
    timeline = listening.timeline_for(data, inspect_wav(files["book_audio.wav"]), inspect_wav(answer),
                                      inspect_wav(hook))
    video = source / "pilot.mp4"
    video.write_bytes(b"fixture video")
    atomic_json(source / "episode.json", data)
    atomic_json(source / "timeline.json", timeline)
    atomic_json(source / "listening_state.json", {"episode": data, "profile": "preview", "sources": sources})
    atomic_json(source / "delivery_checks.json",
                {"timeline": timeline, "source_sha256": sources, "output_sha256": sha256_file(video),
                 "answer_audio_sha256": sha256_file(answer), "hook_audio_sha256": sha256_file(hook)})
    return data, files, sources, source, answer, timeline


class ListeningVideoTest(unittest.TestCase):
    def test_load_validates_section_choices_questions_and_excerpt_bounds(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            for name in ("book.wav", "voice.wav"):
                write_wav(root / name)
            for name in ("voice.txt", "book.md", "scene.blend", "device.glb"):
                (root / name).write_bytes(b"fixture")
            Image.new("RGB", (4, 6), "white").save(root / "cover.jpg")
            atomic_json(root / "device.json", {"sha256": sha256_file(root / "device.glb")})
            data = episode()
            data.update(schema_version=1, id="fixture", language="de", title="Fixture",
                        exam={"family": "dtz", "skill": "listening", "section": "2"},
                        audio="book.wav", book_cover="cover.jpg",
                        voice={"audio": "voice.wav", "transcript": "voice.txt"},
                        scene={"source": "scene.blend", "camera_prefix": "04",
                               "pose_frame": 1, "cycle_frames": 5,
                               "playback_device": {"model": "device.glb", "provenance": "device.json",
                                                   "table_position": [0, 0]}})
            data["source"]["book"] = "book.md"
            path = root / "episode.json"

            def validate():
                atomic_json(path, data)
                return listening.load_episode(path)

            data["audio_excerpt"] = {"start_sample": 3, "end_sample": 23999}
            validate()
            data["audio_excerpt"]["end_sample"] = 24001
            with self.assertRaisesRegex(ValueError, "audio_excerpt"):
                validate()
            data["audio_excerpt"]["end_sample"] = 23999
            data["exam"]["section"] = "4"
            with self.assertRaisesRegex(ValueError, "six|6"):
                validate()
            data["choices"] = ["a", "b", "c", "d", "e", "f"]
            data["correct_choice"] = "F"
            validate()
            data["exam"]["section"] = "3"
            data["questions"] = [
                {"number": 10, "prompt": "One?", "choices": ["yes", "no"], "correct_choice": "B"},
                {"number": 11, "prompt": "Two?", "choices": ["a", "b", "c"], "correct_choice": "C"},
            ]
            validate()
            data["questions"][1]["number"] = 10
            with self.assertRaisesRegex(ValueError, "numbers must differ"):
                validate()
            data["questions"][1]["number"] = 11
            data["questions"][1]["correct_choice"] = "F"
            with self.assertRaisesRegex(ValueError, "correct_choice"):
                validate()

    def test_excerpt_copies_exact_samples_and_rejects_tampering(self):
        with TemporaryDirectory() as directory:
            build = Path(directory)
            (build / "inputs").mkdir()
            source = build / "inputs" / "book_audio.wav"
            samples = bytes(range(256)) * 20
            with wave.open(str(source), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(24000)
                wav.writeframes(samples)
            data = {"audio_excerpt": {"start_sample": 37, "end_sample": 2011}}
            target = listening.book_audio_file(data, build, create=True)
            with wave.open(str(target), "rb") as wav:
                self.assertEqual(wav.getnframes(), 1974)
                self.assertEqual(wav.readframes(1974), samples[37 * 2:2011 * 2])
            self.assertEqual(listening.book_audio_file(data, build, create=False), target)
            with wave.open(str(target), "rb") as wav:
                params, original = wav.getparams(), wav.readframes(wav.getnframes())
            with wave.open(str(target), "wb") as wav:
                wav.setparams(params)
                wav.writeframes(bytes([original[0] ^ 1]) + original[1:])
            with self.assertRaisesRegex(ValueError, "differs"):
                listening.book_audio_file(data, build, create=True)
            data["audio_excerpt"]["end_sample"] = 99999
            with self.assertRaisesRegex(ValueError, "exceeds"):
                listening.book_audio_file(data, build, create=False)

    def test_reuse_checks_excerpt_against_master_and_delivery_hash(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            data, files, sources, source, answer, _ = reuse_fixture(root)
            data["audio_excerpt"] = {"start_sample": 100, "end_sample": 18000}
            excerpt = listening.book_audio_file(data, source, create=True)
            hook = source / "audio" / "hook-fixture.wav"
            timeline = listening.timeline_for(data, inspect_wav(excerpt), inspect_wav(answer), inspect_wav(hook))
            atomic_json(source / "episode.json", data)
            atomic_json(source / "timeline.json", timeline)
            atomic_json(source / "listening_state.json", {"episode": data, "profile": "preview", "sources": sources})
            report_path = source / "delivery_checks.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report.update(timeline=timeline, book_audio_sha256=sha256_file(excerpt))
            atomic_json(report_path, report)
            with patch.object(listening, "audio_delivery_check") as check:
                listening.audio_reuse_spec(source, root / "production", data, files, sources)
                self.assertEqual(check.call_args.args[1], excerpt)
                report["book_audio_sha256"] = "0" * 64
                atomic_json(report_path, report)
                with self.assertRaisesRegex(ValueError, "excerpt checksum"):
                    listening.audio_reuse_spec(source, root / "production", data, files, sources)

    def test_new_part_layouts_show_every_choice_without_early_answer(self):
        with TemporaryDirectory() as directory:
            cover = Path(directory) / "cover.jpg"
            Image.new("RGB", (4, 6), "white").save(cover)
            for section in ("2", "3", "4"):
                data = episode()
                data["exam"] = {"section": section}
                if section == "3":
                    data["questions"] = [
                        {"number": 10, "prompt": "The first question", "choices": ["yes", "no"], "correct_choice": "B"},
                        {"number": 11, "prompt": "The second question", "choices": ["cancel", "move", "call"], "correct_choice": "B"},
                    ]
                elif section == "4":
                    data["choices"] = ["first", "second", "third", "fourth", "fifth", "sixth"]
                with self.subTest(section=section):
                    with patch.object(listening, "draw_wrapped", wraps=listening.draw_wrapped) as draw:
                        image = listening.make_overlay(data, "listening", cover)
                        text = " ".join(call.args[1] for call in draw.call_args_list)
                    self.assertIsNone(image.getchannel("A").crop((0, 186, 720, 520)).getbbox())
                    self.assertNotIn(data["answer_text"], text)
                    self.assertNotIn(data["key_detail"], text)
                    expected = ([choice for item in data["questions"] for choice in item["choices"]]
                                if section == "3" else data["choices"])
                    for choice in expected:
                        self.assertIn(choice, text)
                    with patch.object(listening, "draw_wrapped", wraps=listening.draw_wrapped) as draw:
                        listening.make_overlay(data, "reveal", cover)
                        text = " ".join(call.args[1] for call in draw.call_args_list)
                    if section == "3":
                        self.assertNotIn(data["answer_text"], text)
                    else:
                        self.assertIn(data["answer_text"], text)
                    self.assertIn(data["key_detail"], text)
                    if section == "3":
                        self.assertIn("10  B", text)
                        self.assertIn("11  B", text)

    def test_authored_teil3_reveal_uses_digits_and_does_not_repeat_answers(self):
        path = Path(__file__).parent / "episodes" / "dtz_b1_listening_teil3_termin.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        with patch.object(listening, "draw_wrapped", wraps=listening.draw_wrapped) as draw:
            listening.make_overlay(data, "reveal", Path("unused"))
        strings = [call.args[1] for call in draw.call_args_list]
        self.assertEqual(sum(text.startswith("10  B  falsch") for text in strings), 1)
        self.assertEqual(sum(text.startswith("11  B  Sie verschieben") for text in strings), 1)
        self.assertNotIn(data["answer_text"], strings)
        self.assertIn("10:", data["answer_text"])
        self.assertIn("11:", data["answer_text"])

    def test_production_settings_and_native_crop_preserve_preview_framing(self):
        self.assertEqual(listening.render_settings("preview"), {"width": 360, "height": 640, "samples": 2})
        self.assertEqual(listening.render_settings("production"), {"width": 792, "height": 1408, "samples": 16})
        timeline = listening.timeline_for(episode(), {"frames": 24000, "sample_rate": 24000},
                                          {"frames": 24000, "sample_rate": 24000},
                                          {"frames": 24000, "sample_rate": 24000})
        preview, _ = listening.video_filters(timeline, "preview")
        production, _ = listening.video_filters(timeline, "production")
        self.assertIn("scale=792:1408:flags=lanczos,crop=720:1280:36:120", preview)
        self.assertIn("fps=24,crop=720:1280:36:120", production)
        self.assertNotIn("scale=", production)
        self.assertEqual(preview.split("setsar=1", 1)[1], production.split("setsar=1", 1)[1])
        with self.assertRaisesRegex(ValueError, "Unknown"):
            listening.render_settings("unknown")

    def test_production_reuses_verified_audio_without_synthesis(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            data, files, _, source, answer, timeline = reuse_fixture(root)
            build = root / "production"
            with (patch.object(listening, "load_episode", return_value=(data, files)),
                  patch.object(listening, "audio_delivery_check") as audio_check,
                  patch.object(listening, "make_overlay"),
                  patch.object(listening, "synthesize") as synthesize):
                listening.build_listening.__wrapped__(Path("unused"), build, until="audio",
                                                     profile="production", reuse_audio=source)
            synthesize.assert_not_called()
            audio_check.assert_called_once()
            self.assertEqual(sha256_file(build / "audio" / answer.name), sha256_file(answer))
            self.assertEqual(sha256_file(build / "audio" / "hook-fixture.wav"),
                             sha256_file(source / "audio" / "hook-fixture.wav"))
            self.assertEqual(json.loads((build / "timeline.json").read_text(encoding="utf-8")), timeline)
            state = json.loads((build / "listening_state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["profile"], "production")
            self.assertEqual(state["render"], {"width": 792, "height": 1408, "samples": 16})
            self.assertEqual(state["audio_reuse"]["output_sha256"], sha256_file(source / "pilot.mp4"))

    def test_reuse_rejects_mismatched_or_damaged_preview(self):
        for problem in ("episode", "video", "answer", "hook", "hook_metadata", "legacy", "timeline", "metadata", "source",
                        "snapshot", "ambiguous", "nested"):
            with self.subTest(problem=problem), TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                data, files, sources, source, answer, _ = reuse_fixture(root)
                build = root / "production"
                if problem == "episode":
                    data["answer_text"] = "Different answer."
                elif problem == "video":
                    (source / "pilot.mp4").write_bytes(b"corrupted")
                elif problem == "answer":
                    answer.write_bytes(b"corrupted")
                elif problem == "hook":
                    (source / "audio" / "hook-fixture.wav").write_bytes(b"corrupted")
                elif problem == "hook_metadata":
                    metadata = source / "audio" / "hook-fixture.cache.json"
                    content = json.loads(metadata.read_text(encoding="utf-8"))
                    content["payload"]["text"] = "Different question."
                    atomic_json(metadata, content)
                elif problem == "legacy":
                    report_path = source / "delivery_checks.json"
                    report = json.loads(report_path.read_text(encoding="utf-8"))
                    del report["hook_audio_sha256"]
                    atomic_json(report_path, report)
                elif problem == "timeline":
                    atomic_json(source / "timeline.json", {"fps": 24})
                elif problem == "metadata":
                    metadata = answer.with_suffix(".cache.json")
                    content = json.loads(metadata.read_text(encoding="utf-8"))
                    content["payload"]["text"] = "Different answer."
                    atomic_json(metadata, content)
                elif problem == "source":
                    files["voice.txt"].write_text("Changed reference.", encoding="utf-8")
                    sources["voice.txt"]["sha256"] = sha256_file(files["voice.txt"])
                elif problem == "snapshot":
                    (source / "inputs" / "voice.txt").write_text("Damaged snapshot.", encoding="utf-8")
                elif problem == "ambiguous":
                    shutil.copyfile(answer, answer.with_name("answer-duplicate.wav"))
                else:
                    build = source / "production"
                with patch.object(listening, "audio_delivery_check"), self.assertRaises(ValueError):
                    listening.audio_reuse_spec(source, build, data, files, sources)

    def test_production_requires_exact_reuse_and_rejects_cache_conflict(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            data, files, _, source, _, _ = reuse_fixture(root)
            with patch.object(listening, "load_episode", return_value=(data, files)):
                with self.assertRaisesRegex(ValueError, "requires --reuse-audio"):
                    listening.build_listening.__wrapped__("unused", root / "out", profile="production")
                with self.assertRaisesRegex(ValueError, "not both"):
                    listening.build_listening.__wrapped__("unused", root / "out", profile="production",
                                                          reuse_audio=source, speech_cache_from=source)

    def test_scene_render_uses_frozen_script_and_requested_profile(self):
        for profile in ("preview", "production"):
            with self.subTest(profile=profile), TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                data, files, _, source, answer, _ = reuse_fixture(root)
                data["scene"] = {"cycle_frames": 5, "pose_frame": 447, "camera_prefix": "04",
                                 "playback_device": {"table_position": [-0.8, 0.075]}}
                state_path = source / "listening_state.json"
                state = json.loads(state_path.read_text(encoding="utf-8"))
                state["episode"] = data
                atomic_json(state_path, state)
                atomic_json(source / "episode.json", data)
                build = root / "output"
                settings = listening.render_settings(profile)

                def render(command, _log):
                    self.assertEqual(Path(command[command.index("--python") + 1]),
                                     build / "source_export" / "listening_scene.py")
                    for option, name in (("--width", "width"), ("--height", "height"),
                                         ("--samples", "samples")):
                        self.assertEqual(command[command.index(option) + 1], str(settings[name]))
                    frames = Path(command[command.index("--output") + 1])
                    for index in range(5):
                        Image.new("RGB", (settings["width"], settings["height"])).save(
                            frames / f"listener_{index:03d}.png")
                    atomic_json(build / "device_checks.json", {})

                with (patch.object(listening, "load_episode", return_value=(data, files)),
                      patch.object(listening, "audio_delivery_check"),
                      patch.object(listening, "make_overlay"),
                      patch.object(listening, "synthesize", return_value=[{"audio": str(answer)}, {"audio": str(answer)}]),
                      patch.object(listening, "run_logged", side_effect=render)):
                    listening.build_listening.__wrapped__("unused", build, until="scene", profile=profile,
                                                         reuse_audio=source if profile == "production" else None)
                self.assertEqual(len(list((build / "listener_frames").glob("*.png"))), 8)

    def test_export_rejects_input_changed_during_render(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            data, files, _, _, answer, _ = reuse_fixture(root)
            data["scene"] = {"cycle_frames": 5, "pose_frame": 447, "camera_prefix": "04",
                             "playback_device": {"table_position": [-0.8, 0.075]}}
            build = root / "output"

            def render(command, _log):
                self.assertIn("--python", command)
                frames = Path(command[command.index("--output") + 1])
                for index in range(5):
                    Image.new("RGB", (360, 640)).save(frames / f"listener_{index:03d}.png")
                (build / "inputs" / "book_audio.wav").write_bytes(b"changed")

            with (patch.object(listening, "load_episode", return_value=(data, files)),
                  patch.object(listening, "make_overlay"),
                  patch.object(listening, "synthesize", return_value=[{"audio": str(answer)}, {"audio": str(answer)}]),
                  patch.object(listening, "run_logged", side_effect=render) as run):
                with self.assertRaisesRegex(ValueError, "input snapshot changed"):
                    listening.build_listening.__wrapped__("unused", build)
                self.assertEqual(run.call_count, 1)

    def test_cli_dispatches_listening_production_and_rejects_unsupported_options(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "episode.json"
            path.write_text('{"exam":{"skill":"listening"}}', encoding="utf-8")
            args = ["pipeline.py", "build", "--episode", str(path), "--build", "out", "--profile",
                    "production", "--reuse-audio", "preview", "--qwen-python", sys.executable]
            with (patch.object(sys, "argv", args), patch.object(listening, "load_episode", return_value=({"id": "test"}, {})),
                  patch.object(listening, "build_listening") as build):
                pipeline.main()
            self.assertEqual(build.call_args.kwargs["profile"], "production")
            self.assertEqual(build.call_args.kwargs["reuse_audio"], Path("preview"))
            for flag in (["--render-device", "CUDA"], ["--speech-device", "cuda"], ["--promo"]):
                with (self.subTest(flag=flag), patch.object(sys, "argv", args + flag),
                      patch.object(listening, "load_episode", return_value=({"id": "test"}, {})),
                      self.assertRaises(SystemExit) as error):
                    pipeline.main()
                self.assertNotEqual(error.exception.code, 0)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
    def test_encoded_production_crop_and_phase_boundaries(self):
        with TemporaryDirectory() as directory:
            build = Path(directory)
            for name in ("listener_frames", "overlays", "inputs"):
                (build / name).mkdir()
            image = Image.new("RGB", (792, 1408), "black")
            ImageDraw.Draw(image).rectangle((130, 210, 150, 230), fill="white")
            image.save(build / "listener_frames" / "listener_000.png")
            for phase, color in (("hook", "red"), ("listening", "green"), ("reveal", "blue")):
                overlay = Image.new("RGBA", (720, 1280))
                ImageDraw.Draw(overlay).rectangle((0, 0, 20, 20), fill=color)
                overlay.save(build / "overlays" / f"{phase}.png")
            book, answer, hook = build / "inputs" / "book_audio.wav", build / "answer.wav", build / "hook.wav"
            write_wav(book, 1000)
            write_wav(answer, 1000)
            with wave.open(str(hook), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(24000)
                wav.writeframes(b"".join(struct.pack("<h", round(12000 * math.sin(2 * math.pi * 440 * i / 24000)))
                                         for i in range(1000)))
            timeline = {"fps": 24, "total_frames": 4, "duration": 4 / 24,
                        "phases": [{"name": "hook", "start_frame": 0, "end_frame": 1},
                                   {"name": "listening", "start_frame": 1, "end_frame": 2},
                                   {"name": "reveal", "start_frame": 2, "end_frame": 4}]}
            subprocess.run(listening.encoding_command(build, episode(), timeline, answer, hook, "production"),
                           check=True, capture_output=True)
            probe = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
                                    "-show_streams", "-of", "json", str(build / "pilot.mp4")],
                                   check=True, capture_output=True, text=True)
            stream = json.loads(probe.stdout)["streams"][0]
            self.assertEqual((stream["width"], stream["height"], stream["nb_read_frames"]), (720, 1280, "4"))
            self.assertEqual(stream["sample_aspect_ratio"], "1:1")
            opening = subprocess.run(
                ["ffmpeg", "-v", "error", "-i", str(build / "pilot.mp4"), "-t", "0.04",
                 "-f", "s16le", "-ac", "1", "-ar", "24000", "-"],
                check=True, capture_output=True).stdout
            self.assertGreater(max(abs(value[0]) for value in struct.iter_unpack("<h", opening)), 1000)
            for index, expected in ((0, (255, 0, 0)), (1, (0, 128, 0)), (2, (0, 0, 255))):
                decoded = subprocess.run(
                    ["ffmpeg", "-v", "error", "-i", str(build / "pilot.mp4"), "-vf",
                     f"select=eq(n\\,{index}),crop=2:2:10:10", "-frames:v", "1",
                     "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                    check=True, capture_output=True).stdout
                self.assertEqual(len(decoded), 12)
                self.assertTrue(all(abs(a - b) < 15 for a, b in zip(decoded[:3], expected)))
            cropped = subprocess.run(
                ["ffmpeg", "-v", "error", "-i", str(build / "pilot.mp4"), "-vf",
                 "crop=2:2:100:100", "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                check=True, capture_output=True).stdout
            self.assertTrue(all(value > 235 for value in cropped[:3]))

    def test_real_audio_clock_has_reading_response_reveal_and_cta(self):
        timeline = listening.timeline_for(
            episode(), {"frames": 456961, "sample_rate": 24000},
            {"frames": 96000, "sample_rate": 24000}, {"frames": 24000, "sample_rate": 24000})
        phases = {phase["name"]: phase for phase in timeline["phases"]}
        for remaining in range(7, 0, -1):
            phase = phases[f"reading_{remaining}"]
            self.assertEqual(phase["end_frame"] - phase["start_frame"], 24)
            if remaining > 1:
                self.assertEqual(phase["end_frame"], phases[f"reading_{remaining - 1}"]["start_frame"])
        self.assertEqual(phases["reading_1"]["end_frame"], phases["listening"]["start_frame"])
        self.assertEqual(phases["listening"]["end_frame"] - phases["listening"]["start_frame"], 457)
        self.assertEqual(phases["response_1"]["end_frame"] - phases["response_6"]["start_frame"], 6 * 24)
        self.assertEqual(phases["reveal"]["start_frame"], phases["response_1"]["end_frame"])
        self.assertEqual(phases["cta"]["end_frame"] - phases["cta"]["start_frame"], 6 * 24)
        self.assertEqual(timeline["total_frames"], 1177)
        filters, _ = listening.video_filters(timeline)
        self.assertIn("scale=792:1408:flags=lanczos", filters)
        self.assertIn("crop=720:1280:36:120", filters)
        self.assertIn("setsar=1", filters)
        self.assertIn("adelay=480000S:all=1", filters)
        self.assertIn("adelay=1682000S:all=1", filters)
        command = listening.encoding_command(Path("build"), episode(), timeline, Path("answer.wav"), Path("hook.wav"))
        self.assertEqual(command[command.index("-t") + 1], "49.041666667")
        self.assertIn("-shortest", command)

    def test_listener_loop_returns_via_adjacent_source_frames(self):
        indices = listening.loop_indices(4)
        self.assertEqual(indices, [0, 1, 2, 3, 2, 1])
        self.assertTrue(all(abs(a - b) == 1 for a, b in zip(indices, indices[1:] + indices[:1])))
        self.assertEqual(listening.loop_indices(2), [0, 1])
        indices = listening.loop_indices(96)
        self.assertEqual(len(indices), 190)
        self.assertTrue(all(abs(a - b) == 1 for a, b in zip(indices, indices[1:] + indices[:1])))
        with self.assertRaisesRegex(ValueError, "at least two"):
            listening.loop_indices(1)

    def test_listener_motion_keeps_head_up_and_blinks_briefly(self):
        samples = [listener_offsets(index, 96) for index in range(96)]
        self.assertTrue(all(set(sample) == {"head_yaw", "chest_yaw", "eye_horizontal", "blink"}
                            for sample in samples))
        self.assertEqual(sum(sample["blink"] > 0.001 for sample in samples), 3)
        self.assertLess(abs(samples[0]["head_yaw"] - samples[1]["head_yaw"]), .0001)
        self.assertLess(abs(samples[-1]["head_yaw"] - samples[-2]["head_yaw"]), .0001)
        self.assertGreater(samples[0]["head_yaw"], samples[-1]["head_yaw"])
        with self.assertRaises(ValueError):
            listener_offsets(0, 4)

    def test_countdowns_are_large_lower_frame_and_change_each_second(self):
        data = episode()
        for phase, maximum in (("reading", 7), ("response", 6)):
            for remaining in range(maximum, 0, -1):
                with patch("PIL.ImageDraw.ImageDraw.text", autospec=True) as draw:
                    listening.make_overlay(data, f"{phase}_{remaining}", Path("unused"))
                number = [call for call in draw.call_args_list if call.args[2] == str(remaining)]
                self.assertEqual(len(number), 1)
                self.assertGreaterEqual(number[0].kwargs["font"].size, 80)
                self.assertGreater(number[0].args[1][1], listening.HEIGHT / 2)

    def test_title_and_question_leave_character_head_uncovered(self):
        data = episode()
        with TemporaryDirectory() as directory:
            cover = Path(directory) / "cover.jpg"
            Image.new("RGB", (400, 600), "white").save(cover)
            for phase in ("hook", "reading_7", "listening", "response_6", "reveal", "cta"):
                image = listening.make_overlay(data, phase, cover)
                self.assertIsNone(image.getchannel("A").crop((0, 186, 720, 520)).getbbox(), phase)
        with patch("PIL.ImageDraw.ImageDraw.text", autospec=True) as draw:
            listening.make_overlay(data, "hook", Path("unused"))
        texts = [call.args[2] for call in draw.call_args_list]
        self.assertIn("DTZ B1 HÖREN", texts)
        self.assertNotIn("Kannst du die Frage lösen?", texts)
        question = next(call for call in draw.call_args_list if call.args[2] == data["question"])
        self.assertGreaterEqual(question.args[1][1], 520)

    def test_narration_must_fit_and_exactly_90_seconds_is_rejected(self):
        book = {"frames": 24000, "sample_rate": 24000}
        extended = listening.timeline_for(episode(), book, book, {"frames": 96001, "sample_rate": 24000})
        self.assertEqual(extended["phases"][0]["end_frame"], 97)
        self.assertEqual(extended["phases"][1]["start_frame"], 97)
        with self.assertRaisesRegex(ValueError, "exceeds reveal"):
            listening.timeline_for(episode(), book, {"frames": 9 * 24000, "sample_rate": 24000}, book)
        long = episode()
        long["timing"]["hook_seconds"] = 62
        with self.assertRaisesRegex(ValueError, "strictly shorter"):
            listening.timeline_for(long, book, {"frames": 24000, "sample_rate": 24000}, book)

    def test_build_synthesizes_the_visible_question_as_the_hook(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            data, files, _, source, answer, _ = reuse_fixture(root)
            hook = source / "audio" / "hook-fixture.wav"
            with (patch.object(listening, "load_episode", return_value=(data, files)),
                  patch.object(listening, "make_overlay"),
                  patch.object(listening, "synthesize", return_value=[{"audio": str(hook)}, {"audio": str(answer)}]) as synth):
                listening.build_listening.__wrapped__("unused", root / "new", until="audio")
            turns = synth.call_args.args[0]["turns"]
            self.assertEqual(turns[0]["text"], data["question"])
            self.assertEqual(turns[1]["text"], data["answer_text"])

    def test_answer_is_not_displayed_before_reveal(self):
        data = episode()
        with patch.object(listening, "draw_wrapped", wraps=listening.draw_wrapped) as draw:
            listening.make_overlay(data, "listening", Path("unused"))
            before = [call.args[1] for call in draw.call_args_list]
        self.assertNotIn(data["answer_text"], before)
        self.assertNotIn(data["key_detail"], before)
        with patch.object(listening, "draw_wrapped", wraps=listening.draw_wrapped) as draw:
            listening.make_overlay(data, "reveal", Path("unused"))
            after = [call.args[1] for call in draw.call_args_list]
        self.assertIn(data["answer_text"], after)
        self.assertIn(data["key_detail"], after)

    def test_cta_fits_with_a_book_cover(self):
        with TemporaryDirectory() as directory:
            cover = Path(directory) / "cover.jpg"
            Image.new("RGB", (400, 600), "white").save(cover)
            image = listening.make_overlay(episode(), "cta", cover)
        self.assertEqual(image.size, (720, 1280))


if __name__ == "__main__":
    unittest.main()
