import copy
import json
from pathlib import Path
import unittest

from align_words import validate_words
from derive_fide_social import overlay, short_cta, short_edit
from long_speaking_preview import caption_words

ROOT = Path(__file__).resolve().parent


class FideSocialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = ROOT / "builds" / "fide_a2_b1_single_book_r1"
        if not (source / "timeline.json").is_file():
            raise unittest.SkipTest("The complete local single-book fide delivery is required.")
        cls.timeline = json.loads((source / "timeline.json").read_text(encoding="utf-8"))
        cls.episode = json.loads((source / "episode.json").read_text(encoding="utf-8"))
        cls.config = json.loads((ROOT / "episodes" / "fide_a2_b1_social_three.json").read_text(encoding="utf-8"))

    def test_all_three_edits_retain_complete_models_and_strict_duration(self):
        original = {t["id"]: t for t in self.timeline["turns"]}
        for clip in self.config["clips"]:
            edited, edits = short_edit(self.timeline, clip["turn_numbers"], self.config["cta_sentence"])
            self.assertLess(edited["total_frames"], 180 * edited["fps"])
            self.assertEqual(0, edits[0]["output_start"])
            self.assertEqual(edited["total_frames"], edits[-1]["output_end"])
            for left, right in zip(edits, edits[1:]):
                self.assertEqual(left["output_end"], right["output_start"])
            for turn in edited["turns"][:-1]:
                source = original[turn["id"]]
                for key in ("text", "display_text", "words", "display_word_groups", "mouth_cues",
                            "wav_duration", "tempo_processing"):
                    self.assertEqual(source[key], turn[key], (clip["id"], turn["id"], key))
                self.assertEqual(source["start_frame"], turn["source_start_frame"])
            self.assertEqual(self.timeline["turns"][0]["text"], edited["turns"][0]["text"])
            self.assertEqual(self.config["cta_sentence"], edited["turns"][-1]["display_text"])
        self.assertEqual(3, len(self.config["clips"]))

    def test_core_a2_functions_and_b1_consent_choice_are_preserved(self):
        clips = [short_edit(self.timeline, c["turn_numbers"], self.config["cta_sentence"])[0]
                 for c in self.config["clips"]]
        a2 = clips[0]["turns"]
        self.assertEqual(3, sum(t["section"] == "a2_conversation" and t["speaker"] == "candidate_a" for t in a2))
        phone = [t["id"] for t in self.timeline["turns"] if t["section"] == "a2_phone"]
        self.assertEqual(phone, [t["id"] for t in a2 if t["section"] == "a2_phone"])
        b1 = clips[1]["turns"]
        sections = [t["section"] for t in b1]
        self.assertLess(sections.index("routing"), sections.index("b1_choice"))
        self.assertLess(sections.index("b1_choice"), sections.index("b1_experience"))
        self.assertTrue(any("Ja, ich möchte gerne B1 versuchen." == t["display_text"] for t in b1))
        models = [t["source_segment"] for t in self.timeline["turns"] if t.get("source_track", "").startswith("fide_b1")]
        actual = [t["source_segment"] for clip in clips for t in clip["turns"]
                  if t.get("source_track", "").startswith("fide_b1")]
        self.assertEqual(models, actual)

    def test_cta_uses_real_word_mapping_at_a_safe_complete_sentence_boundary(self):
        old = copy.deepcopy(self.timeline["turns"][-1])
        turn = short_cta(old, self.config["cta_sentence"], self.timeline["fps"])
        cut = turn["source_clip_start_frame"] / self.timeline["fps"]
        source_words = old["words"][-len(turn["words"]):]
        for source, clipped in zip(source_words, turn["words"]):
            self.assertAlmostEqual(source["start"], clipped["start"] + cut)
            self.assertAlmostEqual(source["end"], clipped["end"] + cut)
            self.assertEqual(source["score"], clipped["score"])
        validate_words(turn["words"], turn["text"], turn["wav_duration"])
        self.assertEqual(self.config["cta_sentence"].split(), [w["word"] for w in caption_words(turn)])
        self.assertNotEqual(old["alignment_key"], turn["alignment_key"])
        self.assertNotIn("raw_audio", turn)
        first = len(old["words"]) - len(turn["words"])
        old["words"][first - 1]["end"] = old["words"][first]["start"] + .01
        with self.assertRaisesRegex(ValueError, "No frame-aligned gap"):
            short_cta(old, self.config["cta_sentence"], self.timeline["fps"])

    def test_rejects_exactly_180_seconds_and_unordered_or_non_sentence_cuts(self):
        clip = self.config["clips"][1]
        edited, _ = short_edit(self.timeline, clip["turn_numbers"], self.config["cta_sentence"])
        changed = copy.deepcopy(self.timeline)
        changed["turns"][1]["start_frame"] += 180 * changed["fps"] - edited["total_frames"]
        with self.assertRaisesRegex(ValueError, "strictly below 180"):
            short_edit(changed, clip["turn_numbers"], self.config["cta_sentence"])
        with self.assertRaisesRegex(ValueError, "ordered"):
            short_edit(self.timeline, [1, 7, 6], self.config["cta_sentence"])
        with self.assertRaisesRegex(ValueError, "complete sentence boundary"):
            short_cta(self.timeline["turns"][-1], "in der Bio.", self.timeline["fps"])

    def test_overlay_keeps_spoken_title_and_one_book_with_numbered_video_label(self):
        clip = self.config["clips"][1]
        timeline, _ = short_edit(self.timeline, clip["turn_numbers"], self.config["cta_sentence"])
        episode = {**self.episode, "output_formats": ["social"], "series_label": clip["label"],
                   "turns": copy.deepcopy(timeline["turns"])}
        for frame in (0, timeline["turns"][-1]["start_frame"]):
            image, check = overlay(episode, episode, timeline, "social", frame)
            self.assertEqual((1080, 1920), image.size)
            self.assertEqual(1, check["cover_count"])
            self.assertEqual(self.episode["promotion"]["book"]["url"], check["book_url"])
            self.assertEqual(clip["label"], " ".join(check["text"][-1]["lines"]))
        self.assertEqual(self.episode["turns"][0]["display_text"], timeline["turns"][0]["display_text"])


if __name__ == "__main__":
    unittest.main()
