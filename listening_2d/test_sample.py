import json
import unittest
from pathlib import Path
import tempfile
from unittest.mock import patch

from compose_sample import compose, instruction_intervals, options_html, title_intervals
from prepare_sample import guided_timeline, mix_events, retime_alignment, reveal_sound, write_wav


class TitleMappingTests(unittest.TestCase):
    def timeline(self):
        tokens = "Ö I F B eins Hören. Unabhängige Prüfungssimulation.".split()
        return {"turns": [{
            "id": "title", "start": 2, "wav_duration": 8, "text": " ".join(tokens),
            "words": [{"word": word, "start": n, "end": n + 0.5, "score": 0.9}
                      for n, word in enumerate(tokens)],
        }]}

    def test_abbreviations_use_full_measured_speech_ranges(self):
        result = title_intervals(self.timeline())
        self.assertEqual((result[0]["label"], result[0]["start"], result[0]["end"]),
                         ("ÖIF", 2, 4.5))
        self.assertEqual((result[1]["label"], result[1]["start"], result[1]["end"]),
                         ("B1", 5, 6.5))

    def test_missing_word_timing_is_not_estimated(self):
        timeline = self.timeline()
        del timeline["turns"][0]["words"][2]["end"]
        with self.assertRaisesRegex(ValueError, "interval"):
            title_intervals(timeline)


class InstructionHighlightTests(unittest.TestCase):
    def timeline(self):
        return {"turns": [{
            "id": "instruction", "start": 12.5, "wav_duration": 2,
            "text": "Hören Sie.",
            "words": [{"word": "Hören", "start": 0.17, "end": 0.64, "score": 0.9},
                      {"word": "Sie.", "start": 0.79, "end": 1.71, "score": 0.9}],
        }]}

    def test_instruction_uses_actual_uneven_word_intervals(self):
        words = instruction_intervals(self.timeline(), "Hören Sie.")
        self.assertAlmostEqual(words[0]["start"], 12.67)
        self.assertAlmostEqual(words[1]["end"], 14.21)

    def test_changed_instruction_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "differs"):
            instruction_intervals(self.timeline(), "Lesen Sie.")

    def test_missing_instruction_alignment_is_rejected(self):
        timeline = self.timeline()
        del timeline["turns"][0]["words"][1]["start"]
        with self.assertRaisesRegex(ValueError, "interval"):
            instruction_intervals(timeline, "Hören Sie.")


