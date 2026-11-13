"""Compose, natively patch and verify the B2 instruction/color revision."""

import argparse
import html
import json
import math
from pathlib import Path
import re
import subprocess
import sys

from deliver_b2_r3 import run
from prepare_b2 import read
from prepare_b2_display import READING_TEXT
from prepare_sample import ROOT, atomic_json, sha256_file
from review_full_frames import sheets
from validate_b2_r3 import verify_files
from validate_full import encoded_events

COLORS = """
    [data-answer$=":richtig"] { color:#215640; background:#e0f1e7; border-color:#44806d; }
    [data-answer$=":falsch"] { color:#8c2635; background:#fde9eb; border-color:#b24a57; }
    html[data-resolution="portrait"] .reading-instruction .instruction {
      font-size:52px; line-height:1.45; }
"""


def digest(path):
    return sha256_file(Path(path))


def verify_inputs(build):
    verify_files(read(build / "input_pin.json")["files"])
    for layer in read(build / "source_preservation.json")["layers"]:
        verify_files(layer["files"])
        verify_files(layer["code_inputs"])
        verify_files(layer["input_files"])
    aligned = read(build / "reading_alignment.json")
    assert digest(aligned["audio"]) == aligned["audio_sha256"]
    assert aligned["text"] == READING_TEXT


def reading_mapping(timeline, alignment):
    assert [w["word"] for w in alignment["words"]] == READING_TEXT.split()
    cue = next(e for e in timeline["events"] if e["id"] == "reading_instruction")
    assert cue["text"] == alignment["text"] and cue["sha256"] == alignment["audio_sha256"]
    return [dict(index=i, label=w["word"], start=cue["start"] + w["start"],
                 end=cue["start"] + w["end"], selector=f"#reading-word-{i}")
            for i, w in enumerate(alignment["words"])]


def revised_document(source, scenes, mapping):
    assert source.count("</style>") == 1
    result = source.replace("</style>", COLORS + "\n</style>")
    if mapping:
        index = next(i for i, event in enumerate(scenes) if event["id"] == "reading_instruction")
        pattern = rf'<section id="scene-{index}"[^>]*>.*?</section>'
        match = re.search(pattern, result, re.S)
        assert match
        opening = match.group().split(">", 1)[0] + ">"
        opening = re.sub(r'class="[^"]+"', 'class="clip scene reading-instruction"', opening)
        spans = " ".join(
            f'<span class="instruction-word" id="reading-word-{w["index"]}">'
            f'{html.escape(w["label"])}</span>' for w in mapping)
        replacement = (opening + '<div class="eyebrow">Anleitung</div><h2>Aufgaben lesen</h2>'
                       f'<p class="instruction">{spans}</p>'
                       '<div class="phase"><span class="phase-label">Anleitung</span></div></section>')
        result = result[:match.start()] + replacement + result[match.end():]
        assert result.count(".concat([].map") == 1
        result = result.replace(".concat([].map", ".concat(" + json.dumps(mapping, ensure_ascii=False) + ".map")
    return result


def active_words(mapping, frame):
    seconds = frame / 24
    return tuple(w["index"] for w in mapping if w["start"] <= seconds < w["end"])


def patch_plan(scenes, mapping):
    result, changed = [], []
    for event in scenes:
        if event["kind"] == "reveal" or event["card"] == "summary":
            result.append(dict(start_frame=event["start_frame"], end_frame=event["end_frame"],
                               label=event["id"], active_words=[],
                               crop_selector=".answer-board" if event["card"] == "summary" else None))
            changed.append(dict(start_frame=event["start_frame"], end_frame=event["end_frame"],
                                label=event["id"]))
        if event["id"] == "reading_instruction" and mapping:
            changed.append(dict(start_frame=event["start_frame"], end_frame=event["end_frame"],
                                label="separate reading instruction"))
            for frame in range(event["start_frame"], event["end_frame"]):
                active = list(active_words(mapping, frame))
                if result and result[-1].get("reading") and result[-1]["active_words"] == active:
                    result[-1]["end_frame"] = frame + 1
                else:
                    result.append(dict(start_frame=frame, end_frame=frame + 1, reading=True,
                                       label="reading " + (" / ".join(mapping[i]["label"] for i in active)
                                                          if active else "word gap"),
                                       active_words=active))
    for patch in result:
        patch["sample_frame"] = (patch["start_frame"] + patch["end_frame"] - 1) // 2
    return sorted(result, key=lambda p: p["start_frame"]), changed


