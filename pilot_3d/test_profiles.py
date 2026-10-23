import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from check_speech import check_speech, tokens
from episode_config import check_timeline, read_episode, validate_template
from episode_profiles import ACTORS, active_actors, language_code, language_profile, scene_layout
from entrance import entrance_plan
from prepare_audio import (atomic_json, content_hash, make_cache_payload, synthesize,
                           synthesis_settings, validate_episode)
from produce_v4 import camera_shots
from scene_direction import configure_cast, performance_plan
from social_captions import make_ass, write_publication
from test_episode_config import clock, example

ROOT = Path(__file__).resolve().parent


def interview():
    episode = read_episode(ROOT / "episode_v4.json")
    episode["language"] = "fr"
    episode["scene"].update(layout="interview", observer=False)
    episode["voices"].pop("candidate_b")
    episode["turns"] = episode["turns"][:3]
    for turn in episode["turns"]:
        turn.update(look_at="candidate_a" if turn["speaker"] == "examiner" else "examiner")
    return episode


class LanguageTests(unittest.TestCase):
    def test_default_and_explicit_german_are_identical_and_french_is_explicit(self):
        self.assertEqual(language_profile({}), language_profile({"language": "de"}))
        self.assertEqual(language_code({}), "de")
        self.assertEqual(language_profile({"language": "fr"})["tts"], "French")
        self.assertEqual(language_profile({"language": "fr"})["alignment_model"],
                         "VOXPOPULI_ASR_BASE_10K_FR")
        for bad in ("en", "fr-CA", None, False, [], {}):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, "language"):
                language_code({"language": bad})

    def test_synthesis_language_is_in_the_cache_key(self):
        with patch("prepare_audio.importlib.metadata.version", return_value="test"):
            de = synthesis_settings("base", "cpu", 1, "Bonjour.")
            explicit = synthesis_settings("base", "cpu", 1, "Bonjour.", "de")
            fr = synthesis_settings("base", "cpu", 1, "Bonjour.", "fr")
        self.assertEqual(de, explicit)
        self.assertEqual({k: v for k, v in fr.items() if k != "language"},
                         {k: v for k, v in de.items() if k != "language"})
        self.assertEqual(fr["language"], "French")
        self.assertNotEqual(content_hash(de), content_hash(fr))

    def test_inline_reference_text_does_not_require_a_fake_transcript_file(self):
        with tempfile.TemporaryDirectory() as folder:
            audio = Path(folder) / "voice.wav"
            audio.write_bytes(b"reference fixture")
            text = "Bonjour. J'aimerais des précisions."
            payload = make_cache_payload({"speaker": "examiner", "text": "Oui."},
                                         audio, None, {"language": "French"}, reference_text=text)
            self.assertEqual(payload["reference_text"], text)
            self.assertEqual(payload["reference_transcript_sha256"],
                             hashlib.sha256(text.encode()).hexdigest())
            changed = make_cache_payload({"speaker": "examiner", "text": "Oui."},
                                         audio, None, {"language": "French"}, reference_text=text + " Merci.")
            self.assertNotEqual(content_hash(payload), content_hash(changed))
            with self.assertRaisesRegex(ValueError, "not both"):
                make_cache_payload({}, audio, Path(folder) / "unused.txt", {}, reference_text=text)

    def test_reference_form_is_unambiguous(self):
        data = example()
        voice = data["voices"]["candidate_a"]
        voice.pop("transcript")
        voice["reference_text"] = "Bonjour."
        validate_episode(data)
        voice["transcript"] = "unused.txt"
        with self.assertRaisesRegex(ValueError, "exactly one"):
            validate_episode(data)
        voice.pop("reference_text")
        voice.pop("transcript")
        with self.assertRaisesRegex(ValueError, "exactly one"):
            validate_episode(data)

    def test_french_language_survives_audio_clock_and_mismatch_is_rejected(self):
        episode = interview()
        timeline = clock(episode, seconds=16)
        self.assertEqual(timeline["language"], "fr")
        check_timeline(episode, timeline)
        timeline["language"] = "de"
        with self.assertRaisesRegex(ValueError, "different languages"):
            check_timeline(episode, timeline)
        legacy = clock(example())
        self.assertNotIn("language", legacy)
        check_timeline(example(), legacy)

    def test_french_labels_and_publication_have_no_injected_german(self):
        episode = read_episode(ROOT / "episodes/tef_canada_a1.json")
        timeline = clock(episode, seconds=18)
        ass = make_ass(episode, timeline)
        self.assertIn("Intervenant : Candidate", ass)
        for german in ("Es spricht:", "DEUTSCHKOMPASS", "DTZ", "Lernpause"):
            self.assertNotIn(german, ass)
        with tempfile.TemporaryDirectory() as folder:
            write_publication(Path(folder), episode)
            caption = (Path(folder) / "publishing_caption.txt").read_text()
            self.assertIn("Voix de synthèse", caption)
            self.assertIn("Pour cette vidéo", caption)
            self.assertIn("Snow Rig", caption)
            self.assertIn("CC BY 4.0", caption)
            self.assertNotIn("KI-generierte", caption)

    def test_french_gesture_filter_keeps_content_words(self):
        episode = interview()
        episode["turns"][2]["text"] = "Je vous remercie."
        timeline = clock(episode, seconds=12)
        timeline["turns"][2]["words"] = [
            {"word": word, "start": start, "end": start + .2, "score": .9}
            for word, start in (("Je", .5), ("vous", 1), ("remercie.", 1.5))]
        plan = performance_plan(timeline, episode)
        events = [event for event in plan["gestures"] if event["turn_id"] == episode["turns"][2]["id"]]
        self.assertEqual([event["word"] for event in events], ["remercie."])
        self.assertEqual(set(plan["attention"]), {"candidate_a", "examiner"})
        self.assertFalse(any(event["actor"] == "observer" for event in plan["glances"]))

    def test_synthesis_passes_french_and_inline_text_to_the_clone_api_without_loading_models(self):
        import numpy as np
        import soundfile as sf

        episode = interview()
        model = Mock()
        model.generate_voice_clone.return_value = ([np.full(2400, .05)], 24000)
        factory = Mock(return_value=model)
        torch = SimpleNamespace(set_num_threads=Mock(), set_num_interop_threads=Mock(),
                                manual_seed=Mock(), float32="fixture-float32")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            reference = root / "reference.wav"
            sf.write(reference, np.full(2400, .1), 24000, subtype="PCM_16")
            for voice in episode["voices"].values():
                voice.pop("transcript")
                voice.update(audio=str(reference), reference_text="Bonjour, voici une référence.")
            audio = root / "audio"
            audio.mkdir()
            with patch.dict(sys.modules, {
                "torch": torch, "qwen_tts": SimpleNamespace(
                    Qwen3TTSModel=SimpleNamespace(from_pretrained=factory))}), \
                    patch("prepare_audio.importlib.metadata.version", return_value="fixture"):
                result = synthesize(episode, root, audio, "explicit-mock-model", "cpu", 1)
            self.assertEqual(len(result), 3)
            factory.assert_called_once()
            self.assertEqual(model.create_voice_clone_prompt.call_count, 2)
            for call in model.create_voice_clone_prompt.call_args_list:
                self.assertEqual(call.kwargs["ref_text"], "Bonjour, voici une référence.")
                self.assertEqual(call.kwargs["ref_audio"][1], 24000)
                self.assertFalse(call.kwargs["x_vector_only_mode"])
            for call in model.generate_voice_clone.call_args_list:
                self.assertEqual(call.kwargs["language"], "French")
            for path in audio.glob("*.cache.json"):
                saved = json.loads(path.read_text())
                self.assertEqual(saved["payload"]["settings"]["language"], "French")


