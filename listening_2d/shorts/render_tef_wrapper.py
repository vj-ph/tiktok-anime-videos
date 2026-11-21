"""Render a checked wrapper as native PNG frames when ranged AAC chunking fails."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

from listening_2d.shorts.derive_tef_social import validate_short
from listening_2d.preparation.prepare_tef import FPS, ROOT, atomic_json, read, sha256_file, verify_files
from listening_2d.rendering.deliver_tef import run


def render_wrapper(build, kind):
    validate_short(build)
    checks = read(build / "checks_portrait.json")
    verify_files({str(build / "portrait/index.html"): checks["html_sha256"],
                  str(build / "composition_receipt.json"): checks["composition_sha256"]})
    for name, info in read(build / "composition_receipt.json")["layouts"]["portrait"]["sources"].items():
        verify_files({str(build / "portrait/assets" / name): info["sha256"]})
    if not read(build / "visual_review.json").get("portrait", {}).get("contact_sheets_inspected"):
        raise ValueError("Inspect native frames before rendering.")
    timeline, edit = read(build / "timeline.json"), read(build / "edit_decisions.json")
    first, last = ((0, edit["output_start_frame"]) if kind == "opening"
                   else (edit["output_end_frame"], timeline["total_frames"]))
    target = build / f"{kind}.mp4"
    if target.exists():
        raise ValueError("Preserve the existing wrapper rather than overwrite it.")
    times = [frame / FPS for frame in range(first, last)]
    snapshots = build / f"{kind}_native_frames"
    command = [sys.executable, ROOT / "hyperframes_local.py", "snapshot", build / "portrait",
               "--at", ",".join(map(str, times)), "--no-end", "--no-browser-gpu",
               "--output", snapshots, "--json"]
    log = run(command, build / f"{kind}_native_frames.log")
    text = log.read_text(encoding="utf-8")
    result = json.loads(text[text.index('\n{\n  "ok":') + 1:])
    if not result["ok"] or len(result["frames"]) != len(times):
        raise ValueError("The wrapper is missing native frames.")
    sequence = build / f"{kind}_sequence"
    sequence.mkdir(exist_ok=True)
    frames = []
    for index, (at, frame) in enumerate(zip(times, sorted(result["frames"], key=lambda f: f["time"]))):
        if abs(frame["time"] - at) > .00051:
            raise ValueError("The wrapper snapshot clock changed.")
        path = Path(frame["path"])
        shutil.copyfile(path, sequence / f"frame-{index:04d}.png")
        frames.append({"source_frame": first + index, "file": str(path),
                       "time": at, "sha256": sha256_file(path)})
    encode = ["ffmpeg", "-nostdin", "-v", "error", "-framerate", "24",
              "-i", sequence / "frame-%04d.png", "-frames:v", str(last - first),
              "-vf", "scale=in_range=pc:out_range=tv:out_color_matrix=bt709,format=yuv420p",
              "-an", "-c:v", "libx264", "-threads", "2", "-preset", "fast", "-crf", "16",
              "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
              "-color_range", "tv", "-movflags", "+faststart", target]
    run(encode, build / f"{kind}_video_only.log")
    stream = json.loads(subprocess.check_output(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_streams", "-of", "json", str(target)],
        text=True))["streams"][0]
    if (int(stream["nb_frames"]) != last - first
            or (stream["width"], stream["height"], stream["r_frame_rate"], stream["color_space"])
            != (1080, 1920, "24/1", "bt709")):
        raise ValueError("The video-only wrapper lost native frames or color metadata.")
    archive = build / "wrapper_sources"
    archive.mkdir(exist_ok=True)
    shutil.copyfile(Path(__file__), archive / Path(__file__).name)
    atomic_json(build / f"{kind}_video_only_provenance.json", {
        "method": "Checked original HyperFrames composition, one native PNG per exact output frame; video-only encode",
        "reason": "HyperFrames 0.9.2 ranged AAC packet count error; authoritative audio is muxed later from dialogue.wav",
        "source_html_sha256": checks["html_sha256"], "renderer_sha256": sha256_file(ROOT / "hyperframes_local.py"),
        "generator_sha256": sha256_file(Path(__file__)), "first_source_frame": first, "last_source_frame_exclusive": last,
        "frames": frames, "snapshot_command": list(map(str, command)), "encode_command": list(map(str, encode)),
        "video_sha256": sha256_file(target), "authoritative_audio_sha256": sha256_file(build / "dialogue.wav")})
    print(f"Native video-only {kind}: {last - first} exact frames, ready for the lossless-audio mux.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", required=True, type=Path)
    parser.add_argument("--kind", choices=("opening", "closing"), default="closing")
    args = parser.parse_args()
    render_wrapper(args.build.resolve(), args.kind)
