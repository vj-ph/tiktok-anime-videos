import copy
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import wave

from deliver_b2_display import active_words, patch_plan, reading_mapping, render_command, revised_document
from prepare_b2_display import READING_TEXT


class B2DisplayTests(unittest.TestCase):
    def mapping(self):
        return [dict(index=i, label=word, start=3.0 + i * 0.3, end=3.25 + i * 0.3,
                     selector=f"#reading-word-{i}") for i, word in enumerate(READING_TEXT.split())]

    def test_instruction_replaces_only_its_board_and_registers_measured_highlights(self):
        source = ('<style></style><section id="scene-0" class="clip scene statements" '
                  'data-start="3" data-duration="4"><div data-question="41">question</div></section>'
                  '<section id="scene-1" class="clip scene statements" data-start="7" data-duration="15">'
                  '<div data-question="41">question</div></section><script>const x = [].concat([].map(w=>w));</script>')
        scenes = [dict(id="reading_instruction"), dict(id="reading_pause")]
        revised = revised_document(source, scenes, self.mapping())
        first, second = revised.split("</section>")[:2]
        self.assertIn('class="clip scene reading-instruction"', first)
        self.assertNotIn("data-question", first)
        self.assertIn('data-start="3" data-duration="4"', first)
        self.assertIn('data-question="41"', second)
        self.assertIn('data-start="7" data-duration="15"', second)
        self.assertEqual(revised.count('class="instruction-word"'), len(READING_TEXT.split()))
        self.assertIn('"selector": "#reading-word-3"', revised)

    def test_patch_states_cover_complete_cue_without_moving_reveals(self):
        scenes = [
            dict(id="reading_instruction", kind="speech", card="question", start_frame=72, end_frame=168),
            dict(id="answer", kind="reveal", card="question", start_frame=528, end_frame=600),
        ]
        patches, changed = patch_plan(scenes, self.mapping())
        reading = [p for p in patches if p.get("reading")]
        self.assertEqual([f for p in reading for f in range(p["start_frame"], p["end_frame"])],
                         list(range(72, 168)))
        for patch in reading:
            for frame in range(patch["start_frame"], patch["end_frame"]):
                self.assertEqual(patch["active_words"], list(active_words(self.mapping(), frame)))
        self.assertEqual((patches[-1]["start_frame"], patches[-1]["end_frame"]), (528, 600))
        self.assertEqual((changed[0]["start_frame"], changed[0]["end_frame"]), (72, 168))

    def test_reading_mapping_rejects_changed_text_or_audio_binding(self):
        alignment = dict(text=READING_TEXT, audio_sha256="same",
                         words=[dict(word=w, start=i * .3, end=i * .3 + .2)
                                for i, w in enumerate(READING_TEXT.split())])
        timeline = dict(events=[dict(id="reading_instruction", text=READING_TEXT, sha256="same", start=3)])
        self.assertEqual(reading_mapping(timeline, alignment)[0]["start"], 3)
        changed = copy.deepcopy(alignment)
        changed["words"][3]["word"] = "dreißig"
        with self.assertRaises(AssertionError):
            reading_mapping(timeline, changed)
        changed = copy.deepcopy(timeline)
        changed["events"][0]["sha256"] = "different"
        with self.assertRaises(AssertionError):
            reading_mapping(changed, alignment)

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg unavailable")
    def test_native_replacements_begin_and_end_on_exact_video_frames(self):
        from PIL import Image, ImageDraw
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, audio, patch, output = [root / n for n in ("source.mp4", "audio.wav", "patch.png", "out.mp4")]
            subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i",
                            "color=black:s=64x64:r=24", "-frames:v", "10",
                            "-c:v", "libx264", str(source)], check=True)
            with wave.open(str(audio), "wb") as stream:
                stream.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
                stream.writeframes(bytes(10 * 4000))
            image = Image.new("RGB", (64, 64), "black")
            ImageDraw.Draw(image).rectangle((15, 15, 47, 47), fill="white")
            image.save(patch)
            subprocess.run(render_command(source, audio, [
                dict(image=str(patch), start_frame=2, end_frame=5, crop=[15, 15, 33, 33])],
                10, output), check=True)
            decoded = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(output),
                                      "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                                     check=True, capture_output=True).stdout
            self.assertEqual(len(decoded), 10 * 64 * 64 * 3)
            for frame in range(10):
                center = decoded[frame * 64 * 64 * 3 + (32 * 64 + 32) * 3]
                self.assertGreater(center, 230) if 2 <= frame < 5 else self.assertLess(center, 20)
                self.assertLess(decoded[frame * 64 * 64 * 3], 20)
                if 2 <= frame < 5:
                    self.assertLess(decoded[frame * 64 * 64 * 3 + (32 * 64 + 14) * 3], 30)
                    self.assertGreater(decoded[frame * 64 * 64 * 3 + (32 * 64 + 15) * 3], 230)


if __name__ == "__main__":
    unittest.main()