def job_dir(build, job):
    return build / "reviews" / job["name"]


def compose(build):
    if (build / "delivery_manifest.json").exists():
        raise ValueError("Preserve frozen deliveries; choose a fresh revision.")
    verify_inputs(build)
    alignment = read(build / "reading_alignment.json")
    for job in read(build / "jobs.json").values():
        clip = build / job["clip"]
        timeline = read(clip / "timeline.json")
        mapping = reading_mapping(timeline, alignment) if job["name"] in ("teil_1", "teil_2") else []
        source = Path(job["source_html"]).read_text(encoding="utf-8")
        document = revised_document(source, job["scenes"], mapping)
        (clip / job["layout"] / "index.html").write_text(document, encoding="utf-8")
        patches, changed = patch_plan(job["scenes"], mapping)
        directory = job_dir(build, job)
        directory.mkdir(parents=True, exist_ok=True)
        source_review = read(Path(job["source"]) / "browser_visual_review.json")
        frames = {p["frame"]: {**p, "edited_review": False} for p in source_review["frames"]}
        def add(frame, label):
            frame = max(0, min(timeline["total_frames"] - 1, frame))
            item = frames.setdefault(frame, dict(frame=frame, seconds=frame / 24, labels=[]))
            item["edited_review"] = True
            item["labels"].insert(0, label)
        for event in changed:
            for frame, label in ((event["start_frame"] - 1, "before"),
                                 (event["start_frame"], "first"),
                                 (event["end_frame"] - 1, "last"), (event["end_frame"], "after")):
                add(frame, event["label"] + " " + label)
        for patch in patches:
            add(patch["sample_frame"], patch["label"])
        for item in frames.values():
            seconds = item["frame"] / 24
            stamp = math.ceil(seconds * 1000 - 1e-7) / 1000
            if mapping:
                cue = next(e for e in job["scenes"] if e["id"] == "reading_instruction")
                if cue["start_frame"] <= item["frame"] < cue["end_frame"]:
                    expected = active_words(mapping, item["frame"])
                    candidates = (stamp, math.floor(seconds * 1000 + 1e-7) / 1000)
                    stamp = next(t for t in candidates if active_words(mapping, t * 24) == expected
                                 and cue["start"] <= t < cue["end"])
            item["snapshot_seconds"] = stamp
            item["stamp"] = f'{stamp:.3f}'.rstrip("0").rstrip(".")
        plan = dict(job=job, frames=sorted(frames.values(), key=lambda p: p["frame"]),
                    patches=patches, changed_ranges=changed, reading_words=mapping,
                    timeline_sha256=digest(clip / "timeline.json"),
                    html_sha256=digest(clip / job["layout"] / "index.html"),
                    generator_sha256=digest(Path(__file__)))
        atomic_json(directory / "plan.json", plan)
        print(f'{job["name"]}: {len(patches)} native replacement states; clock unchanged.', flush=True)


def validate_source(build, job):
    clip, source = build / job["clip"], Path(job["source"])
    timeline = read(clip / "timeline.json")
    assert timeline == read(source / "timeline.json")
    assert digest(clip / "dialogue.wav") == digest(source / "dialogue.wav")
    for name in ("sample_content.json", "audio_manifest.json"):
        assert read(clip / name) == read(source / name)
    plan = read(job_dir(build, job) / "plan.json")
    mapping = reading_mapping(timeline, read(build / "reading_alignment.json")) if job["name"] in ("teil_1", "teil_2") else []
    expected = revised_document(Path(job["source_html"]).read_text(encoding="utf-8"), job["scenes"], mapping)
    document = clip / job["layout"] / "index.html"
    assert document.read_text(encoding="utf-8") == expected
    assert plan["html_sha256"] == digest(document) and plan["generator_sha256"] == digest(Path(__file__))
    assert plan["timeline_sha256"] == digest(clip / "timeline.json")
    assert (plan["patches"], plan["changed_ranges"]) == patch_plan(job["scenes"], mapping)
    verify_files({str(clip / job["layout"] / "assets" / name): value
                  for name, value in read(clip / job["layout"] / "assets_manifest.json").items()})
    for patch in plan["patches"]:
        assert 0 <= patch["start_frame"] < patch["end_frame"] <= timeline["total_frames"]
        assert patch["active_words"] == list(active_words(mapping, patch["sample_frame"]))
        if patch.get("reading"):
            assert all(list(active_words(mapping, f)) == patch["active_words"]
                       for f in range(patch["start_frame"], patch["end_frame"]))
    if mapping:
        cue = next(e for e in timeline["events"] if e["id"] == "reading_instruction")
        pause = timeline["events"][timeline["events"].index(cue) + 1]
        assert cue["end_frame"] == pause["start_frame"]
        assert pause["kind"] == "silence" and pause["end_frame"] - pause["start_frame"] == 360
    return timeline


