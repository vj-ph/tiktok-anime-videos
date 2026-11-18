"""Portable regression tests for new-episode routing and build pins."""

import contextlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import listening_2d.listening_pipeline as pipeline


class ListeningPipelineTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.cover = self.root / "cover.jpg"
        self.cover.write_bytes(b"fixture cover")

    def fixture(self, filename, profile):
        episode = pipeline.read(pipeline.ROOT / "episodes" / filename)
        episode["id"] = profile + "-episode-02"
        episode["source"] = {}
        episode["promotion"]["cover" if profile == "fide" else "cover_source"] = self.cover.name
        episode["promotion"].pop("cover_sha256", None)
        return episode

    def a2(self):
        episode = self.fixture("oeif_a2_listening_01.json", "oeif-a2")
        revision = pipeline.read(pipeline.ROOT / "episodes" / "oeif_a2_listening_01_revision_r2.json")
        episode["timing"].update(revision["timing"])
        episode["opening"] = revision["opening"]
        return episode

    def test_existing_german_profiles_plan_second_episodes_from_data(self):
        a2 = self.a2()
        group = a2["sections"][0]["groups"][0]
        group["id"] = "new_voicemail"
        group["recording"][0]["text"] = "Das ist die neue Nachricht."
        b1 = self.fixture("oeif_b1_listening_01.json", "oeif-b1")
        b1["instruction_template"] = str(pipeline.ROOT / "instruction_templates.json")
        b2 = self.fixture("oeif_b2_listening_01.json", "oeif-b2")
        interview = b2["sections"][1]["groups"][0]
        interview["id"] = "another_interview"
        for turn in interview["recording"]:
            if turn["id"] == "interview_q51":
                turn["id"] = "new_question_51"
        b2["interview_page2_at"] = "new_question_51"
        fide = self.fixture("fide_a2_b1_listening_01.json", "fide")
        for section in fide["situations"]:
            for item in section["items"]:
                if "image" in item:
                    item["image"] = self.cover.name

        for profile, episode in (("oeif-a2", a2), ("oeif-b1", b1), ("oeif-b2", b2), ("fide", fide)):
            with self.subTest(profile=profile):
                source = self.root / f"{profile}.json"
                pipeline.atomic_json(source, episode)
                config, speech, _ = pipeline.plan(profile, source)
                self.assertEqual(config["episode"]["id"], episode["id"])
                measured = {t["id"]: {**t, "frames": 96000, "audio": "fixture.wav",
                                      "sha256": t["id"], "wav_duration": 2} for t in speech["turns"]}
                measured.update({k: {"audio": "cue.wav", "sha256": k, "frames": 2000}
                                 for k in pipeline.CUES})
                timeline = pipeline.schedule(profile, speech, measured)
                if profile == "oeif-a2":
                    from listening_2d.checks.audit_a2_sequence import compare_sequence
                    result = compare_sequence(config["episode"], timeline)
                    self.assertTrue(result["matches_requested_sequence"], result["issues"])
                    repeat = [e for e in timeline["events"] if e.get("audio_id") == "new_voicemail_audio_1"]
                    self.assertEqual([e["text"] for e in repeat], ["Das ist die neue Nachricht."] * 2)
                elif profile == "oeif-b1":
                    from listening_2d.checks.validate_full import check_structure
                    self.assertEqual(check_structure(timeline, config)["p4_statements_read"], 60)
                elif profile == "oeif-b2":
                    from listening_2d.checks.audit_b2_sequence_r3 import compare_sequence
                    from listening_2d.rendering.compose_b2_r3 import visual_plan
                    result = compare_sequence(config["episode"], timeline)
                    self.assertTrue(result["matches_requested_sequence"], result["issues"])
                    reveals = [e for e in visual_plan(timeline, "portrait")
                               if e["card"] == "another_interview" and e["kind"] == "reveal"]
                    self.assertEqual([e["page"] for e in reveals], [1, 2])
                else:
                    from listening_2d.checks.audit_fide_sequence import compare_sequence
                    result = compare_sequence(timeline)
                    self.assertTrue(result["ok"], result["issues"])

    def test_episode_plan_refuses_changed_inputs_and_requires_exact_approval(self):
        source, build, approval = (self.root / name for name in ("episode.json", "build", "approval.json"))
        pipeline.atomic_json(source, self.a2())
        common = ["--profile", "oeif-a2", "--episode", str(source), "--build", str(build)]
        with patch.object(pipeline, "synthesize") as synthesize, contextlib.redirect_stdout(None):
            pipeline.main(["plan", *common])
            self.assertFalse((build / "audio").exists())
            pipeline.atomic_json(approval, {"episode_sha256": pipeline.sha256_file(source),
                                            "plan_sha256": "wrong"})
            with self.assertRaisesRegex(ValueError, "approval"):
                pipeline.main(["prepare", *common, "--approval", str(approval)])
            self.cover.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "inputs changed"):
                pipeline.main(["plan", *common])
            synthesize.assert_not_called()

    def test_a2_second_episode_build_uses_approved_content_and_exact_pcm(self):
        source, build, approval = (self.root / name for name in ("episode.json", "build", "approval.json"))
        episode = self.a2()
        episode["sections"][0]["groups"][0]["recording"][0]["text"] = "Die neue Nachricht."
        pipeline.atomic_json(source, episode)
        common = ["--profile", "oeif-a2", "--episode", str(source), "--build", str(build)]
        pipeline.main(["plan", *common])
        review = self.root / "review.txt"
        review.write_text("Test reviewer fixture.", encoding="utf-8")
        pipeline.atomic_json(approval, {
            "episode_sha256": pipeline.sha256_file(source),
            "plan_sha256": pipeline.sha256_file(build / "episode_plan.json"),
            "script_approved": True, "reviewer_model": "claude-sonnet-5.5",
            "review_status": "pass", "review_files": {review.name: pipeline.sha256_file(review)},
        })

        def fake_normalize(_source, target, _effect=None):
            pipeline.write_wav(target, b"\x01\x00" * 2000)
            return {"frames": 2000, "wav_duration": 1 / 24}

        def fake_synthesize(speech, *_args):
            return [{"audio": str(self.root / "mock_raw.wav")} for _ in speech["turns"]]

        with (patch.object(pipeline, "voices", return_value=({}, {})),
              patch.object(pipeline, "synthesize", side_effect=fake_synthesize) as synthesize,
              patch.object(pipeline, "prepare_turn_audio", return_value={}),
              patch.object(pipeline, "tempo_turn_audio", return_value={"audio": str(self.cover)}),
              patch.object(pipeline, "normalize", side_effect=fake_normalize)):
            pipeline.main(["prepare", *common, "--approval", str(approval)])
        self.assertIn("Die neue Nachricht.", [t["text"] for t in synthesize.call_args.args[0]["turns"]])
        pipeline.validate(build, "oeif-a2", source)
        from listening_2d.rendering.compose_a2_r2 import compose
        timeline = pipeline.read(build / "timeline.json")
        for turn in timeline["turns"]:
            if turn["id"].startswith("instruction_"):
                words = turn["text"].split()
                step = turn["wav_duration"] / (len(words) + 1)
                turn["words"] = [{"word": word, "start": i * step, "end": (i + 1) * step,
                                  "score": .9} for i, word in enumerate(words)]
        pipeline.atomic_json(build / "timeline.json", timeline)
        # Composition copies assets without decoding them; use local fixtures so no Node/font install is needed.
        assets = dict.fromkeys(("gsap.min.js", "arial.ttf", "arialbd.ttf"), self.cover)
        compose(build, fonts=assets)
        for layout in pipeline.LAYOUTS:
            html = (build / layout / "index.html").read_text(encoding="utf-8")
            self.assertIn("<h1>ÖIF A2 Hören</h1>", html)
            self.assertNotIn("{{", html)
        mix = build / "dialogue.wav"
        with mix.open("r+b") as output:
            output.seek(44)
            output.write(b"\xff")
        with self.assertRaisesRegex(ValueError, "Unexpected audio"):
            pipeline.validate(build, "oeif-a2", source)


if __name__ == "__main__":
    unittest.main()
