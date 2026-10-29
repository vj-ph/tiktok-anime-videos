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
import prepare_listening_source
from listener_motion import listener_offsets
from PIL import Image, ImageDraw
from prepare_audio import atomic_json, content_hash, inspect_wav, make_cache_payload, sha256_file


def episode():
    return {
        "fps": 24,
        "scene": {},
        "title": "DTZ B1: Arzttermin",
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


def fixture_alignment(data, audio):
    words = []
    for index, word in enumerate(listening.aligned_title(data["title"]).split()):
        words.append({"word": word, "start": index * 0.2, "end": index * 0.2 + 0.15, "score": 0.9})
    return {"title": data["title"], "aligned_text": listening.aligned_title(data["title"]),
            "audio_sha256": sha256_file(audio), "provenance": {"language": data.get("language", "de")},
            "words": words}


def fake_hook_alignment(build, data, audio):
    receipt = fixture_alignment(data, audio)
    atomic_json(build / "hook_alignment.json", receipt)
    return receipt


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
    for name, text in (("answer", data["answer_text"]), ("hook", data["title"])):
        recording = source / "audio" / f"{name}-fixture.wav"
        write_wav(recording)
        payload = make_cache_payload({"speaker": "narrator", "text": text},
                                     files["voice.wav"], files["voice.txt"], {"model": "fixture"})
        atomic_json(recording.with_suffix(".cache.json"),
                    {"payload": payload, "cache_key": content_hash(payload),
                     "wav_sha256": sha256_file(recording), "audio_info": inspect_wav(recording)})
    answer, hook = (source / "audio" / f"{name}-fixture.wav" for name in ("answer", "hook"))
    atomic_json(source / "hook_alignment.json", fixture_alignment(data, hook))
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
    report_path = source / "delivery_checks.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["hook_alignment_sha256"] = sha256_file(source / "hook_alignment.json")
    atomic_json(report_path, report)
    return data, files, sources, source, answer, timeline


class ListeningVideoTest(unittest.TestCase):
    def test_authored_tef_bus_stop_uses_portable_paths_and_four_choices(self):
        path = Path(__file__).parent / "episodes" / "tef_canada_listening_bus_stop.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["exam"], {"family": "tef_canada", "skill": "listening",
                                        "section": "text_choice"})
        self.assertEqual(data["language"], "fr")
        self.assertEqual(len(data["choices"]), 4)
        self.assertEqual(data["correct_choice"], "B")
        self.assertIn("devant la pharmacie", data["source"]["audio_transcript"])
        for value in (data["audio"], data["voice"]["audio"], data["voice"]["transcript"],
                      data["source_voice"]["audio"], data["source_voice"]["transcript"],
                      data["book_cover"], data["scene"]["source"], data["source"]["book"],
                      data["source"]["audio_provenance"], data["scene"]["flag_artwork"],
                      data["scene"]["flag_provenance"]):
            self.assertNotIn("\\", value)
        self.assertEqual(data["voice"]["voice_id"], "fr_ca_qc_narrator_f01")
        self.assertEqual(data["source_voice"]["voice_id"], "fr_ca_qc_service_m01")
        self.assertEqual(data["audio_effect"], "pa_chime_echo")
        self.assertTrue(data["scene"]["rest_hands_on_table"])
        self.assertTrue(data["book_cover"].endswith("/listening/listening.jpg"))

    def test_authored_tef_bus_stop_matches_book_when_available(self):
        path = Path(__file__).parent / "episodes" / "tef_canada_listening_bus_stop.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        book = (path.parent / data["source"]["book"]).resolve()
        if not book.is_file():
            self.skipTest("The sibling TEF listening book is not available.")
        text = book.read_text(encoding="utf-8")
        candidate, review = text.split("### 2. Public announcements", 2)[1:]
        question = candidate.split("#### Question 17", 1)[1].split("#### Question 18", 1)[0]
        solution = review.split("#### Question 17", 1)[1].split("#### Question 18", 1)[0]
        self.assertIn(data["question"], question)
        for choice in data["choices"]:
            self.assertIn(choice, question)
        self.assertIn(data["source"]["audio_transcript"], solution)
        self.assertIn("**Correct answer:** B", solution)

    def test_prepare_source_requires_exact_book_text_and_never_overwrites(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            builds = root / "builds"
            for name in ("voice.wav",):
                write_wav(root / name)
            (root / "voice.txt").write_text("Reference text.", encoding="utf-8")
            (root / "book.md").write_text("The original announcement.", encoding="utf-8")
            target = builds / "exercise" / "announcement.wav"
            data = {
                "language": "fr", "audio": str(target),
                "voice": {"audio": str(root / "voice.wav"), "transcript": str(root / "voice.txt")},
                "source": {"book": str(root / "book.md"), "audio_transcript": "The original announcement.",
                           "audio_provenance": str(target.with_suffix(".cache.json"))},
            }
            path = root / "episode.json"
            registry = root / "audio" / "voices" / "voices.json"
            registry.parent.mkdir(parents=True)
            registry_data = {"voices": [{"voice_id": "test", "availability": False,
                                         "reference_audio": "voice.wav",
                                         "reference_text": "Reference text."}]}
            atomic_json(registry, registry_data)
            data["voice"]["voice_id"] = "test"
            data["source"]["voice_registry"] = str(registry)
            atomic_json(path, data)

            def fake_synthesize(speech, _episode_dir, output, _model, _device, _threads):
                self.assertEqual(speech["language"], "fr")
                self.assertEqual(speech["turns"][0]["text"], data["source"]["audio_transcript"])
                self.assertEqual(speech["voices"]["announcement"]["audio"], str(root / "voice.wav"))
                recording = output / "announcement-generated.wav"
                write_wav(recording)
                payload = {"text": speech["turns"][0]["text"], "settings": {"language": "French"},
                           "reference_audio_sha256": sha256_file(root / "voice.wav"),
                           "reference_transcript_sha256": sha256_file(root / "voice.txt"),
                           "reference_text": "Reference text."}
                atomic_json(recording.with_suffix(".cache.json"), {
                    "payload": payload, "cache_key": content_hash(payload),
                    "wav_sha256": sha256_file(recording), "audio_info": inspect_wav(recording)})
                return [{"audio": str(recording)}]

            with (patch.object(prepare_listening_source, "BUILDS", builds),
                  patch.object(prepare_listening_source, "synthesize", side_effect=fake_synthesize) as synth):
                data["source"]["audio_transcript"] = "Not in the book."
                atomic_json(path, data)
                with self.assertRaisesRegex(ValueError, "not found"):
                    prepare_listening_source.prepare(path, "model")
                synth.assert_not_called()
                data["source"]["audio_transcript"] = "The original announcement."
                atomic_json(path, data)
                with self.assertRaisesRegex(ValueError, "unavailable"):
                    prepare_listening_source.prepare(path, "model")
                registry_data["voices"][0]["availability"] = True
                registry_data["voices"][0]["reference_text"] = "A different transcript."
                atomic_json(registry, registry_data)
                with self.assertRaisesRegex(ValueError, "does not match"):
                    prepare_listening_source.prepare(path, "model")
                registry_data["voices"][0]["reference_text"] = "Reference text."
                atomic_json(registry, registry_data)
                data["source_voice"] = data["voice"].copy()
                data["voice"]["voice_id"] = "different-narrator"
                atomic_json(path, data)
                self.assertEqual(prepare_listening_source.prepare(path, "model"), target)
                digest = sha256_file(target)
                with self.assertRaisesRegex(ValueError, "already exists"):
                    prepare_listening_source.prepare(path, "model")
                self.assertEqual(sha256_file(target), digest)
                self.assertEqual(synth.call_count, 1)

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

            data["timing"]["reading_seconds"] = 5
            validate()
            data["exam"]["section"] = "1"
            with self.assertRaisesRegex(ValueError, "at least 7 seconds"):
                validate()
            data["exam"]["section"] = "2"
            data["timing"]["reading_seconds"] = 4
            with self.assertRaisesRegex(ValueError, "at least 5 seconds"):
                validate()
            data["timing"]["reading_seconds"] = 5
            data["timing"]["response_seconds"] = 5
            with self.assertRaisesRegex(ValueError, "six seconds to respond"):
                validate()
            data["timing"]["response_seconds"] = 6
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

            data.update(language="fr", exam={"family": "tef_canada", "skill": "listening",
                                            "section": "text_choice"},
                        choices=["un", "deux", "trois", "quatre"], correct_choice="D")
            with self.assertRaisesRegex(ValueError, "at least 7 seconds"):
                validate()
            data["timing"]["reading_seconds"] = 7
            validate()
            payload = {"text": "Annonce originale.", "settings": {"language": "French"}}
            data["source"].update(audio_provenance="book.cache.json", audio_transcript=payload["text"])
            metadata = {"payload": payload, "cache_key": content_hash(payload),
                        "wav_sha256": sha256_file(root / "book.wav"),
                        "audio_info": inspect_wav(root / "book.wav")}
            atomic_json(root / "book.cache.json", metadata)
            self.assertIn("book_audio.cache.json", validate()[1])
            metadata["wav_sha256"] = "0" * 64
            atomic_json(root / "book.cache.json", metadata)
            with self.assertRaisesRegex(ValueError, "provenance"):
                validate()
            metadata["wav_sha256"] = sha256_file(root / "book.wav")
            atomic_json(root / "book.cache.json", metadata)
            data["source"]["audio_transcript"] = "Une autre annonce."
            with self.assertRaisesRegex(ValueError, "provenance"):
                validate()
            data["source"]["audio_transcript"] = payload["text"]
            payload["settings"]["language"] = "German"
            metadata["cache_key"] = content_hash(payload)
            atomic_json(root / "book.cache.json", metadata)
            with self.assertRaisesRegex(ValueError, "provenance"):
                validate()
            del data["source"]["audio_provenance"]
            del data["source"]["audio_transcript"]
            original_choice = data["choices"][0]
            data["choices"][0] = " ".join(["option"] * 100)
            with self.assertRaisesRegex(ValueError, "exceeds"):
                validate()
            data["choices"][0] = original_choice
            data["choices"].pop()
            with self.assertRaisesRegex(ValueError, "4 nonempty"):
                validate()
            data["choices"].append("quatre")
            data["language"] = "de"
            with self.assertRaisesRegex(ValueError, "TEF Canada French"):
                validate()
            data["language"] = "fr"
            data["exam"]["section"] = "3"
            with self.assertRaisesRegex(ValueError, "TEF Canada French"):
                validate()

    def test_tef_generated_source_uses_distinct_registered_quebec_voices(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for name, frames in (("book.wav", 24000), ("voice.wav", 24000), ("source.wav", 12000)):
                write_wav(root / name, frames)
            for name in ("book.md", "scene.blend", "device.glb"):
                (root / name).write_bytes(b"fixture")
            (root / "voice.txt").write_text("Narrator reference.", encoding="utf-8")
            (root / "source.txt").write_text("Announcement reference.", encoding="utf-8")
            Image.new("RGB", (4, 6), "white").save(root / "cover.jpg")
            atomic_json(root / "device.json", {"sha256": sha256_file(root / "device.glb")})
            registry = root / "audio" / "voices" / "voices.json"
            registry.parent.mkdir(parents=True)
            entries = [
                {"voice_id": "fr_ca_qc_narrator", "locale": "fr-CA", "availability": True,
                 "reference_audio": "voice.wav", "reference_text": "Narrator reference."},
                {"voice_id": "fr_ca_qc_service", "locale": "fr-CA", "availability": True,
                 "reference_audio": "source.wav", "reference_text": "Announcement reference."},
            ]
            atomic_json(registry, {"voices": entries})
            data = episode()
            data.update(schema_version=1, id="fixture", language="fr", title="Fixture",
                        exam={"family": "tef_canada", "skill": "listening", "section": "text_choice"},
                        choices=["un", "deux", "trois", "quatre"], audio="book.wav",
                        book_cover="cover.jpg",
                        voice={"audio": "voice.wav", "transcript": "voice.txt",
                               "voice_id": "fr_ca_qc_narrator"},
                        source_voice={"audio": "source.wav", "transcript": "source.txt",
                                      "voice_id": "fr_ca_qc_service"},
                        scene={"source": "scene.blend", "camera_prefix": "04", "pose_frame": 1,
                               "cycle_frames": 5, "framing": "full", "hide_objects": ["Task sheet"],
                               "playback_device": {"model": "device.glb", "provenance": "device.json",
                                                   "table_position": [0, 0]}})
            data["source"].update(book="book.md", voice_registry="audio/voices/voices.json",
                                  audio_provenance="book.cache.json", audio_transcript="Annonce.")
            payload = {"text": "Annonce.", "settings": {"language": "French"},
                       "reference_audio_sha256": sha256_file(root / "source.wav"),
                       "reference_transcript_sha256": sha256_file(root / "source.txt")}
            metadata = {"payload": payload, "cache_key": content_hash(payload),
                        "wav_sha256": sha256_file(root / "book.wav"), "audio_info": inspect_wav(root / "book.wav")}
            atomic_json(root / "book.cache.json", metadata)
            path = root / "episode.json"

            def validate():
                atomic_json(path, data)
                return listening.load_episode(path)

            files = validate()[1]
            self.assertTrue({"source_voice.wav", "source_voice.txt", "voice_registry.json"} <= files.keys())
            payload["reference_audio_sha256"] = sha256_file(root / "voice.wav")
            metadata["cache_key"] = content_hash(payload)
            atomic_json(root / "book.cache.json", metadata)
            with self.assertRaisesRegex(ValueError, "provenance"):
                validate()
            payload["reference_audio_sha256"] = sha256_file(root / "source.wav")
            metadata["cache_key"] = content_hash(payload)
            atomic_json(root / "book.cache.json", metadata)
            entries[1]["locale"] = "fr-FR"
            atomic_json(registry, {"voices": entries})
            with self.assertRaisesRegex(ValueError, "Quebec French"):
                validate()
            entries[1]["locale"] = "fr-CA"
            atomic_json(registry, {"voices": entries})
            data["source_voice"] = data["voice"].copy()
            with self.assertRaisesRegex(ValueError, "distinct"):
                validate()
            data["source_voice"] = {"audio": "source.wav", "transcript": "source.txt",
                                    "voice_id": "fr_ca_qc_service"}
            data["scene"]["hide_objects"] = ["Task sheet", "Task sheet"]
            with self.assertRaisesRegex(ValueError, "unique"):
                validate()
            data["scene"]["hide_objects"] = ["Task sheet"]
            data["scene"]["rest_hands_on_table"] = "yes"
            with self.assertRaisesRegex(ValueError, "rest_hands_on_table"):
                validate()
            data["scene"]["rest_hands_on_table"] = True
            data["scene"]["min_hair_drop_m"] = 0
            with self.assertRaisesRegex(ValueError, "hair_drop"):
                validate()
            data["scene"]["min_hair_drop_m"] = 0.15
            data["audio_effect"] = "unknown"
            with self.assertRaisesRegex(ValueError, "audio_effect"):
                validate()
            data["audio_effect"] = "pa_chime_echo"
            (root / "flag.png").write_bytes(b"fixture flag")
            data["scene"].update(flag_artwork="flag.png", flag_provenance="flag.json")
            flag = {"assets": {"canada_flag": {"sha256": sha256_file(root / "flag.png")}}}
            atomic_json(root / "flag.json", flag)
            self.assertIn("flag.png", validate()[1])
            flag["assets"]["canada_flag"]["sha256"] = "0" * 64
            atomic_json(root / "flag.json", flag)
            with self.assertRaisesRegex(ValueError, "Flag artwork checksum"):
                validate()

    def test_tef_overlay_shows_four_choices_without_answer_until_reveal(self):
        data = episode()
        data.update(
            language="fr", exam={"family": "tef_canada", "skill": "listening",
                                 "section": "text_choice"},
            question="Que doivent faire les voyageurs qui utilisent habituellement l’arrêt Rue-des-Érables ?",
            choices=["Prendre le métro jusqu’au centre-ville.",
                     "Attendre la ligne 18 devant la pharmacie.",
                     "Attendre un autobus de remplacement sur le pont.",
                     "Reporter tous leurs déplacements à demain."],
            correct_choice="B",
            answer_text="La bonne réponse est B. L’arrêt provisoire est devant la pharmacie.",
            key_detail="« devant la pharmacie »",
        )
        with TemporaryDirectory() as directory:
            cover = Path(directory) / "cover.jpg"
            Image.new("RGB", (4, 6), "white").save(cover)
            for phase in ("reading_7", "listening", "response_6"):
                with self.subTest(phase=phase), patch.object(
                        listening, "draw_wrapped", wraps=listening.draw_wrapped) as draw:
                    image = listening.make_overlay(data, phase, cover)
                    self.assertIsNone(image.getchannel("A").crop((250, 370, 440, 580)).getbbox())
                    self.assertIsNone(image.getchannel("A").crop((164, 10, 480, 184)).getbbox())
                    self.assertIsNone(image.getchannel("A").crop((347, 940, 657, 1178)).getbbox())
                    text = " ".join(call.args[1] for call in draw.call_args_list)
                    for choice in data["choices"]:
                        self.assertIn(choice, text)
                    self.assertNotIn(data["answer_text"], text)
                    self.assertNotIn(data["key_detail"], text)
            with patch.object(listening, "draw_wrapped", wraps=listening.draw_wrapped) as draw:
                image = listening.make_overlay(data, "reveal", cover)
                self.assertIsNone(image.getchannel("A").crop((250, 370, 440, 580)).getbbox())
                self.assertIsNone(image.getchannel("A").crop((347, 940, 657, 1178)).getbbox())
                text = " ".join(call.args[1] for call in draw.call_args_list)
                self.assertIn(data["answer_text"], text)
                self.assertIn(data["key_detail"], text)
                self.assertIn("B  " + data["choices"][1], text)
            with patch.object(listening, "draw_wrapped", wraps=listening.draw_wrapped) as draw:
                image = listening.make_overlay(data, "cta", cover)
                self.assertIsNone(image.getchannel("A").crop((250, 370, 440, 580)).getbbox())
                self.assertIsNone(image.getchannel("A").crop((347, 940, 657, 1178)).getbbox())
                text = " ".join(call.args[1] for call in draw.call_args_list)
                self.assertIn("TEF Canada", text)
                self.assertNotIn("DTZ", text)

            data["choices"] = [" ".join(["option"] * 100)] * 4
            with self.assertRaisesRegex(ValueError, "exceeds"):
                listening.make_overlay(data, "listening", cover)

    def test_tef_build_synthesizes_french_opening_and_answer(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            data, files, _, _, _, _ = reuse_fixture(root)
            data.update(language="fr", exam={"family": "tef_canada", "skill": "listening",
                                             "section": "text_choice"})
            def fake_synthesize(narration, _, audio_dir, *args, **kwargs):
                self.assertEqual(narration["language"], "fr")
                self.assertEqual([turn["text"] for turn in narration["turns"]],
                                 [data["title"], data["answer_text"]])
                paths = [audio_dir / "hook-test.wav", audio_dir / "answer-test.wav"]
                for path in paths:
                    write_wav(path)
                return [{"audio": str(path)} for path in paths]

            with (patch.object(listening, "load_episode", return_value=(data, files)),
                  patch.object(listening, "make_overlay"),
                  patch.object(listening, "prepare_hook_alignment", side_effect=fake_hook_alignment),
                  patch.object(listening, "synthesize", side_effect=fake_synthesize)):
                listening.build_listening.__wrapped__(Path("unused"), root / "tef-build",
                                                     until="audio", profile="preview")

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

    def test_public_address_effect_preserves_source_and_validates_derived_audio(self):
        with TemporaryDirectory() as directory:
            build = Path(directory)
            (build / "inputs").mkdir()
            source = build / "inputs" / "book_audio.wav"
            samples = [round(14000 * math.sin(2 * math.pi * 220 * i / 24000)) for i in range(24000)]
            with wave.open(str(source), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(24000)
                wav.writeframes(struct.pack("<24000h", *samples))
            digest = sha256_file(source)
            data = episode()
            data["audio_effect"] = "pa_chime_echo"
            result = listening.book_audio_file(data, build, create=True)
            self.assertEqual(sha256_file(source), digest)
            with wave.open(str(result), "rb") as wav:
                rendered = struct.unpack(f"<{wav.getnframes()}h", wav.readframes(wav.getnframes()))
            lead = round(24000 * 0.96)
            delay = round(24000 * 0.05)
            self.assertEqual(len(rendered), lead + len(samples) + delay)
            self.assertGreater(max(rendered[:lead]), 3500)
            self.assertTrue(all(value == 0 for value in rendered[19200:lead]))
            for index in (100, 1200, 5000, 23999):
                expected = (7 * samples[index] + (samples[index - delay] if index >= delay else 0)) // 8
                self.assertEqual(rendered[lead + index], expected)
            self.assertEqual(listening.book_audio_file(data, build, create=False), result)
            with wave.open(str(result), "rb") as wav:
                params, output = wav.getparams(), wav.readframes(wav.getnframes())
            with wave.open(str(result), "wb") as wav:
                wav.setparams(params)
                wav.writeframes(bytes([output[0] ^ 1]) + output[1:])
            with self.assertRaisesRegex(ValueError, "sound treatment differs"):
                listening.book_audio_file(data, build, create=False)
            data["audio_effect"] = "unknown"
            with self.assertRaisesRegex(ValueError, "Unsupported"):
                listening.book_audio_file(data, build, create=False)

    def test_reuse_checks_treated_announcement_delivery_hash(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            data, files, sources, source, answer, _ = reuse_fixture(root)
            data["audio_effect"] = "pa_chime_echo"
            treated = listening.book_audio_file(data, source, create=True)
            hook = source / "audio" / "hook-fixture.wav"
            timeline = listening.timeline_for(data, inspect_wav(treated), inspect_wav(answer), inspect_wav(hook))
            atomic_json(source / "episode.json", data)
            atomic_json(source / "timeline.json", timeline)
            atomic_json(source / "listening_state.json", {"episode": data, "profile": "preview", "sources": sources})
            report_path = source / "delivery_checks.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report.update(timeline=timeline, book_audio_sha256=sha256_file(treated))
            atomic_json(report_path, report)
            with patch.object(listening, "audio_delivery_check") as check:
                listening.audio_reuse_spec(source, root / "production", data, files, sources)
                self.assertEqual(check.call_args.args[1], treated)
                report["book_audio_sha256"] = "0" * 64
                atomic_json(report_path, report)
                with self.assertRaisesRegex(ValueError, "excerpt checksum"):
                    listening.audio_reuse_spec(source, root / "production", data, files, sources)

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
        for profile in ("preview", "production"):
            full, _ = listening.video_filters(timeline, profile, "full")
            self.assertIn("scale=720:1280:flags=lanczos", full)
            self.assertNotIn("crop=", full)
        with self.assertRaisesRegex(ValueError, "framing"):
            listening.video_filters(timeline, "preview", "invalid")
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
        for problem in ("episode", "video", "answer", "hook", "hook_metadata", "legacy", "alignment",
                        "alignment_content", "timeline", "metadata", "source", "snapshot", "ambiguous", "nested"):
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
                    del report["hook_alignment_sha256"]
                    atomic_json(report_path, report)
                elif problem in ("alignment", "alignment_content"):
                    alignment_path = source / "hook_alignment.json"
                    alignment = json.loads(alignment_path.read_text(encoding="utf-8"))
                    alignment["words"][0]["word"] = "changed"
                    atomic_json(alignment_path, alignment)
                    if problem == "alignment_content":
                        report_path = source / "delivery_checks.json"
                        report = json.loads(report_path.read_text(encoding="utf-8"))
                        report["hook_alignment_sha256"] = sha256_file(alignment_path)
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
                      patch.object(listening, "prepare_hook_alignment", side_effect=fake_hook_alignment),
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
                  patch.object(listening, "prepare_hook_alignment", side_effect=fake_hook_alignment),
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
        title = next(call for call in draw.call_args_list if call.args[2] == "DTZ")
        self.assertGreaterEqual(title.args[1][1], 520)

    def test_title_overlay_highlights_only_the_aligned_word(self):
        data = episode()
        data["title"] = "DTZ B1: Süßes oder Prüfungsangst?"
        for index, expected in enumerate(listening.aligned_title(data["title"]).split()):
            with self.subTest(word=expected), patch("PIL.ImageDraw.ImageDraw.text", autospec=True) as draw:
                listening.make_overlay(data, "hook", Path("unused"), highlight_word=index)
            tokens = [call for call in draw.call_args_list if call.args[2] in data["title"].split()]
            self.assertEqual(len(tokens), 5)
            highlighted = [call.args[2] for call in tokens if call.kwargs["fill"] == (174, 242, 198, 255)]
            self.assertEqual(highlighted, [expected])
        data.update(language="fr", exam={"family": "tef_canada", "section": "text_choice"},
                    title="TEF Canada : Compréhension orale")
        with patch("PIL.ImageDraw.ImageDraw.text", autospec=True) as draw:
            listening.make_overlay(data, "hook", Path("unused"), highlight_word=1)
        highlighted = [call.args[2] for call in draw.call_args_list
                       if call.kwargs.get("fill") == (174, 242, 198, 255)]
        self.assertIn("Canada:", highlighted)

    def test_title_highlight_uses_measured_frame_boundaries(self):
        timeline = {"fps": 24, "total_frames": 102, "duration": 4.25, "phases": [
            {"name": "hook", "start_frame": 0, "end_frame": 30},
            {"name": "reading_1", "start_frame": 30, "end_frame": 54},
            {"name": "listening", "start_frame": 54, "end_frame": 78},
            {"name": "reveal", "start_frame": 78, "end_frame": 102},
        ]}
        words = [{"word": "A", "start": 0.1, "end": 0.25},
                 {"word": "B", "start": 0.4, "end": 0.5}]
        windows = listening.hook_overlay_windows(timeline, words)
        self.assertEqual([(w["name"], w["start_frame"], w["end_frame"]) for w in windows],
                         [("hook", 0, 3), ("hook_word_0", 3, 6), ("hook", 6, 10),
                          ("hook_word_1", 10, 12), ("hook", 12, 30)])
        filters, _ = listening.video_filters(timeline, hook_words=words)
        self.assertIn("enable='gte(n,3)*lt(n,6)'", filters)
        self.assertIn("enable='gte(n,10)*lt(n,12)'", filters)
        self.assertIn("[9:a]aresample=48000", filters)
        command = listening.encoding_command(Path("build"), episode(), timeline,
                                             Path("answer.wav"), Path("hook.wav"), hook_words=words)
        self.assertIn("build/overlays/hook_word_0.png", command)
        self.assertIn("build/overlays/hook_word_1.png", command)
        self.assertEqual(command[command.index("-filter_complex") + 1], filters)
        with self.assertRaisesRegex(ValueError, "no valid encoded highlight interval"):
            listening.hook_overlay_windows(timeline, [{"word": "A", "start": 0.01, "end": 0.02}])

    def test_title_alignment_is_measured_cached_and_validated(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            audio = root / "hook.wav"
            write_wav(audio)
            data = episode()
            def fake_align(build):
                timeline = json.loads((build / "timeline.json").read_text(encoding="utf-8"))
                self.assertEqual(timeline["turns"][0]["text"], data["title"])
                self.assertEqual(timeline["turns"][0]["audio"], str(audio))
                receipt = fixture_alignment(data, audio)
                atomic_json(build / "word_alignment.json", {
                    "provenance": receipt["provenance"], "turns": [{"words": receipt["words"]}]})
            with patch.object(listening, "align_build", side_effect=fake_align) as align:
                receipt = listening.prepare_hook_alignment(root, data, audio)
                self.assertEqual(len(receipt["words"]), 3)
                self.assertEqual(listening.prepare_hook_alignment(root, data, audio), receipt)
                align.assert_called_once()
                receipt["words"][0]["word"] = "wrong"
                atomic_json(root / "hook_alignment.json", receipt)
                with self.assertRaisesRegex(ValueError, "changed transcript token"):
                    listening.prepare_hook_alignment(root, data, audio)

    def test_title_highlight_review_rejects_missing_encoded_color(self):
        data = episode()
        with TemporaryDirectory() as directory:
            root = Path(directory)
            highlighted = listening.make_overlay(data, "hook", Path("unused"), highlight_word=1)
            plain = listening.make_overlay(data, "hook", Path("unused"))
            background = Image.new("RGBA", (720, 1280), (100, 100, 100, 255))
            highlighted.save(root / "highlight.png")
            Image.alpha_composite(background, highlighted).convert("RGB").save(root / "frame.png")
            check = listening.check_hook_highlight(root / "frame.png", root / "highlight.png")
            self.assertGreater(check["matching_fraction"], 0.99)
            Image.alpha_composite(background, highlighted).convert("RGB").save(root / "frame.jpg", quality=80)
            self.assertGreater(listening.check_hook_highlight(root / "frame.jpg",
                                                             root / "highlight.png")["matching_fraction"], 0.4)
            Image.alpha_composite(background, plain).convert("RGB").save(root / "frame.png")
            with self.assertRaisesRegex(ValueError, "highlight is missing"):
                listening.check_hook_highlight(root / "frame.png", root / "highlight.png")

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

    def test_five_second_reading_countdown_ends_at_listening(self):
        data = episode()
        data["timing"]["reading_seconds"] = 5
        audio = {"frames": 24000, "sample_rate": 24000}
        timeline = listening.timeline_for(data, audio, audio, audio)
        phases = timeline["phases"]
        reading = [phase for phase in phases if phase["name"].startswith("reading_")]
        self.assertEqual([phase["name"] for phase in reading],
                         [f"reading_{remaining}" for remaining in range(5, 0, -1)])
        self.assertTrue(all(phase["end_frame"] - phase["start_frame"] == 24 for phase in reading))
        listening_phase = next(phase for phase in phases if phase["name"] == "listening")
        self.assertEqual(reading[-1]["end_frame"], listening_phase["start_frame"])

    def test_build_synthesizes_the_visible_title_as_the_hook(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            data, files, _, source, answer, _ = reuse_fixture(root)
            hook = source / "audio" / "hook-fixture.wav"
            with (patch.object(listening, "load_episode", return_value=(data, files)),
                  patch.object(listening, "make_overlay"),
                  patch.object(listening, "prepare_hook_alignment", side_effect=fake_hook_alignment),
                  patch.object(listening, "synthesize", return_value=[{"audio": str(hook)}, {"audio": str(answer)}]) as synth):
                listening.build_listening.__wrapped__("unused", root / "new", until="audio")
            turns = synth.call_args.args[0]["turns"]
            self.assertEqual(turns[0]["text"], data["title"])
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