def check(build, job):
    verify_inputs(build)
    validate_source(build, job)
    directory = job_dir(build, job)
    document = build / job["clip"] / job["layout"] / "index.html"
    previous = read(directory / "pre_render.json") if (directory / "pre_render.json").exists() else None
    same_html = previous and previous["files"].get(str(document)) == digest(document)
    if same_html:
        verify_files({p: value for p, value in previous["files"].items() if ".hyperframes" in Path(p).parts})
    run(["node", str(ROOT / "check_b2_layout_r3.cjs"), str(document),
         str(directory / "geometry.json"), job["layout"]], directory / "geometry.log")
    run(["node", str(ROOT / "check_b2_display.cjs"), str(document),
         str(directory / "plan.json"), str(directory / "display_checks.json")], directory / "display_checks.log")
    if not same_html:
        run([sys.executable, "-X", "utf8", str(ROOT / "hyperframes_local.py"), "check",
             str(document.parent), "--json", "--at-transitions", "--snapshots",
             "--no-browser-gpu", "--timeout", "4m"], directory / "browser_check.log")
    report_path = max((document.parent / ".hyperframes" / "artifacts" / "checks").glob("*.json"),
                      key=lambda p: p.stat().st_mtime_ns)
    report = read(report_path)
    assert report["ok"] and not report.get("browserSkipped", False)
    previous_geometry = read(Path(job["source"]) / (
        f"geometry_{job['layout']}.json" if job["clip"] == "full" else "geometry_portrait.json"))
    assert read(directory / "geometry.json")["questionPositions"] == previous_geometry["questionPositions"]
    atomic_json(directory / "pre_render.json", {"files": {
        str(document): digest(document), str(report_path): digest(report_path),
        str(directory / "geometry.json"): digest(directory / "geometry.json"),
        str(directory / "display_checks.json"): digest(directory / "display_checks.json"),
    }, "source_pcm_and_timeline_identical": True})
    print(f'{job["name"]}: native geometry, colors, word seeks and browser checks passed.', flush=True)


def native_review(build, job):
    import numpy as np
    from PIL import Image
    validate_source(build, job)
    directory = job_dir(build, job)
    plan = read(directory / "plan.json")
    output = directory / "native"
    output.mkdir(exist_ok=True)
    run([sys.executable, "-X", "utf8", str(ROOT / "hyperframes_local.py"), "snapshot",
         str(build / job["clip"] / job["layout"]), "--at", ",".join(p["stamp"] for p in plan["frames"]),
         "--no-end", "--keep", "--output", str(output), "--no-browser-gpu",
         "--timeout", "180000", "--json"], directory / "native_snapshot_r2.log")
    paths = [output / f'at-{p["stamp"]}s.png' for p in plan["frames"]]
    edited = [(p, path) for p, path in zip(plan["frames"], paths) if p["edited_review"]]
    contact_sheets = sheets([p for _, p in edited], [p for p, _ in edited], output, job["layout"])
    inherited = read(Path(job["source"]) / "browser_visual_review.json")
    inherited = inherited["layouts"][job["layout"]] if job["clip"] == "full" else inherited
    box = inherited["persistent_promotion"]["box"]
    with Image.open(paths[0]) as image:
        baseline = np.asarray(image.convert("RGB").crop(box))
    for path in paths:
        with Image.open(path) as image:
            assert np.array_equal(baseline, np.asarray(image.convert("RGB").crop(box)))
    images = {p["frame"]: path for p, path in zip(plan["frames"], paths)}
    crops = read(directory / "display_checks.json")["patchCrops"]
    for patch in plan["patches"]:
        patch["image"] = str(images[patch["sample_frame"]])
        patch["image_sha256"] = digest(patch["image"])
        if patch.get("crop_selector"):
            patch["crop"] = crops[patch["label"]]
    atomic_json(directory / "native_review.json", {
        "files": {str(path): digest(path) for path in paths + [Path(p) for p in contact_sheets]},
        "contact_sheets": contact_sheets, "patches": plan["patches"],
        "persistent_promotion_box": box, "persistent_promotion_pixel_identical": True,
        "reviewed_frames": len(paths), "edited_contact_frames": len(edited),
    })
    print(f'{job["name"]}: {len(paths)} native frames; {len(contact_sheets)} edited sheets.', flush=True)


