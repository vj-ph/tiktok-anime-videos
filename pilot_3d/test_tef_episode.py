import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import wave

from episode_config import check_timeline, read_episode, section_windows, task_window, validate_template
from episode_profiles import active_actors
from picture_presentation import (COMPACT_BOX, FACE_BOX, NOTICE_COMPACT_PANEL,
                                  TASK_REVEAL_BOX, picture_bounds, picture_filters, picture_windows)
from prepare_audio import atomic_json, sha256_file
from produce_v4 import camera_shots
from render import mux, scene_hash
from review_social import review_pictures
from scene_direction import performance_plan
from social_captions import (SAFE, audit_ass, caption_pages, make_ass, validate_layout,
                             write_publication)
from test_episode_config import clock

ROOT = Path(__file__).resolve().parent


class TefEpisodeTests(unittest.TestCase):
    def setUp(self):
        self.path = ROOT / "episodes/tef_canada_a1.json"
        self.episode = read_episode(self.path)

    def test_real_episode_and_external_assets_validate(self):
        validate_template(self.episode, check_assets=True)
        validate_layout(self.episode)
        self.assertEqual(self.episode["language"], "fr")
        self.assertEqual(self.episode["exam"], {"family": "tef_canada", "skill": "speaking", "section": "A"})
        self.assertNotIn("exam_part", self.episode)
        self.assertEqual(active_actors(self.episode), ("candidate_a", "examiner"))
        source = (self.path.parent / self.episode["source"]["book"]).resolve()
        self.assertTrue(source.is_file())
        self.assertIn(self.episode["source"]["exercise"], source.read_text())
        self.assertNotIn("exercises", self.episode["source"])
        self.assertEqual(len(self.episode["pictures"]), 1)

    def test_task_advertisement_and_wall_logo_match_the_approved_original_bytes(self):
        for key, source in self.episode["source"]["images"].items():
            picture = self.episode["pictures"][key]
            self.assertEqual(sha256_file(Path(picture["path"])),
                             sha256_file((self.path.parent / source).resolve()))
            self.assertEqual(picture["purpose"], "task")
            self.assertEqual(picture["candidate"], "candidate_a")
            self.assertIn("2026-10-24", picture["permission"])
            self.assertIn("commercial", picture["permission"])
        self.assertEqual(sha256_file(Path(self.episode["scene"]["wall_logo"])),
                         sha256_file((self.path.parent / self.episode["source"]["logo"]).resolve()))

    def test_task_pictures_keep_real_questions_and_do_not_become_picture_description(self):
        prompt, response = self.episode["turns"][1:3]
        self.assertEqual(prompt["picture"], response["picture"])
        self.assertEqual(response["action"], "ask")
        self.assertEqual(response["camera"], "picture_a")
        self.assertFalse(any(t["action"] == "describe" for t in self.episode["turns"]))
        self.assertTrue(all(t["camera"] == t["speaker"] for t in self.episode["turns"][3:]))
        timeline = clock(self.episode, seconds=18)
        windows = picture_windows(self.episode, timeline)
        self.assertEqual([w["mode"] for w in windows], ["reveal", "compact"])
        self.assertTrue(all(w["purpose"] == "task" for w in windows))
        self.assertIn((windows[0]["start"], "wide"), camera_shots(self.episode, timeline))
        ass = make_ass(self.episode, timeline)
        self.assertIn("Annonce · texte agrandi", ass)
        self.assertIn("Pause · Arrêtez la vidéo.", ass)
        self.assertNotIn("Décrivez l'image.", ass)
        self.assertNotIn("Parlez de votre expérience.", ass)
        self.assertFalse(self.episode["task_card"])

    def test_explicit_notice_crop_matches_approved_reading_and_lower_reference_bounds(self):
        from PIL import Image
        picture = self.episode["pictures"]["atelier_clic_voisin"]
        self.assertEqual(picture["layout"], "notice_detail")
        self.assertEqual(picture["crop"], [236, 44, 966, 538])
        inputs, filters, _, windows = picture_filters(self.episode, clock(self.episode, seconds=18))
        self.assertEqual([w["bounds"] for w in windows],
                         [[56, 370, 664, 782], [104, 790, 424, 1006]])
        self.assertTrue(all(w["crop"] == picture["crop"] for w in windows))
        self.assertTrue(all("crop=730:494:236:44,scale=" in f for f in filters[::2]))
        self.assertEqual(inputs.count(picture["path"]), 2)
        self.assertGreater(windows[1]["bounds"][1], max(FACE_BOX[3], 742))
        self.assertEqual(1280 - NOTICE_COMPACT_PANEL[3], 266)
        self.assertEqual(720 - NOTICE_COMPACT_PANEL[2], 288)
        with Image.open(picture["path"]) as image:
            self.assertEqual(image.size, (1200, 896))

    def test_whole_image_task_layout_remains_the_default(self):
        from PIL import Image
        picture = self.episode["pictures"]["atelier_clic_voisin"]
        picture.pop("layout")
        picture.pop("crop")
        for mode, box in (("reveal", TASK_REVEAL_BOX), ("compact", COMPACT_BOX)):
            x, y, right, bottom = picture_bounds(picture["path"], mode, purpose="task")
            self.assertTrue(box[0] <= x < right <= box[2])
            self.assertTrue(box[1] <= y < bottom <= box[3])
            with Image.open(picture["path"]) as image:
                self.assertLess(abs((right-x)/(bottom-y) - image.width/image.height), .02)
        _, filters, _, windows = picture_filters(self.episode, clock(self.episode, seconds=18))
        self.assertTrue(all("crop=" not in f for f in filters))
        self.assertTrue(all("layout" not in w and "crop" not in w for w in windows))
        self.assertEqual([w["bounds"] for w in windows],
                         [[104, 334, 496, 626], [134, 310, 294, 430]])

    def test_invalid_task_purposes_owners_and_reveal_sequences_fail(self):
        variants = [
            lambda e: e["pictures"]["atelier_clic_voisin"].update(purpose="description"),
            lambda e: e["pictures"]["atelier_clic_voisin"].update(purpose="unknown"),
            lambda e: e["pictures"]["atelier_clic_voisin"].update(purpose=[]),
            lambda e: e["pictures"]["atelier_clic_voisin"].update(candidate="candidate_b"),
            lambda e: e["pictures"]["atelier_clic_voisin"].update(permission=""),
            lambda e: e["turns"][1].pop("picture_card_delay_seconds"),
            lambda e: e["turns"][2].update(action="describe"),
            lambda e: e["turns"][2].update(camera="candidate_a"),
            lambda e: e["turns"][2].pop("picture"),
            lambda e: e["turns"][1].update(picture_card_delay_seconds=9.2),
            lambda e: e.update(task_card=["Overlapping reading card"]),
            lambda e: e["pictures"]["atelier_clic_voisin"].update(layout="unknown"),
            lambda e: e["pictures"]["atelier_clic_voisin"].update(layout="whole"),
            lambda e: e["pictures"]["atelier_clic_voisin"].pop("crop"),
            lambda e: e["pictures"]["atelier_clic_voisin"].update(crop=[True, 44, 966, 538]),
            lambda e: e["pictures"]["atelier_clic_voisin"].update(crop=[236.0, 44, 966, 538]),
            lambda e: e["pictures"]["atelier_clic_voisin"].update(crop=[235, 44, 966, 538]),
            lambda e: e["pictures"]["atelier_clic_voisin"].update(crop=[-2, 44, 966, 538]),
            lambda e: e["pictures"]["atelier_clic_voisin"].update(crop=[236, 44, 966, 46]),
        ]
        for mutate in variants:
            episode = copy.deepcopy(self.episode)
            mutate(episode)
            with self.subTest(mutation=variants.index(mutate)), self.assertRaises(ValueError):
                validate_template(episode)

    def test_notice_crop_cannot_extend_beyond_the_actual_source(self):
        self.episode["pictures"]["atelier_clic_voisin"]["crop"] = [236, 44, 1234, 538]
        with self.assertRaisesRegex(ValueError, "exceeds the source"):
            validate_template(self.episode, check_assets=True)
        with self.assertRaisesRegex(ValueError, "exceeds the source"):
            picture_filters(self.episode, clock(self.episode, seconds=18))

    def test_notice_layout_keeps_speech_headers_and_subtitle_events_identical(self):
        timeline = clock(self.episode, seconds=18)
        revised = make_ass(self.episode, timeline)
        self.assertNotIn("m 96 280 l 332", revised)
        self.assertIn("m 96 758 l 432 758 432 1014 96 1014", revised)
        self.assertIn(r"\pos(104,764)\fs18", revised)
        picture = self.episode["pictures"]["atelier_clic_voisin"]
        picture.pop("layout")
        picture.pop("crop")
        original = make_ass(self.episode, timeline)
        for token in (r"\fs31", "Intervenant :", "FRENCH COMPASS", "Section A"):
            self.assertEqual([line for line in revised.splitlines() if line.startswith("Dialogue:") and token in line],
                             [line for line in original.splitlines() if line.startswith("Dialogue:") and token in line])

    def test_scoped_notice_audit_does_not_relax_ordinary_text_or_graphic_bounds(self):
        ass = make_ass(self.episode, clock(self.episode, seconds=18))
        header = ass[:ass.index("Dialogue:")]
        lower_label = r"{\an7\pos(104,764)\fs18}Détail · Clic Voisin"
        valid = header + "Dialogue: 0,0:00:00.00,0:00:01.00,NoticeReferenceText,,0,0,0,," + lower_label + "\n"
        with tempfile.TemporaryDirectory() as folder:
            build = Path(folder)
            report = audit_ass(build, valid)
            self.assertTrue(report["all_inside"])
            self.assertEqual(SAFE, (88, 200, 512, 752))
            self.assertTrue(report["notice_graphic_policy"]["standard_states_inside_baseline"])
            self.assertIn("not Instagram/TikTok", report["notice_graphic_policy"]["note"])
            for bad in (valid.replace(",NoticeReferenceText,", ",Text,"),
                        valid.replace("104,764", "104,1100"),
                        valid.replace("Détail · Clic Voisin", "W" * 80)):
                with self.subTest(bad=bad[-100:]), self.assertRaisesRegex(ValueError, "Unsafe"):
                    audit_ass(build, bad)

    def test_picture_credit_is_in_both_publication_receipts(self):
        with tempfile.TemporaryDirectory() as folder:
            build = Path(folder)
            write_publication(build, self.episode)
            for filename in ("publishing_caption.txt", "CREDITS.txt"):
                text = (build / filename).read_text()
                self.assertIn("Annonce : French Compass", text)
                for required in ("Snow Rig", "Rain Rig", "CC BY 4.0"):
                    self.assertIn(required, text)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
    def test_real_encoded_task_card_and_reference_change_on_exact_odd_frames(self):
        import numpy as np
        from PIL import Image, ImageDraw
        with tempfile.TemporaryDirectory() as folder:
            build = Path(folder)
            (build / "frames").mkdir()
            turns = []
            for index, (source, start, stop) in enumerate(((1, 0, 5), (2, 17, 30), (3, 35, 45))):
                turn = {**self.episode["turns"][source], "id": f"t{index}", "text": "Une annonce."}
                if "picture_card_delay_seconds" in turn:
                    turn["picture_card_delay_seconds"] = 4/24
                turns.append({**turn, "start": start/24, "end": stop/24,
                              "start_frame": start, "end_frame": stop,
                              "wav_duration": (stop-start)/24, "duration": (stop-start)/24,
                              "words": [{"word": "Une", "start": .01, "end": .04, "score": .9},
                                        {"word": "annonce.", "start": .06, "end": .09, "score": .9}]})
            episode = {**self.episode, "intro_seconds": 0, "outro_seconds": 0,
                       "subtitle_mode": "legacy", "turns": [
                           {k: v for k, v in t.items() if k not in (
                               "start", "end", "start_frame", "end_frame", "wav_duration", "duration", "words")}
                           for t in turns]}
            timeline = {"language": "fr", "fps": 24, "total_frames": 100, "duration": 100/24, "turns": turns}
            manifest = {"episode": episode, "timeline": timeline,
                        "width": 90, "height": 160, "motion_step": 2}
            for name, data in (("episode.json", episode), ("timeline.json", timeline),
                               ("scene_manifest.json", manifest)):
                atomic_json(build / name, data)
            (build / "studio.blend").write_bytes(b"Explicit synthetic task-picture fixture, not a scene")
            atomic_json(build / "frames_manifest.json", {"scene": manifest, "blend_sha256": scene_hash(build)})
            plate = Image.new("RGB", (720, 1280), "#888888")
            ImageDraw.Draw(plate).rectangle((340, 350, 494, 552), fill="#598a73")
            for frame in range(1, 101, 2):
                plate.resize((90, 160)).save(build / "frames" / f"frame_{frame:04d}.png")
            with wave.open(str(build / "dialogue.wav"), "wb") as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(48000)
                audio.writeframes(b"\x00\x00"*200000)
            mux(build, build / "episode.json")
            report = review_pictures(build, episode, timeline)
            self.assertEqual([w["start_frame"] for w in report["windows"]], [9, 17])
            self.assertEqual([w["end_frame"] for w in report["windows"]], [17, 35])
            self.assertTrue(all(len(w["decoded_checks"]) == 5 for w in report["windows"]))
            self.assertEqual(report["windows"][1]["bounds"], [104, 790, 424, 1006])
            self.assertTrue(json.loads((build / "safe_zone_report.json").read_text())[
                "notice_graphic_policy"]["standard_states_inside_baseline"])
            decoded = build / "dialogue_frame.png"
            from review_social import frame_at
            frame_at(build, "pilot.mp4", 26/24, decoded)
            clean = build / "dialogue_clean.png"
            frame_at(build, "pilot_clean.mp4", 26/24, clean)
            with Image.open(decoded) as actual, Image.open(clean) as reference:
                box = (350, 360, 484, 542)
                error = np.abs(np.asarray(actual.crop(box)).astype(float)
                               - np.asarray(reference.crop(box)).astype(float)).mean()
                self.assertLess(error, 3)

    def test_french_voice_texts_match_the_authoritative_existing_registry(self):
        registry_path = (self.path.parent / self.episode["source"]["voice_registry"]).resolve()
        registry = {entry["voice_id"]: entry for entry in json.loads(registry_path.read_text())["voices"]}
        for voice in self.episode["voices"].values():
            entry = registry[voice["voice_id"]]
            self.assertTrue(entry["availability"])
            self.assertEqual(voice["reference_text"], entry["reference_text"])
            self.assertEqual(Path(voice["audio"]),
                             registry_path.parents[2] / entry["reference_audio"])
            self.assertNotIn("transcript", voice)
        self.assertEqual(len({voice["voice_id"] for voice in self.episode["voices"].values()}), 2)

    def test_a1_requirements_have_real_speaking_turns_and_consistent_facts(self):
        turns = {turn["id"]: turn for turn in self.episode["turns"]}
        for point, ids in self.episode["source"]["coverage"].items():
            with self.subTest(point=point):
                self.assertTrue(ids)
                self.assertTrue(set(ids) <= set(turns))
        for turn_id, words in {
            "03": ("Bonjour Monsieur", "renseigner"),
            "06": ("mardi ou le jeudi", "dix-huit heures", "dix-neuf heures trente", "six semaines"),
            "08": ("gratuit", "s'inscrire"),
            "10": ("six ordinateurs", "à deux"),
            "12": ("messagerie", "formulaires"),
            "14": ("deux cent quatre", "deuxième étage", "ascenseur"),
            "16": ("Saint-Paul", "deux minutes", "quelques places"),
            "17": ("Quand vous dites", "quelques places", "aussi le jeudi"),
            "18": ("deux places le mardi", "jeudi est complet"),
            "19": ("liste d'attente", "mardi"),
            "20": ("si une place se libère",),
            "22": ("même programme",),
            "23": ("rappellerai", "confirmer l'inscription", "Bonne journée"),
        }.items():
            for word in words:
                self.assertIn(word, turns[turn_id]["text"])
        self.assertEqual([t["speaker"] for t in self.episode["turns"][2:]],
                         ["candidate_a", "examiner"] * 11)
        self.assertTrue(all(turn["look_at"] == ("examiner" if turn["speaker"] == "candidate_a"
                                              else "candidate_a") for turn in turns.values()))

    def test_pedagogical_hold_and_card_do_not_change_exam_timing_claims(self):
        episode = self.episode
        timeline = clock(episode, seconds=18)
        check_timeline(episode, timeline)
        start, end = task_window(timeline)
        self.assertEqual(round((start - timeline["turns"][1]["end"]) * 24), 29)
        self.assertEqual(round((end-start) * 24), 192)
        self.assertEqual(episode["outro_seconds"], 6)
        self.assertEqual(episode["takeaway"], [])
        self.assertTrue(all(t["pause_after"] == 1.2 for t in episode["turns"][2:]))
        self.assertIn("pas au temps officiel", episode["publication"]["disclosure"])
        self.assertNotIn("candidates", [camera for _, camera in camera_shots(episode, timeline)])

    def test_french_headers_caption_words_and_cast_are_consistent(self):
        timeline = clock(self.episode, seconds=18)
        pages = caption_pages(self.episode, timeline)
        for turn in timeline["turns"]:
            self.assertEqual(" ".join(page["text"] for page in pages if page["turn_id"] == turn["id"]),
                             turn["text"])
        self.assertEqual([window["section"] for window in section_windows(self.episode, timeline)],
                         [None, "A", None])
        ass = make_ass(self.episode, timeline)
        self.assertIn("Intervenant : Interlocuteur", ass)
        self.assertIn("Lien Amazon dans le profil", ass)
        for stale in ("DEUTSCHKOMPASS", "DTZ", "Es spricht:", "Amazon-Buchlink", "Samir"):
            self.assertNotIn(stale, ass)
        plan = performance_plan(timeline, self.episode)
        self.assertEqual(set(plan["attention"]), set(active_actors(self.episode)))

    def test_inherited_dtz_voice_cannot_leak_into_interview(self):
        data = copy.deepcopy(self.episode)
        data["voices"]["candidate_b"] = copy.deepcopy(data["voices"]["candidate_a"])
        with self.assertRaisesRegex(ValueError, "inactive"):
            validate_template(data)


if __name__ == "__main__":
    unittest.main()