class AlignmentLanguageTests(unittest.TestCase):
    def test_mismatched_snapshot_is_rejected_before_alignment_model_loading(self):
        from align_words import align_build

        with tempfile.TemporaryDirectory() as folder:
            build = Path(folder)
            atomic_json(build / "timeline.json", {"language": "fr"})
            atomic_json(build / "episode.json", {"language": "de"})
            with self.assertRaisesRegex(ValueError, "different languages"):
                align_build(build)

    def test_loader_cache_and_provenance_use_the_timeline_language_without_loading_models(self):
        from align_words import align_build

        episode = interview()
        timeline = clock(episode, seconds=16)
        torch = SimpleNamespace(set_num_threads=Mock(), hub=SimpleNamespace(get_dir=lambda: "/model-fixture"))
        torchaudio = SimpleNamespace(pipelines=SimpleNamespace(
            VOXPOPULI_ASR_BASE_10K_FR=SimpleNamespace(_path="french-fixture.pt"),
            VOXPOPULI_ASR_BASE_10K_DE=SimpleNamespace(_path="german-fixture.pt")))
        whisperx = SimpleNamespace(load_align_model=Mock(return_value=("model-fixture", {})), align=Mock())

        def align(segments, *args, **kwargs):
            words = segments[0]["text"].split()
            return {"word_segments": [
                {"word": word, "start": index * .3, "end": index * .3 + .2, "score": .9}
                for index, word in enumerate(words)]}

        whisperx.align.side_effect = align
        with tempfile.TemporaryDirectory() as folder:
            build = Path(folder)
            atomic_json(build / "timeline.json", timeline)
            with patch.dict(sys.modules, {"torch": torch, "torchaudio": torchaudio, "whisperx": whisperx}), \
                    patch("align_words.sha256_file", return_value="explicit-fixture-hash"), \
                    patch("align_words.inspect_wav", return_value={"wav_duration": 16}), \
                    patch("align_words.importlib.metadata.version", return_value="fixture"):
                align_build(build)
                whisperx.load_align_model.assert_called_with(
                    language_code="fr", device="cpu", model_name="VOXPOPULI_ASR_BASE_10K_FR")
                french = json.loads((build / "timeline.json").read_text())
                self.assertEqual(french["word_alignment"]["language"], "fr")
                self.assertEqual(french["word_alignment"]["model"], "VOXPOPULI_ASR_BASE_10K_FR")
                self.assertTrue(all(call.kwargs["interpolate_method"] == "ignore"
                                    for call in whisperx.align.call_args_list))
                count = whisperx.align.call_count
                align_build(build)
                self.assertEqual(whisperx.align.call_count, count)
                french["language"] = "de"
                atomic_json(build / "timeline.json", french)
                align_build(build)
                german = json.loads((build / "timeline.json").read_text())
                self.assertEqual(german["word_alignment"]["language"], "de")
                self.assertNotEqual(french["turns"][0]["alignment_key"],
                                    german["turns"][0]["alignment_key"])


