import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import wave

from PIL import ImageChops

from fide_speaking import compose_turn
from revise_fide_book import join_audio, load_config, overlay, replace_cta, revised_episode

ROOT = Path(__file__).resolve().parent


class SingleBookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = ROOT / "builds" / "fide_a2_b1_trimmed_08_production_r1" / "episode.json"
        if not source.exists():
            raise unittest.SkipTest("The local completed fide production is required for layout fixtures.")
        cls.original = json.loads(source.read_text(encoding="utf-8"))
        cls.config = load_config(ROOT / "episodes" / "fide_a2_b1_single_book.json")

    def test_only_promotion_and_final_cta_change(self):
        original = copy.deepcopy(self.original)
        episode = revised_episode(original, self.config)
        self.assertEqual(self.original, original)
        self.assertEqual(original["turns"][:-1], episode["turns"][:-1])
        self.assertEqual(original["voices"], episode["voices"])
        self.assertEqual(original["render"], episode["render"])
        self.assertEqual({"book", "pointing_emoji"}, set(episode["promotion"]))
        self.assertIn("unserem", episode["turns"][-1]["text"])
        self.assertNotIn("unseren", episode["turns"][-1]["text"])
        self.assertIn("Hören", episode["turns"][-1]["display_text"])

    def test_every_level_and_final_cta_show_exactly_one_book(self):
        episode = revised_episode(self.original, self.config)
        for section in ("opening", "a2_phone", "b1_experience", "closing", "cta"):
            turn = next(t for t in episode["turns"] if t["section"] == section)
            for mode in ("youtube", "social"):
                with patch("revise_fide_book.display_state", return_value=(turn, 0, 10, None)):
                    image, check = overlay(episode, episode, {}, mode, 0)
                self.assertEqual(self.config["book"]["url"], check["book_url"])
                self.assertEqual(1, check["cover_count"])
                self.assertEqual((1920, 1080) if mode == "youtube" else (1080, 1920), image.size)
                text = " ".join(line for record in check["text"] for line in record["lines"])
                self.assertNotIn("fide-Büchern", text)
                self.assertNotIn("VORSCHAU", text)
                if section == "cta":
                    self.assertIn("Sprechen + Schreiben + Hören", text)
                    self.assertIn("Komplettband", text)
                else:
                    old, _ = compose_turn(self.original, turn, mode, 0, 10)
                    scene = (72, 388, 908, 868) if mode == "social" else (64, 210, 1280, 790)
                    self.assertIsNone(ImageChops.difference(image.crop(scene), old.crop(scene)).getbbox())

    def test_rejects_bad_cover_hash_and_nonfinal_cta(self):
        config = json.loads((ROOT / "episodes" / "fide_a2_b1_single_book.json").read_text(encoding="utf-8"))
        config["book"]["cover_sha256"] = "0" * 64
        with patch("revise_fide_book.read", return_value=config):
            with self.assertRaisesRegex(ValueError, "cover changed"):
                load_config(ROOT / "episodes" / "fide_a2_b1_single_book.json")
        original = copy.deepcopy(self.original)
        original["turns"][-1]["kind"] = "model"
        with self.assertRaisesRegex(ValueError, "final static CTA"):
            revised_episode(original, self.config)


class ExactCtaSpliceTests(unittest.TestCase):
    def test_changes_only_final_turn_and_rebases_its_measured_words(self):
        old = {"fps": 24, "duration": 8, "total_frames": 192, "word_alignment": {"model": "original"},
               "turns": [{"id": "exam", "start_frame": 0, "end_frame": 120, "text": "Unchanged."},
                         {"id": "cta", "kind": "cta", "start_frame": 120, "end_frame": 168,
                          "start": 5, "end": 7}]}
        words = [{"word": "Buch.", "start": .2, "end": .8, "score": .92}]
        cta = {"fps": 24, "total_frames": 96, "word_alignment": {"model": "new CTA"},
               "turns": [{"id": "cta", "kind": "cta", "start_frame": 0, "end_frame": 24,
                          "start": 0, "end": 1, "words": words}]}
        result = replace_cta(old, cta)
        self.assertEqual(old["turns"][:-1], result["turns"][:-1])
        self.assertEqual(216, result["total_frames"])
        self.assertEqual(9, result["duration"])
        self.assertEqual(5, result["turns"][-1]["start"])
        self.assertEqual(6, result["turns"][-1]["end"])
        self.assertEqual(words, result["turns"][-1]["words"])
        self.assertEqual(0, cta["turns"][0]["start_frame"])
        self.assertIn("final_cta_revision", result["word_alignment"])
        cta["turns"][0]["id"] = "another"
        with self.assertRaisesRegex(ValueError, "final CTA"):
            replace_cta(old, cta)

    def test_pcm_prefix_and_measured_cta_are_byte_identical(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)

            def save(name, pcm):
                path = root / name
                with wave.open(str(path), "wb") as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(48000)
                    wav.writeframes(pcm)
                return path

            original = b"\x01\x00" * 6000 + b"\x02\x00" * 6000
            replacement = b"\x03\x00" * 8000
            source, cta = save("old.wav", original), save("new.wav", replacement)
            output = root / "joined.wav"
            receipt = join_audio(source, cta, output, 3, 24)
            with wave.open(str(output), "rb") as wav:
                self.assertEqual(original[:12000] + replacement, wav.readframes(wav.getnframes()))
            self.assertEqual(6000, receipt["unchanged_prefix_samples"])
            self.assertTrue(receipt["prefix_pcm_byte_identical"])
            with self.assertRaisesRegex(ValueError, "before the CTA boundary"):
                join_audio(source, cta, output, 99, 24)


if __name__ == "__main__":
    unittest.main()