def render_command(video, audio, patches, frames, output):
    command = ["ffmpeg", "-nostdin", "-v", "error", "-i", str(video), "-i", str(audio)]
    filters = ["[0:v]setpts=PTS-STARTPTS[v0]"]
    for index, patch in enumerate(patches, 1):
        command.extend(["-framerate", "24", "-i", patch["image"]])
        start, end = patch["start_frame"] / 24 - 1e-7, patch["end_frame"] / 24 - 1e-7
        x, y = 0, 0
        image = f"{index+1}:v"
        if patch.get("crop"):
            x, y, width, height = patch["crop"]
            right, bottom = (x + width + 1) // 2 * 2, (y + height + 1) // 2 * 2
            x, y = x // 2 * 2, y // 2 * 2
            width, height = right - x, bottom - y
            filters.append(f"[{image}]crop={width}:{height}:{x}:{y}[patch{index}]")
            image = f"patch{index}"
        filters.append(f"[v{index-1}][{image}]overlay={x}:{y}:eof_action=repeat:repeatlast=1:"
                       f"enable='gte(t,{start:.12f})*lt(t,{end:.12f})'[v{index}]")
    command.extend(["-filter_complex_threads", "1", "-filter_complex", ";".join(filters),
                    "-map", f"[v{len(patches)}]", "-map", "1:a:0", "-r", "24",
                    "-frames:v", str(frames), "-c:v", "libx264", "-preset", "fast",
                    "-crf", "18", "-pix_fmt", "yuv420p", "-threads", "4",
                    "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "1",
                    "-t", str(frames / 24), "-movflags", "+faststart", str(output)])
    return command


def render(build, job):
    verify_inputs(build)
    timeline = validate_source(build, job)
    directory = job_dir(build, job)
    verify_files(read(directory / "pre_render.json")["files"])
    verify_files(read(directory / "native_review.json")["files"])
    assert read(build / "visual_approval.json")["native"]
    output = build / job["clip"] / f"production_{job['layout']}.mp4"
    assert not output.exists(), "Refusing to overwrite an export."
    patches = read(directory / "native_review.json")["patches"]
    run(render_command(job["source_video"], build / job["clip"] / "dialogue.wav",
                       patches, timeline["total_frames"], output), directory / "render.log")
    print(f'{job["name"]}: revised export ready: {output}', flush=True)