class SceneProfileTests(unittest.TestCase):
    def test_legacy_cast_and_performance_are_unchanged(self):
        episode = example()
        self.assertEqual(active_actors(episode), ACTORS)
        explicit = copy.deepcopy(episode)
        explicit.update(language="de")
        explicit["scene"].update(layout="pair", observer=True)
        timeline = clock(episode)
        self.assertEqual(performance_plan(timeline), performance_plan(timeline, explicit))
        self.assertEqual(camera_shots(episode, timeline), camera_shots(explicit, timeline))

    def test_layout_observer_and_exam_metadata_validate_independently(self):
        data = interview()
        data["exam"] = {"family": "tef_canada", "skill": "speaking", "section": "A"}
        validate_template(data)
        self.assertEqual(active_actors(data), ("candidate_a", "examiner"))
        data["scene"]["observer"] = True
        self.assertEqual(active_actors(data), ("candidate_a", "examiner", "observer"))
        for layout in ("unknown", [], {}):
            bad = copy.deepcopy(data)
            bad["scene"]["layout"] = layout
            with self.assertRaisesRegex(ValueError, "scene.layout"):
                validate_template(bad)
        for value in (None, "false", 0):
            bad = copy.deepcopy(data)
            bad["scene"]["observer"] = value
            with self.assertRaisesRegex(ValueError, "observer"):
                validate_template(bad)
        data["exam"]["skill"] = "listening"
        with self.assertRaisesRegex(ValueError, "listening"):
            validate_template(data)

    def test_hidden_actors_cannot_speak_be_addressed_or_supply_a_two_candidate_shot(self):
        for change in ("voice", "gaze", "camera"):
            data = interview()
            if change == "voice":
                data["voices"]["candidate_b"] = copy.deepcopy(data["voices"]["candidate_a"])
            elif change == "gaze":
                data["turns"][0]["look_at"] = "candidate_b"
            else:
                data["turns"][2]["camera"] = "candidates"
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_template(data)

    def test_single_candidate_enters_with_a_finite_door_close_and_no_ghost_partner(self):
        data = interview()
        timeline = clock(data, seconds=16)
        plan = entrance_plan(data, timeline)
        self.assertTrue(plan["enabled"])
        self.assertEqual(set(plan["actors"]), {"candidate_a"})
        self.assertGreater(plan["door"]["close_end"], plan["door"]["close_start"])
        self.assertLess(plan["door"]["close_end"], plan["actors"]["candidate_a"]["seat_end"])
        shots = camera_shots(data, timeline)
        self.assertNotIn("candidates", [camera for _, camera in shots])
        self.assertEqual(shots[-1][1], "wide")

    def test_inactive_rig_children_and_unused_furniture_are_hidden(self):
        objects = []
        for name in ACTORS:
            mesh = SimpleNamespace(name=name + " mesh", hide_render=False, hide_set=Mock())
            mesh.animation_data = SimpleNamespace(
                drivers=[SimpleNamespace(data_path="hide_render", mute=False),
                         SimpleNamespace(data_path="unrelated_native_control", mute=False)])
            objects.append(SimpleNamespace(name=name, children_recursive=[mesh],
                                           hide_render=False, hide_set=Mock(),
                                           parent=None, location=SimpleNamespace(x=-.82, y=.65)))
        objects.append(SimpleNamespace(name="Chair.002", children_recursive=[], hide_render=False,
                                       hide_set=Mock(), parent=None, location=SimpleNamespace(x=.82, y=.65)))
        objects.append(SimpleNamespace(name="Chair.003", children_recursive=[], hide_render=False,
                                       hide_set=Mock(), parent=None, location=SimpleNamespace(x=.82, y=-1.6)))

        class Objects(list):
            def __getitem__(self, key):
                if isinstance(key, str):
                    return next(obj for obj in self if obj.name == key)
                return super().__getitem__(key)

        scene = SimpleNamespace(objects=Objects(objects))
        report = configure_cast(scene, interview())
        self.assertEqual(report["active_actors"], ["candidate_a", "examiner"])
        for name in ("candidate_b", "observer"):
            self.assertTrue(scene.objects[name].hide_render)
            self.assertTrue(scene.objects[name].children_recursive[0].hide_render)
            drivers = scene.objects[name].children_recursive[0].animation_data.drivers
            self.assertTrue(drivers[0].mute)
            self.assertFalse(drivers[1].mute)
        self.assertTrue(scene.objects["Chair.002"].hide_render)
        self.assertFalse(scene.objects["candidate_a"].hide_render)
        self.assertFalse(scene.objects["examiner"].hide_render)
        scene.objects["Chair.003"].hide_render = False
        episode = interview()
        episode["scene"]["observer"] = True
        configure_cast(scene, episode)
        self.assertFalse(scene.objects["Chair.003"].hide_render)


