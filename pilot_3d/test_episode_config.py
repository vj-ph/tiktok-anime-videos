import copy
import json
from pathlib import Path
import tempfile
import unittest
import wave
from unittest.mock import patch

from episode_config import (PROFILES, check_timeline, duration_limit, read_episode, takeaway_seconds, task_window,
                            validate_template)
from pipeline import audio_reuse_spec, build_episode
from episode_profiles import language_code, language_profile
from prepare_audio import (atomic_json, build_timeline, ceil_frames, content_hash, inspect_wav,
                           make_cache_payload, sha256_file)
from produce_v4 import camera_at_frame, camera_shots, plan_promo
from render import ass_time
from social_captions import (audit_ass, caption_pages, frame_safe_time, make_ass,
                             validate_layout, write_publication)

ROOT = Path(__file__).resolve().parent


def example():
    return read_episode(ROOT / "episodes/lerntreff.json")


def clock(episode, seconds=6):
    infos = [{"frames": round(seconds * 48000), "sample_rate": 48000, "audio": "/synthetic.wav"}
             for _ in episode["turns"]]
    cues = [[{"start": 0, "end": seconds, "value": "X"}] for _ in infos]
    timeline = build_timeline(episode, infos, cues)
    for turn in timeline["turns"]:
        tokens = turn["text"].split()
        step = (seconds - 0.4) / len(tokens)
        turn["words"] = [{"word": token, "start": 0.15 + i * step,
                          "end": 0.15 + i * step + step * 0.85, "score": 0.9}
                         for i, token in enumerate(tokens)]
    return timeline