def validate(build, job):
    import numpy as np
    from PIL import Image
    timeline = validate_source(build, job)
    clip, directory = build / job["clip"], job_dir(build, job)
    encoded = encoded_events(clip, timeline, job["layout"])
    probe = json.loads(subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,duration",
        "-of", "json", str(clip / f"production_{job['layout']}.mp4")
    ], check=True, capture_output=True, text=True).stdout)
    if job["clip"] != "full":
        assert float(probe["format"]["duration"]) < 180
        assert all(float(s["duration"]) < 180 for s in probe["streams"])
    plan = read(directory / "plan.json")
    native = read(directory / "native_review.json")
    verify_files(native["files"])
    output = directory / "encoded"
    output.mkdir(exist_ok=True)
    selector = "+".join(f'eq(n\\,{p["frame"]})' for p in plan["frames"])
    run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", str(clip / f"production_{job['layout']}.mp4"),
         "-vf", "select=" + selector, "-fps_mode", "vfr", "-frames:v", str(len(plan["frames"])),
         str(output / "frame-%03d.png")], directory / "extract.log")
    comparisons, edited_paths, edited_plan = [], [], []
    for index, point in enumerate(plan["frames"], 1):
        expected = directory / "native" / f'at-{point["stamp"]}s.png'
        actual = output / f"frame-{index:03d}.png"
        with Image.open(expected) as a, Image.open(actual) as b:
            assert a.size == b.size
            error = float(np.mean(np.abs(np.asarray(a.convert("RGB"), dtype=float) -
                                         np.asarray(b.convert("RGB"), dtype=float))))
            box = native["persistent_promotion_box"]
            promotion = float(np.mean(np.abs(np.asarray(a.convert("RGB").crop(box), dtype=float) -
                                             np.asarray(b.convert("RGB").crop(box), dtype=float))))
        assert error < 4 and promotion < 4, (job["name"], point["frame"], error, promotion)
        comparisons.append({**point, "mean_rgb_error": error, "promotion_mean_rgb_error": promotion,
                            "file": str(actual), "sha256": digest(actual)})
        if point["edited_review"]:
            edited_paths.append(actual)
            edited_plan.append(point)
    contact_sheets = sheets(edited_paths, edited_plan, output, job["layout"])
    atomic_json(directory / "validation.json", dict(
        status="pass", encoded=encoded, actual_durations=probe, frames=comparisons,
        contact_sheets=contact_sheets, unchanged_lossless_pcm=True, unchanged_timeline=True,
        spoken_reading_instruction_before_complete_15_second_silence=True))
    print(f'{job["name"]}: every encoded event and {len(comparisons)} frame comparisons passed.', flush=True)


def freeze(build):
    verify_inputs(build)
    approval = read(build / "visual_approval.json")
    assert approval["native"] and approval["encoded"]
    verify_files(approval["files"])
    jobs = read(build / "jobs.json")
    outputs = {}
    for job in jobs.values():
        timeline = validate_source(build, job)
        directory = job_dir(build, job)
        report = read(directory / "validation.json")
        verify_files(read(directory / "pre_render.json")["files"])
        verify_files(read(directory / "native_review.json")["files"])
        assert report["status"] == "pass"
        for frame in report["frames"]:
            verify_files({frame["file"]: frame["sha256"]})
        path = build / job["clip"] / f"production_{job['layout']}.mp4"
        assert report["encoded"]["sha256"] == digest(path)
        outputs[job["name"]] = dict(file=str(path.relative_to(build)), sha256=digest(path),
                                   frames=timeline["total_frames"], duration=timeline["duration"])
    files = {str(p.relative_to(build)): digest(p) for p in build.rglob("*")
             if p.is_file() and ".hyperframes" not in p.parts
             and p.name not in ("delivery_manifest.json", "delivery_audit.json")}
    code = {}
    for layer in read(build / "source_preservation.json")["layers"]:
        code.update(layer["code_inputs"])
    code.update({str(ROOT / name): digest(ROOT / name) for name in (
        "prepare_b2_display.py", "deliver_b2_display.py", "check_b2_display.cjs", "test_b2_display.py")})
    verify_files(code)
    atomic_json(build / "delivery_manifest.json", dict(
        files=files, code_inputs=code, outputs=outputs,
        scope="Five B2 display-only revisions; separate aligned reading cue; green Richtig/red Falsch.",
        video="Native replacement frames on changed intervals; other source frames reused; video re-encoded.",
        audio="Original complete mixed PCM encoded once to 192-kbps AAC; timelines unchanged.",
        limitations="Inherited ASR uncertainties and alignment scores retained; no human listening or continuous-motion certification.",
        publication="Nothing uploaded."))
    verify_files({str(build / name): value for name, value in files.items()})
    atomic_json(build / "delivery_audit.json", dict(
        status="pass", manifest_sha256=digest(build / "delivery_manifest.json"),
        files_rehashed=len(files), code_inputs_rehashed=len(code), all_five_outputs_verified=True))
    print(f"Frozen five revised B2 exports: {build}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("compose", "check", "review", "render", "validate", "freeze"))
    parser.add_argument("--build", required=True, type=Path)
    parser.add_argument("--job")
    args = parser.parse_args()
    build = args.build.resolve()
    if args.stage in ("compose", "freeze"):
        {"compose": compose, "freeze": freeze}[args.stage](build)
    else:
        jobs = read(build / "jobs.json")
        selected = [jobs[args.job]] if args.job else list(jobs.values())
        for job in selected:
            {"check": check, "review": native_review, "render": render, "validate": validate}[args.stage](build, job)