class SpeechCheckTests(unittest.TestCase):
    def test_normalization_does_not_hide_changed_words_or_numbers(self):
        self.assertEqual(tokens("À bientôt, MADAME !"), tokens("à bientôt madame"))
        self.assertNotEqual(tokens("deux places"), tokens("trois places"))
        self.assertNotEqual(tokens("2 places"), tokens("deux places"))

    def test_asr_receives_french_without_the_expected_text_and_records_mismatches(self):
        episode = interview()
        timeline = clock(episode, seconds=16)
        with tempfile.TemporaryDirectory() as folder:
            build = Path(folder)
            audio = build / "fixture.wav"
            audio.write_bytes(b"explicit ASR unit-test fixture; not a delivery")
            for turn in timeline["turns"]:
                turn["audio"] = str(audio)
            atomic_json(build / "episode.json", episode)
            atomic_json(build / "timeline.json", timeline)
            recognizer = Mock()
            recognizer.transcribe.side_effect = [
                (iter([SimpleNamespace(text=turn["text"])]), None) for turn in timeline["turns"]]
            before = audio.read_bytes()
            report = check_speech(build, recognizer=recognizer)
            self.assertTrue(report["all_match"])
            self.assertEqual(report["language"], "fr")
            self.assertEqual(audio.read_bytes(), before)
            for call in recognizer.transcribe.call_args_list:
                self.assertEqual(call.kwargs, {
                    "language": "fr", "beam_size": 5, "vad_filter": False,
                    "condition_on_previous_text": False, "initial_prompt": None})
            recognizer.transcribe.side_effect = [
                (iter([SimpleNamespace(text="Un texte différent.")]), None) for _ in timeline["turns"]]
            report = check_speech(build, recognizer=recognizer)
            self.assertFalse(report["all_match"])
            self.assertFalse(json.loads((build / "speech_asr_check.json").read_text())["all_match"])

    def test_export_and_review_reject_language_mismatch_before_media_processing(self):
        from render import load_inputs
        from review_social import review

        episode = interview()
        timeline = clock(episode, seconds=16)
        timeline["language"] = "de"
        with tempfile.TemporaryDirectory() as folder:
            build = Path(folder)
            atomic_json(build / "episode.json", episode)
            atomic_json(build / "timeline.json", timeline)
            atomic_json(build / "scene_manifest.json", {"episode": episode})
            with self.assertRaisesRegex(ValueError, "languages differ"):
                load_inputs(build, build / "episode.json")
            with self.assertRaisesRegex(ValueError, "different languages"):
                review(build)


if __name__ == "__main__":
    unittest.main()