class EpisodeConfigTests(unittest.TestCase):
    def test_authored_duration_limit_is_strict_on_the_encoded_frame_clock(self):
        episode = example()
        timeline = clock(episode)
        seconds = timeline["total_frames"] / timeline["fps"]
        episode["source"] = {"duration_limit_seconds": seconds + 1 / timeline["fps"]}
        check_timeline(episode, timeline)
        for limit in (seconds, seconds - 1 / timeline["fps"]):
            episode["source"]["duration_limit_seconds"] = limit
            with self.assertRaisesRegex(ValueError, "strictly below"):
                check_timeline(episode, timeline)
        for limit in (0, -1, float("inf"), float("nan"), True, "90", None):
            episode["source"]["duration_limit_seconds"] = limit
            with self.assertRaisesRegex(ValueError, "source.duration_limit_seconds"):
                duration_limit(episode)
            with self.assertRaisesRegex(ValueError, "source.duration_limit_seconds"):
                validate_template(episode)

    def test_both_shipped_episodes_validate(self):
        for path in (ROOT / "episode_v4.json", ROOT / "episodes/lerntreff.json"):
            with self.subTest(path=path):
                episode = read_episode(path)
                validate_template(episode, check_assets=True)
                validate_layout(episode)

    def test_shipped_episodes_use_shared_voice_profiles_with_their_matching_transcript(self):
        shared = (ROOT / "../../shared-voices/qwen3-tts-german").resolve()
        profiles = {"examiner": "male_middle_aged", "candidate_a": "female_young_adult",
                    "candidate_b": "male_young_adult"}
        for path in (ROOT / "episode.json", ROOT / "episode_v4.json", ROOT / "episodes/lerntreff.json"):
            episode = read_episode(path)
            for role, voice in episode["voices"].items():
                with self.subTest(path=path, role=role):
                    self.assertEqual((path.parent / voice["audio"]).resolve(), shared / (profiles[role] + ".wav"))
                    self.assertEqual((path.parent / voice["transcript"]).resolve(), shared / "reference_text.txt")

    def test_paths_follow_an_external_episode_not_the_project_or_build(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "configs").mkdir()
            (root / "media").mkdir()
            data = json.loads((ROOT / "episodes/lerntreff.json").read_text())
            data["book_cover"] = "../media/cover.png"
            data["scene"]["base_scene"] = "../media/room.blend"
            data["scene"]["wall_logo"] = "../media/logo.png"
            for voice in data["voices"].values():
                voice.update(audio="../media/voice.wav", transcript="../media/voice.txt")
            path = root / "configs/custom.json"
            atomic_json(path, data)
            loaded = read_episode(path)
            self.assertEqual(loaded["book_cover"], str(root / "media/cover.png"))
            self.assertEqual(loaded["scene"]["base_scene"], str(root / "media/room.blend"))
            self.assertEqual(loaded["scene"]["wall_logo"], str(root / "media/logo.png"))
            self.assertEqual(loaded["voices"]["candidate_a"]["audio"], str(root / "media/voice.wav"))
            snapshot = root / "snapshot.json"
            atomic_json(snapshot, loaded)
            self.assertEqual(read_episode(snapshot), loaded)
            self.assertEqual(json.loads(path.read_text()), data)

    def test_arbitrary_ids_and_topic_reach_all_visible_surfaces(self):
        episode = example()
        episode.update(title="Unser neues Thema", hook="Ein anderer Dialog",
                       task_card=[], takeaway_title="NEUE TIPPS",
                       cta=["Neue Übungsdialoge", "Unser anderes Buch", "Buchlink im Profil"])
        episode["header"] = {"brand": "TEST · SPRECHEN", "topic": "Unser neues Thema"}
        for turn, name in zip(episode["turns"], ("alpha", "reply-42", "last")):
            turn["id"] = name
        timeline = clock(episode)
        check_timeline(episode, timeline)
        ass = make_ass(episode, timeline)
        for value in ("Unser neues Thema", "Ein anderer Dialog", "NEUE TIPPS", "Unser anderes Buch", "Buchlink im Profil"):
            self.assertIn(value, ass)
        for value in ("Ausflug", "Sonntag", "Münster", "DEIN NÄCHSTER SCHRITT"):
            self.assertNotIn(value, ass)
        self.assertIsNone(task_window(timeline))
        self.assertEqual(camera_shots(episode, timeline)[0][1], "candidate_a")
        with tempfile.TemporaryDirectory() as directory:
            build = Path(directory)
            write_publication(build, episode)
            caption = (build / "publishing_caption.txt").read_text()
            self.assertIn("Unser neues Thema", caption)
            self.assertIn("Unser anderes Buch", caption)
            self.assertIn("Snow Rig", caption)
            self.assertNotIn("Ausflug", caption)
            self.assertTrue(audit_ass(build, ass)["all_inside"])

    def test_instruction_phase_is_independent_of_turn_ids(self):
        episode = read_episode(ROOT / "episode_v4.json")
        episode["turns"][1].pop("task_card_delay_seconds", None)
        for i, turn in enumerate(episode["turns"]):
            turn["id"] = f"custom-turn-{i}"
        timeline = clock(episode)
        window = task_window(timeline)
        self.assertEqual(window, (timeline["turns"][1]["end"], timeline["turns"][2]["start"]))
        pages = caption_pages(episode, timeline)
        last_instruction = [p for p in pages if p["turn_id"] == "custom-turn-1"][-1]
        self.assertEqual(last_instruction["end"], round(window[0] * 100) / 100)
        self.assertIn("DEINE AUFGABE", make_ass(episode, timeline))

    def test_examiner_holds_before_eight_second_task_card_and_then_lea_begins(self):
        episode = read_episode(ROOT / "episode_v4.json")
        episode["turns"][1]["id"] = "custom-instruction"
        timeline = clock(episode)
        check_timeline(episode, timeline)
        instruction, lea = timeline["turns"][1:3]
        fps = timeline["fps"]
        start, end = task_window(timeline)
        self.assertEqual(instruction["task_card_delay_seconds"], 1.2)
        self.assertEqual(round((start - instruction["end"]) * fps), 29)
        self.assertAlmostEqual(end - start, 8)
        self.assertEqual(end, lea["start"])
        shots = camera_shots(episode, timeline)
        markers = [{"frame": 1 + round(t * fps), "camera": name} for t, name in shots]
        self.assertEqual(camera_at_frame(markers, round(start * fps)), "examiner")
        self.assertEqual(camera_at_frame(markers, 1 + round(start * fps)), "candidates")
        self.assertEqual(camera_at_frame(markers, 1 + round(end * fps)), "candidate_a")
        last_page = [page for page in caption_pages(episode, timeline)
                     if page["turn_id"] == instruction["id"]][-1]
        self.assertEqual(last_page["end"], round(frame_safe_time(start, fps) * 100) / 100)
        ass = make_ass(episode, timeline)
        card = [line for line in ass.splitlines() if "DEINE AUFGABE" in line]
        self.assertEqual(len(card), 1)
        self.assertTrue(card[0].startswith(
            f"Dialogue: 0,{ass_time(frame_safe_time(start, fps))},{ass_time(frame_safe_time(end, fps))},"))

    def test_instruction_hold_validates_scope_values_and_frame_quantization(self):
        for value in (-1, True, "1.2", float("nan"), float("inf"), 9.2, 10):
            with self.subTest(delay=value):
                episode = read_episode(ROOT / "episode_v4.json")
                episode["turns"][1]["task_card_delay_seconds"] = value
                with self.assertRaises(ValueError):
                    validate_template(episode)
        for variant in ("dialogue", "missing_card", "no_encoded_card_frame"):
            with self.subTest(variant=variant):
                episode = read_episode(ROOT / "episode_v4.json")
                if variant == "dialogue":
                    episode["turns"][2]["task_card_delay_seconds"] = 1.2
                elif variant == "missing_card":
                    episode["task_card"] = []
                else:
                    episode["turns"][1].update(pause_after=.02, task_card_delay_seconds=.01)
                    self.assertEqual(ceil_frames(.02, episode["fps"]), ceil_frames(.01, episode["fps"]))
                with self.assertRaisesRegex(ValueError, "task_card_delay_seconds"):
                    validate_template(episode)

    def test_task_window_rejects_a_hold_that_exhausts_the_prepared_pause(self):
        timeline = clock(read_episode(ROOT / "episode_v4.json"))
        timeline["turns"][1]["task_card_delay_seconds"] = timeline["turns"][1]["pause_after"]
        with self.assertRaisesRegex(ValueError, "no task-card reading time"):
            task_window(timeline)

    def test_v4_ends_with_only_a_six_second_book_cta(self):
        episode = read_episode(ROOT / "episode_v4.json")
        self.assertEqual(episode["takeaway"], [])
        self.assertNotIn("takeaway_title", episode)
        self.assertEqual(takeaway_seconds(episode), 0)
        self.assertEqual(episode["outro_seconds"], 6)
        timeline = clock(episode)
        ass = make_ass(episode, timeline)
        self.assertNotIn("TIPPS FÜR EUREN DIALOG", ass)
        self.assertNotIn("Einen Vorschlag machen.", ass)
        self.assertIn("Amazon-Buchlink im Profil", ass)
        cta = [line for line in ass.splitlines() if "Amazon-Buchlink im Profil" in line]
        self.assertEqual(len(cta), 1)
        self.assertTrue(cta[0].startswith(
            f"Dialogue: 0,{ass_time(frame_safe_time(timeline['duration'] - 6, timeline['fps']))},"
            f"{ass_time(frame_safe_time(timeline['duration'], timeline['fps']))},"))

    def test_invalid_template_camera_phase_and_layout_fail_explicitly(self):
        variants = []
        data = example()
        data["scene"]["template"] = "unknown"
        variants.append(data)
        data = example()
        data["turns"][0]["camera"] = "candidate_b"
        variants.append(data)
        data = example()
        data["turns"][1]["phase"] = "unknown"
        variants.append(data)
        data = example()
        data["scene"]["entrance"] = True
        variants.append(data)
        data = example()
        data["scene"]["wall_logo"] = ""
        variants.append(data)
        for data in variants:
            with self.subTest(data=data), self.assertRaises(ValueError):
                validate_template(data)
        data = example()
        data["header"]["brand"] = "Zu viel Text " * 10
        with self.assertRaisesRegex(ValueError, "overlaps"):
            validate_layout(data)

    def test_promo_uses_custom_hook_id_lengths_and_contiguous_selection(self):
        episode = example()
        episode["promo"].update(turn_ids=["offer-place", "confirm-plan"],
                                min_seconds=10, max_seconds=25, hook="UNSER PROMO")
        result, timeline, start, stop, lead, tail = plan_promo(episode, clock(episode))
        self.assertEqual(result["id"], "b1_lerntreff_promo")
        self.assertEqual(result["hook"], "UNSER PROMO")
        self.assertEqual([turn["id"] for turn in timeline["turns"]], ["offer-place", "confirm-plan"])
        self.assertEqual((lead, tail), (48, 96))
        self.assertEqual(timeline["total_frames"], lead + stop - start + tail)
        self.assertIn("UNSER PROMO", make_ass(result, timeline))
        episode["promo"]["turn_ids"] = ["propose-time", "confirm-plan"]
        with self.assertRaisesRegex(ValueError, "consecutive"):
            validate_template(episode)
        with self.assertRaisesRegex(ValueError, "consecutive"):
            plan_promo(episode, clock(episode))

    def test_auto_promo_does_not_hide_an_examiner_interruption(self):
        episode = example()
        episode["turns"][1].update(speaker="examiner", phase="dialogue", camera="examiner")
        episode["voices"]["examiner"] = copy.deepcopy(episode["voices"]["candidate_a"])
        episode["promo"].update(min_seconds=15, max_seconds=30)
        with self.assertRaisesRegex(ValueError, "No contiguous"):
            plan_promo(episode, clock(episode))

    def test_profiles_separate_preview_from_full_rate_production(self):
        self.assertEqual(PROFILES["preview"]["motion_step"], 2)
        self.assertEqual(PROFILES["production"]["motion_step"], 1)
        self.assertGreater(PROFILES["production"]["samples"], PROFILES["preview"]["samples"])


class PipelineCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.episode = example()
        asset = self.root / "asset.bin"
        asset.write_bytes(b"explicit synthetic checkpoint asset")
        self.episode["scene"]["base_scene"] = str(asset)
        self.episode["book_cover"] = str(asset)
        for voice in self.episode["voices"].values():
            voice.update(audio=str(asset), transcript=str(asset))
        self.path = self.root / "episode.json"
        atomic_json(self.path, self.episode)
        self.build = self.root / "output"

    def run_fake_command(self, command, log):
        strings = list(map(str, command))
        if any(value.endswith("prepare_audio.py") for value in strings):
            timeline = clock(self.episode)
            atomic_json(self.build / "audio_timeline.json", timeline)
            atomic_json(self.build / "timeline.json", timeline)
            (self.build / "dialogue.wav").write_bytes(b"explicit synthetic checkpoint audio")
        elif any(value.endswith("align_words.py") for value in strings):
            timeline = json.loads((self.build / "timeline.json").read_text())
            timeline["word_alignment"] = {"fixture": True}
            atomic_json(self.build / "timeline.json", timeline)
            atomic_json(self.build / "word_alignment.json", {"fixture": True})
        else:
            self.fail(f"Unexpected mocked command: {strings}")

    def test_resume_skips_verified_audio_and_alignment_and_keeps_snapshot(self):
        with patch("pipeline.preflight", return_value=self.episode), \
                patch("pipeline.caption_preflight"), \
                patch("pipeline.run_command", side_effect=self.run_fake_command) as run:
            build_episode(self.path, self.build, until="audio")
            self.assertEqual(run.call_count, 2)
            before = sha256_file(self.build / "episode.json")
            build_episode(self.path, self.build, until="audio")
            self.assertEqual(run.call_count, 2)
            self.assertEqual(before, sha256_file(self.build / "episode.json"))

    def test_stage_notifications_follow_success_and_distinguish_checkpoint_reuse(self):
        with patch("pipeline.preflight", return_value=self.episode), \
                patch("pipeline.caption_preflight"), \
                patch("pipeline.run_command", side_effect=self.run_fake_command), \
                patch("pipeline.stage_completed") as completed:
            build_episode(self.path, self.build, until="audio")
            self.assertEqual([call.args[0] for call in completed.call_args_list], ["audio", "alignment"])
            completed.reset_mock()
            build_episode(self.path, self.build, until="audio")
            self.assertEqual([call.kwargs for call in completed.call_args_list],
                             [{"reused": True, "force": True}, {"reused": True, "force": True}])

    def test_failed_stage_does_not_emit_completion(self):
        with patch("pipeline.preflight", return_value=self.episode), \
                patch("pipeline.run_command", side_effect=RuntimeError("synthetic stage failure")), \
                patch("pipeline.stage_completed") as completed:
            with self.assertRaises(RuntimeError):
                build_episode(self.path, self.build, until="audio")
        completed.assert_not_called()

    def test_modified_asset_rejects_resume_instead_of_using_stale_voice(self):
        with patch("pipeline.preflight", return_value=self.episode), \
                patch("pipeline.caption_preflight"), \
                patch("pipeline.run_command", side_effect=self.run_fake_command):
            build_episode(self.path, self.build, until="audio")
            Path(self.episode["book_cover"]).write_bytes(b"changed asset")
            with self.assertRaisesRegex(ValueError, "different episode"):
                build_episode(self.path, self.build, until="audio")

    def test_render_backend_and_speech_device_are_frozen_and_forwarded(self):
        with patch("pipeline.preflight", return_value=self.episode), \
                patch("pipeline.caption_preflight"), \
                patch("pipeline.check_render_device") as probe, \
                patch("pipeline.run_command", side_effect=self.run_fake_command) as run:
            build_episode(self.path, self.build, until="audio", render_device="HIP", speech_device="cuda:0")
            probe.assert_called_once_with("HIP")
            command = list(map(str, run.call_args_list[0].args[0]))
            self.assertEqual(command[command.index("--device") + 1], "cuda:0")
            state = json.loads((self.build / "pipeline_state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["spec"]["render_device"], "HIP")
            self.assertEqual(state["spec"]["speech_device"], "cuda:0")
            with self.assertRaisesRegex(ValueError, "different episode"):
                build_episode(self.path, self.build, until="audio", render_device="CPU", speech_device="cuda:0")

    def test_raw_speech_cache_is_an_optional_performance_hint_not_content_reuse(self):
        source = self.root / "speech-source"
        (source / "audio").mkdir(parents=True)
        with patch("pipeline.preflight", return_value=self.episode), \
                patch("pipeline.caption_preflight"), \
                patch("pipeline.run_command", side_effect=self.run_fake_command) as run:
            build_episode(self.path, self.build, until="audio", speech_cache_from=source)
            first = list(map(str, run.call_args_list[0].args[0]))
            self.assertIn("--speech-cache-from", first)
            self.assertEqual(first[-1], str(source))
            build_episode(self.path, self.build, until="audio")
            self.assertEqual(run.call_count, 2)
        self.assertEqual(json.loads((self.build / "pipeline_state.json").read_text())["speech_cache_from"], str(source))

    def test_unowned_nonempty_build_is_never_overwritten(self):
        self.build.mkdir()
        original = self.build / "pilot.mp4"
        original.write_bytes(b"do not overwrite this existing video")
        with patch("pipeline.preflight", return_value=self.episode), \
                self.assertRaisesRegex(ValueError, "nonempty"):
            build_episode(self.path, self.build, until="audio")
        self.assertEqual(original.read_bytes(), b"do not overwrite this existing video")

    def reuse_source(self):
        source = self.root / "source"
        source.mkdir()
        timeline = clock(self.episode)
        timeline["word_alignment"] = {"fixture": True, "language": language_code(self.episode)}

        def wav(path, frames):
            with wave.open(str(path), "wb") as output:
                output.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
                output.writeframes((b"\xe8\x03\x18\xfc" * ((frames + 1) // 2))[:frames * 2])

        wav(source / "dialogue.wav", timeline["total_frames"] * 2000)
        for turn in timeline["turns"]:
            raw = source / (turn["id"] + ".wav")
            wav(raw, round(turn["wav_duration"] * 48000))
            turn["raw_audio"] = str(raw)
            turn["alignment_key"] = turn["id"] + "-fixture"
            voice = self.episode["voices"][turn["speaker"]]
            payload = make_cache_payload(
                turn, Path(voice["audio"]), Path(voice["transcript"]) if "transcript" in voice else None,
                {"language": language_profile(self.episode)["tts"]}, reference_text=voice.get("reference_text"))
            atomic_json(raw.with_suffix(".cache.json"), {
                "cache_key": content_hash(payload), "payload": payload,
                "wav_sha256": sha256_file(raw), "audio_info": inspect_wav(raw)})
        atomic_json(source / "timeline.json", timeline)
        atomic_json(source / "word_alignment.json", {
            "provenance": timeline["word_alignment"], "turns": [
                {key: turn[key] for key in ("id", "start", "words", "alignment_key")} for turn in timeline["turns"]]})
        atomic_json(source / "export_manifest.json", {
            "files_sha256": {name: sha256_file(source / name) for name in ("dialogue.wav", "timeline.json")}})
        return source

    def test_french_inline_references_support_exact_verified_reuse(self):
        self.episode["language"] = "fr"
        for voice in self.episode["voices"].values():
            voice["reference_text"] = Path(voice.pop("transcript")).read_text()
        source = self.reuse_source()
        receipt = audio_reuse_spec(self.episode, source)
        self.assertEqual(receipt["source"], str(source))
        with patch("pipeline.preflight", return_value=self.episode), \
                patch("pipeline.caption_preflight"), patch("pipeline.run_command") as run:
            build_episode(self.path, self.build, until="audio", reuse_audio=source)
        run.assert_not_called()
        self.assertEqual((source / "dialogue.wav").read_bytes(), (self.build / "dialogue.wav").read_bytes())

    def test_reuse_rejects_wrong_alignment_and_synthesis_languages(self):
        source = self.reuse_source()
        alignment_path = source / "word_alignment.json"
        original = json.loads(alignment_path.read_text())
        bad = copy.deepcopy(original)
        bad["provenance"]["language"] = "fr"
        atomic_json(alignment_path, bad)
        with self.assertRaisesRegex(ValueError, "alignment language"):
            audio_reuse_spec(self.episode, source)
        atomic_json(alignment_path, original)
        timeline = json.loads((source / "timeline.json").read_text())
        metadata_path = Path(timeline["turns"][0]["raw_audio"]).with_suffix(".cache.json")
        saved = json.loads(metadata_path.read_text())
        saved["payload"]["settings"]["language"] = "French"
        saved["cache_key"] = content_hash(saved["payload"])
        atomic_json(metadata_path, saved)
        with self.assertRaisesRegex(ValueError, "synthesis language"):
            audio_reuse_spec(self.episode, source)

    def test_visual_revision_reuses_exact_audio_and_alignment_without_models(self):
        source = self.reuse_source()
        with patch("pipeline.preflight", return_value=self.episode), \
                patch("pipeline.caption_preflight"), patch("pipeline.run_command") as run:
            build_episode(self.path, self.build, until="audio", reuse_audio=source)
            build_episode(self.path, self.build, until="audio", reuse_audio=source)
            run.assert_not_called()
        for name in ("dialogue.wav", "timeline.json", "word_alignment.json"):
            self.assertEqual(sha256_file(source / name), sha256_file(self.build / name))
        self.assertIn("no resynthesis", json.loads((self.build / "audio_reuse.json").read_text())["policy"])

    def test_audio_reuse_rejects_changed_dialogue_clock_and_reference_voices(self):
        source = self.reuse_source()
        changed = copy.deepcopy(self.episode)
        changed["turns"][0]["text"] += " Anders."
        with self.assertRaisesRegex(ValueError, "regenerate audio"):
            audio_reuse_spec(changed, source)
        changed = copy.deepcopy(self.episode)
        changed["intro_seconds"] += 1
        with self.assertRaisesRegex(ValueError, "intro/outro"):
            audio_reuse_spec(changed, source)
        Path(self.episode["voices"]["candidate_a"]["transcript"]).write_text("Different reference.")
        with self.assertRaisesRegex(ValueError, "different text/reference"):
            audio_reuse_spec(self.episode, source)

    def test_audio_reuse_follows_moved_raw_cache_without_rewriting_frozen_timeline(self):
        source = self.reuse_source()
        old = self.root / "build_voice"
        timeline = json.loads((source / "timeline.json").read_text())
        for turn in timeline["turns"]:
            turn["raw_audio"] = str(old / Path(turn["raw_audio"]).name)
        atomic_json(source / "timeline.json", timeline)
        manifest = json.loads((source / "export_manifest.json").read_text())
        manifest["files_sha256"]["timeline.json"] = sha256_file(source / "timeline.json")
        atomic_json(source / "export_manifest.json", manifest)
        before = {name: sha256_file(source / name) for name in
                  ("timeline.json", "dialogue.wav", "word_alignment.json", "export_manifest.json")}
        moved = self.root / "builds/voice"
        moved.parent.mkdir()
        source.rename(moved)
        with patch("build_paths.ROOT", self.root), patch("build_paths.BUILDS", moved.parent):
            receipt = audio_reuse_spec(self.episode, old)
        self.assertEqual(receipt["source"], str(moved))
        self.assertEqual(len(receipt["voice_cache_sha256"]), len(timeline["turns"]))
        self.assertEqual(before, {name: sha256_file(moved / name) for name in before})
        self.assertFalse(old.exists())

    def test_audio_reuse_rejects_tampered_source_and_alignment(self):
        source = self.reuse_source()
        sidecar = json.loads((source / "word_alignment.json").read_text())
        sidecar["turns"][0]["words"][0]["word"] = "Falsch"
        atomic_json(source / "word_alignment.json", sidecar)
        with self.assertRaisesRegex(ValueError, "sidecar differs"):
            audio_reuse_spec(self.episode, source)
        (source / "dialogue.wav").write_bytes(b"unverified replacement")
        with self.assertRaisesRegex(ValueError, "not a verified delivery"):
            audio_reuse_spec(self.episode, source)


if __name__ == "__main__":
    unittest.main()