class AnswerRevealTests(unittest.TestCase):
    def test_correct_option_is_hidden_until_reveal_and_uses_the_key(self):
        question = {"options": {"a": "Erster Weg", "b": "Zweiter Weg", "c": "Dritter Weg"},
                    "answer": "c"}
        hidden = options_html(question)
        self.assertNotIn('option correct', hidden)
        self.assertNotIn('Richtige Antwort', hidden)
        visible = options_html(question, reveal=True)
        self.assertEqual(visible.count('option correct'), 1)
        self.assertIn('class="option correct"><span class="letter">c</span>', visible)
        self.assertIn('Richtige Antwort: c', visible)

    def timeline(self):
        return {"fps": 24, "total_frames": 360, "duration": 15,
                "events": [
                    {"id": "task1", "kind": "speech", "card": "task1", "duration": 1,
                     "start_frame": 0, "end_frame": 24, "start": 0, "end": 1},
                    {"id": "task1_answer", "kind": "silence", "card": "task1", "duration": 12,
                     "start_frame": 24, "end_frame": 312, "start": 1, "end": 13},
                    {"id": "chime_back", "kind": "chime", "card": "end", "duration": 1,
                     "start_frame": 312, "end_frame": 336, "start": 13, "end": 14},
                    {"id": "cta", "kind": "speech", "card": "cta", "duration": 1,
                     "start_frame": 336, "end_frame": 360, "start": 14, "end": 15}],
                "turns": [{"id": "task1", "start": 0, "end": 1, "words": []},
                          {"id": "cta", "start": 14, "end": 15,
                           "words": [{"start": 0.2, "end": 0.7}]}]}

    def test_reveal_preserves_pause_and_shifts_later_speech_not_word_times(self):
        source = self.timeline()
        result = guided_timeline(source)
        self.assertEqual(result["events"][1], source["events"][1])
        self.assertEqual([e["id"] for e in result["events"]],
                         ["task1", "task1_answer", "task1_reveal", "chime_back", "cta"])
        self.assertEqual((result["events"][2]["start"], result["events"][2]["end"]), (13, 16))
        self.assertEqual(result["turns"][1]["start"], 17)
        self.assertEqual(result["turns"][1]["words"], source["turns"][1]["words"])
        self.assertEqual(source["total_frames"], 360)
        self.assertEqual(result["total_frames"], 432)

    def test_invalid_or_duplicate_reveals_are_rejected(self):
        for seconds in (0, -1, 0.01, float("inf")):
            with self.subTest(seconds=seconds), self.assertRaises(ValueError):
                guided_timeline(self.timeline(), seconds)
        with self.assertRaisesRegex(ValueError, "already"):
            guided_timeline(guided_timeline(self.timeline()))

    def test_alignment_receipt_uses_new_turn_offsets_but_keeps_local_intervals(self):
        alignment = {"turns": [{"id": "cta", "start": 14,
                               "words": [{"start": 0.2, "end": 0.7}]}]}
        result = retime_alignment(alignment, guided_timeline(self.timeline()))
        self.assertEqual(result["turns"][0]["start"], 17)
        self.assertEqual(result["turns"][0]["words"], alignment["turns"][0]["words"])
        self.assertEqual(alignment["turns"][0]["start"], 14)

    def test_remove_sound_begins_at_reveal_without_changing_pause_or_reveal(self):
        timeline = {"events": [
            {"id": "task1_answer", "kind": "silence", "start_frame": 0, "end_frame": 288},
            {"id": "task1_reveal", "kind": "reveal", "start_frame": 288, "end_frame": 360}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "chime_remove.wav"
            sound = b"\x04\x00" * 12000
            write_wav(path, sound)
            result = reveal_sound(timeline, {"audio": str(path), "sha256": "test", "frames": 12000})
            mixed = mix_events(result["events"])
        boundary = 288 * 4000
        self.assertFalse(any(mixed[:boundary]))
        self.assertEqual(mixed[boundary:boundary + len(sound)], sound)
        self.assertFalse(any(mixed[boundary + len(sound):]))
        self.assertEqual(len(mixed), 360 * 4000)
        self.assertEqual(result["events"][1]["start_frame"], 288)
        self.assertEqual(result["events"][1]["end_frame"], 360)
        self.assertNotIn("audio", timeline["events"][1])

    def test_oversized_remove_tail_is_not_cut_or_allowed_into_next_cue(self):
        timeline = {"events": [{"kind": "reveal", "start_frame": 0, "end_frame": 72}]}
        with self.assertRaisesRegex(ValueError, "full tail"):
            reveal_sound(timeline, {"frames": 144001})


class PresentationTests(unittest.TestCase):
    def test_all_slides_omit_guided_taglines_and_use_distinct_phase_labels(self):
        cards = [("title", "Titel"), ("instruction", "Anleitung"), ("example", "Beispiel"),
                 ("task1", "Lesen"), ("cta", "Mehr üben")]
        timeline = {"duration": 5, "practice_mode": "guided", "events": [
            {"id": card, "card": card, "phase": phase, "kind": "speech",
             "start": index, "duration": 1} for index, (card, phase) in enumerate(cards)]}
        question = {"question": "Welche Antwort passt?", "options": {"a": "Links", "b": "Rechts"},
                    "answer": "b"}
        content = {"episode": {"sections": [{"example": question, "tasks": [question]}],
                              "promotion": {"cover_source": "book.jpg", "youtube_label": "Amazon",
                                            "social_label": "Amazon"}},
                   "instructions": {"sections": [{"instruction": "Hören Sie."}]}}
        words = [{"index": i, "label": label, "start": i * 0.1, "end": (i + 1) * 0.1}
                 for i, label in enumerate(["ÖIF", "B1", "Hören", "Unabhängige", "Prüfungssimulation"])]
        with tempfile.TemporaryDirectory() as directory:
            build = Path(directory)
            (build / "timeline.json").write_text(json.dumps(timeline), encoding="utf-8")
            (build / "sample_content.json").write_text(json.dumps(content), encoding="utf-8")
            with patch("compose_sample.shutil.copyfile"), patch("compose_sample.sha256_file", return_value="test"), \
                    patch("compose_sample.title_intervals", return_value=words), \
                    patch("compose_sample.instruction_intervals", return_value=[]):
                compose(build)
            for layout in ("landscape", "portrait"):
                document = (build / layout / "index.html").read_text(encoding="utf-8")
                self.assertNotIn("Geführte Hörübung", document)
                self.assertNotIn("Lösungen nach jeder Aufgabe", document)
                self.assertNotIn("von Deutsch Kompass", document)
                self.assertIn('id="title-word-0">ÖIF</span>', document)
                self.assertIn("VORSCHAU", document)
                self.assertEqual(document.count('class="phase-label"'), len(cards))
                for _, label in cards:
                    self.assertIn(f'class="phase-label">{label}</span>', document)


if __name__ == "__main__":
    unittest.main()
