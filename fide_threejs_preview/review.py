"""Verify encoded previews, make decoded contact sheets, and preserve source hashes."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import wave

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
REPO = HERE.parent


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def pcm(path):
    with wave.open(str(path), "rb") as stream:
        assert stream.getframerate() == 48000 and stream.getsampwidth() == 2
        return np.frombuffer(stream.readframes(stream.getnframes()), dtype="<i2").astype(float)


def review(build):
    timeline = read(build / "timeline.json")
    receipt = read(build / "render_receipt.json")
    assert not receipt["fixture"]
    baseline = read(build / "existing_files.json")
    for name, expected in baseline.items():
        assert digest(REPO / name) == expected, f"Existing file changed: {name}"
    for name, expected in read(build / "voice_inputs.json").items():
        assert digest(name) == expected, f"Reference voice changed: {name}"
    audio_receipt = read(build / "audio_receipt.json")
    for name, expected in {**audio_receipt["files"], **audio_receipt["inputs"]}.items():
        assert digest(name) == expected, f"Prepared input changed: {name}"
    original = pcm(build / "dialogue.wav")
    assert len(original) == timeline["total_frames"] * 2000
    results = []
    for format in receipt["formats"]:
        name = format["name"]
        video = build / f"{name}.mp4"
        probe = json.loads(subprocess.check_output(
            ["ffprobe", "-v", "error", "-count_frames", "-show_streams", "-show_format", "-of", "json", str(video)]))
        stream = next(s for s in probe["streams"] if s["codec_type"] == "video")
        assert int(stream["nb_read_frames"]) == timeline["total_frames"]
        assert int(stream["width"]) == format["width"] and int(stream["height"]) == format["height"]
        assert stream["r_frame_rate"] == "24/1"
        assert abs(float(probe["format"]["duration"]) - timeline["duration"]) < 0.05
        assert float(probe["format"]["duration"]) < 90
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(video), "-f", "null", "-"], check=True)
        decoded = np.frombuffer(subprocess.check_output(
            ["ffmpeg", "-nostdin", "-v", "error", "-i", str(video), "-vn", "-ar", "48000", "-ac", "1",
             "-c:a", "pcm_s16le", "-f", "s16le", "-"]), dtype="<i2").astype(float)
        assert len(decoded) >= len(original)
        speech = []
        silences = []
        for i, turn in enumerate(timeline["turns"]):
            start = turn["start_frame"] * 2000
            end = start + turn["audio_samples"]
            expected = pcm(turn["audio"])
            assert np.array_equal(original[start:end], expected)
            correlation = float(np.corrcoef(expected, decoded[start:end])[0, 1])
            assert correlation > 0.985, f"{name}/{turn['id']}: audio mismatch {correlation}"
            speech.append({"id": turn["id"], "correlation": correlation, "samples": len(expected)})
            next_start = timeline["turns"][i + 1]["start_frame"] * 2000 if i + 1 < len(timeline["turns"]) else len(original)
            assert np.max(np.abs(original[end:next_start]), initial=0) == 0
            # AAC may ring at boundaries; inspect only the interior of each authored pause.
            interior = decoded[end + 4096:next_start - 4096]
            peak = float(np.max(np.abs(interior), initial=0))
            assert peak <= 16, f"{name}: unexpected sound in {turn['id']} pause: {peak}"
            silences.append({"after": turn["id"], "interior_peak_pcm16": peak})
        folder = build / f"decoded_{name}"
        folder.mkdir(exist_ok=True)
        expression = "+".join(f"eq(n\\,{frame})" for frame in format["reference_frames"])
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(video),
                        "-vf", f"select={expression}", "-fps_mode", "vfr", str(folder / "%02d.png")], check=True)
        comparisons, panels = [], []
        for i, frame in enumerate(format["reference_frames"], 1):
            image = Image.open(folder / f"{i:02d}.png").convert("RGB")
            native = Image.open(build / f"reference_{name}" / f"{frame:06d}.png").convert("RGB")
            error = float(np.mean(np.abs(np.asarray(image, dtype=float) - np.asarray(native, dtype=float))))
            assert error < 8, f"{name}/{frame}: encoded frame differs: {error}"
            comparisons.append({"frame": frame, "mean_rgb_error": error})
            image.thumbnail((360, 640) if name == "social" else (480, 270))
            panel = Image.new("RGB", (image.width, image.height + 28), "#f3f5ef")
            panel.paste(image, (0, 0))
            ImageDraw.Draw(panel).text((8, image.height + 7), f"{name} | frame {frame} | {frame / 24:.3f}s", fill="#203d35")
            panels.append(panel)
        cols = 4 if name == "social" else 3
        rows = (len(panels) + cols - 1) // cols
        pw, ph = panels[0].size
        sheet = Image.new("RGB", (cols * pw, rows * ph), "#d8e1d6")
        for i, panel in enumerate(panels):
            sheet.paste(panel, ((i % cols) * pw, (i // cols) * ph))
        sheet.save(build / f"contact_{name}.jpg", quality=94)
        results.append({"name": name, "frames": int(stream["nb_read_frames"]),
                        "duration": float(probe["format"]["duration"]), "speech": speech,
                        "silences": silences, "decoded_frame_comparisons": comparisons})
    audit = {"status": "automated_checks_passed", "existing_files_unchanged": len(baseline),
             "voice_family": "user-provided Swiss Standard German", "formats": results,
             "review_limitations": ["Independent ASR is not human listening.",
                                    "Technical A2 excerpt, not a full fide exam simulation."]}
    (build / "final_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest = {}
    for path in sorted(HERE.rglob("*")):
        if not path.is_file() or "node_modules" in path.parts or "__pycache__" in path.parts:
            continue
        if "builds" in path.parts and not path.is_relative_to(build):
            continue
        if path.name != "delivery_manifest.json":
            manifest[str(path.relative_to(HERE))] = digest(path)
    (build / "delivery_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"existing_files_unchanged": len(baseline), "manifest_files": len(manifest),
                      "formats": [{"name": r["name"], "duration": r["duration"],
                                   "minimum_audio_correlation": min(t["correlation"] for t in r["speech"])}
                                  for r in results]}, indent=2))


if __name__ == "__main__":
    review(HERE / "builds" / (sys.argv[1] if len(sys.argv) > 1 else "preview_swiss_r1"))
