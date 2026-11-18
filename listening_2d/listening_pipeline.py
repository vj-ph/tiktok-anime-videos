"""Build a new listening episode using an existing exam profile."""

import argparse
from importlib import import_module
import json
import os
from pathlib import Path
import re
import sys
import wave

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from listening_2d.preparation.prepare_sample import (CHIME_FILTER, FPS, FRAME_SAMPLES, MODEL, RATE, ROOT,
                            atomic_json, inspect_wav, mix_events, normalize,
                            prepare_turn_audio, sha256_file, synthesize, tempo_turn_audio, write_wav)


PROFILES = ("oeif-a2", "oeif-b1", "oeif-b2", "fide", "tef")
CUES = {"chime_start": "start", "chime_back": "end", "chime_remove": "reveal"}
GERMAN = {
    "oeif-a2": ("listening_2d.rendering.compose_a2_r2", "checks/check_a2_layout_r2.cjs", "listening_2d.checks.review_a2_frames_r2"),
    "oeif-b1": ("listening_2d.rendering.compose_full", None, "listening_2d.checks.review_full_frames"),
    "oeif-b2": ("listening_2d.rendering.compose_b2_r3", "checks/check_b2_layout_r3.cjs", "listening_2d.checks.review_b2_frames_r3"),
    "fide": ("listening_2d.rendering.compose_fide", "checks/check_fide_layout.cjs", "listening_2d.checks.review_fide_frames"),
}
LAYOUTS = ("landscape", "portrait")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def pin(paths):
    return {str(p.resolve(strict=True)): sha256_file(p) for p in paths}


def verify(files):
    for path, digest in files.items():
        if sha256_file(Path(path)) != digest:
            raise ValueError(f"Input changed; use a fresh build: {path}")


def episode_path(source, value):
    return (source.parent / value.replace("\\", "/")).resolve(strict=True)


def plan(profile, source):
    episode = read(source)
    paths = [source]
    content = {"episode": episode}
    if profile == "tef":
        from listening_2d.preparation.prepare_tef import planned_speech, sources
        episode, _, cards, groups, paths = sources(source)
        return {"episode": episode, "cards": cards, "groups": groups}, {
            "turns": planned_speech(episode, cards, groups)}, paths
    promotion = episode["promotion"]
    cover = "cover" if profile == "fide" else "cover_source"
    original = episode_path(source, promotion[cover])
    if promotion.get("cover_sha256", sha256_file(original)) != sha256_file(original):
        raise ValueError("Book cover does not match the episode hash.")
    promotion[cover] = str(original)
    paths.append(original)
    if profile == "oeif-a2":
        from listening_2d.preparation.prepare_a2_r2 import plan as make_plan
        timing = episode["timing"]
        keys = ("initial_read_seconds_per_part", "between_replays_seconds",
                "answer_seconds_after_final_play", "reveal_seconds", "between_parts_seconds")
        if (episode.get("level") != "A2" or tuple(timing[k] for k in keys) != (30, 5, 10, 3, 5)
                or [s["plays"] for s in episode["sections"]] != [2, 2, 1, 1]
                or episode["opening"]["display"] != "ÖIF A2 Hören"
                or episode["opening"]["text"] != "Ö I F A zwei Hören."):
            raise ValueError("Use the A2 title-only opening and current 30/5/10/3/5 sequence.")
        from listening_2d.checks.audit_a2_sequence import expected_sequence
        expected_sequence(episode)
        speech = make_plan(episode, final_cue="Ende des Testteils Hören.")
    elif profile == "oeif-b1":
        from listening_2d.preparation.prepare_full import plan as make_plan
        path = episode_path(source, episode["instruction_template"])
        paths.append(path)
        content["instructions"] = read(path)
        if ([s["part"] for s in episode["sections"]] != [1, 2, 3, 4]
                or [s["part"] for s in content["instructions"]["sections"]] != [1, 2, 3, 4]
                or episode["answer_reveal_seconds"] != 3):
            raise ValueError("Use the four-part B1 profile and separate three-second reveals.")
        speech = make_plan(episode, content["instructions"])
    elif profile == "oeif-b2":
        from listening_2d.preparation.prepare_b2_r3 import plan as make_plan
        if episode.get("level") != "B2" or [s["part"] for s in episode["sections"]] != [1, 2, 3]:
            raise ValueError("Use the three-part B2 profile.")
        speech = make_plan(episode)
        interview = episode["sections"][1]["groups"][0]
        switch = episode.get("interview_page2_at", "interview_q51")
        if switch not in {t["id"] for t in interview["recording"][1:]}:
            raise ValueError("Set interview_page2_at to the spoken question that starts page two.")
        speech["interview_page2_at"] = switch
    else:
        from listening_2d.preparation.prepare_fide import plan as make_plan
        for section in episode["situations"]:
            for item in section["items"]:
                if "image" in item:
                    image = episode_path(source, item["image"])
                    item["image"] = str(image)
                    paths.append(image)
        speech = make_plan(episode)
    content["cards"] = speech["cards"]
    for label, rows in (("speech", speech["turns"]), ("event", speech["events"])):
        ids = [row["id"] for row in rows]
        if len(set(ids)) != len(ids) or any(not re.fullmatch(r"[a-zA-Z0-9_-]+", i) for i in ids):
            raise ValueError(f"{label} IDs must be unique and safe for filenames.")
    evidence = episode.get("source", {})
    for key in ("book", "model_transcript", "research_pin"):
        item = evidence.get(key)
        digest = evidence.get(key + "_sha256")
        if isinstance(item, dict):
            digest = item.get("sha256")
            item = item.get("path")
        if item:
            path = episode_path(source, item)
            if digest:
                verify({str(path): digest})
            paths.append(path)
    return content, speech, paths


def approval(path, episode_sha256, digest):
    value = read(path)
    if (value.get("episode_sha256") != episode_sha256 or value.get("plan_sha256") != digest
            or value.get("script_approved") is not True
            or value.get("reviewer_model") != "claude-sonnet-5.5"
            or value.get("review_status") != "pass" or not value.get("review_files")):
        raise ValueError("Independent review and user approval must bind the exact episode and speech plan.")
    files = {str((path.parent / name).resolve()): checksum
             for name, checksum in value["review_files"].items()}
    verify(files)
    return {**pin([path]), **files}


def chimes(speech):
    index = ROOT / "assets" / "sfx" / "sources.json"
    settings = read(index)
    by_name = {asset["file"]: asset["sha256"] for asset in settings["assets"]}
    selected = {}
    for ident in {e.get("audio_id") for e in speech["events"]} & CUES.keys():
        name = settings["selected_cues"][CUES[ident]]
        selected[ident] = index.parent / name
        verify({str(selected[ident]): by_name[name]})
    return selected


def voices(profile, roles):
    from listening_2d.preparation.prepare_full import voices as austrian
    from listening_2d.preparation.prepare_fide import voices as swiss
    bindings, refs = swiss() if profile == "fide" else austrian()
    aliases = {"announcement_female": "opinion_mature"} if profile in ("oeif-a2", "oeif-b2") else {}
    return ({role: bindings[aliases.get(role, role)] for role in roles},
            {role: refs[aliases.get(role, role)] for role in roles})


def schedule(profile, speech, measured):
    if profile == "fide":
        from listening_2d.preparation.prepare_fide import schedule as clock
    elif profile == "oeif-a2":
        from listening_2d.preparation.prepare_a2_r2 import schedule as clock
    else:
        from listening_2d.preparation.prepare_b2 import schedule as clock
    timeline = clock(speech["events"], measured)
    if "interview_page2_at" in speech:
        timeline["interview_page2_at"] = speech["interview_page2_at"]
    if any(e["end_frame"] <= e["start_frame"] for e in timeline["events"]):
        raise ValueError("All events must have positive durations.")
    return timeline


def prepare(build, profile, source, approval_path=None):
    content, speech, paths = plan(profile, source)
    plan_path = build / "episode_plan.json"
    plan_data = {"profile": profile, "content": content, "speech": speech, "files": pin(paths)}
    if plan_path.is_file() and read(plan_path) != plan_data:
        raise ValueError("Episode plan or its inputs changed; use a fresh build.")
    if not plan_path.is_file():
        atomic_json(plan_path, plan_data)
    if not approval_path:
        print(f"{profile}: {len(speech['turns'])} speech clips planned (no synthesis).")
        return
    if (build / "timeline.json").is_file():
        raise ValueError("This build already has a measured timeline; continue with align or use a fresh build.")
    sources = plan_data["files"]
    approved = approval(approval_path, sources[str(source)], sha256_file(plan_path))
    if profile == "tef":
        from listening_2d.preparation.prepare_tef import prepare as prepare_tef
        atomic_json(build / "workflow_approval.json", approved)
        prepare_tef(build, config_path=source)
        return
    bindings, refs = voices(profile, {t["speaker"] for t in speech["turns"]})
    effects = chimes(speech)
    files = {**sources, **approved, **pin(effects.values()),
             **{entry["path"]: entry["sha256"] for role in refs.values() for entry in role.values()}}
    if (build / "input_pin.json").exists() and read(build / "input_pin.json")["files"] != files:
        raise ValueError("Episode inputs changed; use a fresh build.")
    atomic_json(build / "input_pin.json", {"files": files})
    atomic_json(build / "voice_references.json", refs)
    atomic_json(build / "sample_content.json", content)
    atomic_json(build / "speech_plan.json", speech)
    audio = build / "audio"
    audio.mkdir(exist_ok=True)
    measured = {}
    for ident, path in effects.items():
        target = audio / f"{ident}.wav"
        measured[ident] = {**normalize(path, target, CHIME_FILTER), "audio": str(target),
                           "sha256": sha256_file(target), "original_sha256": sha256_file(path)}
    for event in speech["events"]:
        if event.get("audio_id") in effects and "seconds" in event:
            if measured[event["audio_id"]]["frames"] > round(event["seconds"] * FPS) * FRAME_SAMPLES:
                raise ValueError(f"Complete chime does not fit: {event['id']}")
    raw = synthesize({"language": "de", "voices": bindings, "turns": speech["turns"]},
                     ROOT, audio, MODEL, "cpu", 8)
    for turn, result in zip(speech["turns"], raw, strict=True):
        ident = turn["id"]
        cleaned = prepare_turn_audio(ident, result, audio)
        slowed = tempo_turn_audio(ident, cleaned, audio, .8)
        target = audio / f"{ident}.wav"
        measured[ident] = {**turn, **normalize(Path(slowed["audio"]), target), "audio": str(target),
                           "sha256": sha256_file(target), "raw_audio": result["audio"],
                           "processed_audio": slowed["audio"], "atempo": .8}
    timeline = schedule(profile, speech, measured)
    write_wav(build / "dialogue.wav", mix_events(timeline["events"]))
    atomic_json(build / "audio_manifest.json", measured)
    atomic_json(build / "timeline.json", timeline)


def validate(build, profile, source):
    verify(read(build / "input_pin.json")["files"])
    planned = read(build / "episode_plan.json")
    verify(planned["files"])
    if profile == "tef":
        from listening_2d.rendering.deliver_tef import validate as validate_tef
        verify(read(build / "workflow_approval.json"))
        if (read(build / "content.json") != planned["content"]
                or read(build / "speech_plan.json") != planned["speech"]):
            raise ValueError("TEF build content or plan differs from the approved episode.")
        validate_tef(build)
        return
    content, speech, _ = plan(profile, source)
    if (read(build / "sample_content.json") != content or read(build / "speech_plan.json") != speech):
        raise ValueError("Build content or plan differs from the approved episode.")
    timeline = read(build / "timeline.json")
    measured = read(build / "audio_manifest.json")
    for turn in speech["turns"]:
        item = measured[turn["id"]]
        if any(item.get(k) != turn[k] for k in ("text", "speaker")) or item.get("atempo") != .8:
            raise ValueError(f"Speech manifest differs from the approved script: {turn['id']}")
    expected = schedule(profile, speech, measured)
    if (any(timeline.get(k) != v for k, v in expected.items() if k != "turns")
            or [{k: t[k] for k in t if k not in ("words", "alignment_key")}
                for t in timeline["turns"]] != expected["turns"]):
        raise ValueError("Measured timeline differs from the profile's authored sequence.")
    with wave.open(str(build / "dialogue.wav"), "rb") as track:
        if ((track.getframerate(), track.getnchannels(), track.getsampwidth(), track.getnframes())
                != (RATE, 1, 2, timeline["total_frames"] * FRAME_SAMPLES)):
            raise ValueError("Lossless audio does not fit the exact frame clock.")
        for event in timeline["events"]:
            size = (event["end_frame"] - event["start_frame"]) * FRAME_SAMPLES
            actual = track.readframes(size)
            exact = b""
            if "audio" in event:
                audio = Path(event["audio"])
                verify({str(audio): event["sha256"]})
                with wave.open(str(audio), "rb") as clip:
                    exact = clip.readframes(clip.getnframes())
            if not actual.startswith(exact) or any(actual[len(exact):]):
                raise ValueError(f"Unexpected audio or non-silent padding: {event['id']}")
    if profile == "oeif-a2":
        from listening_2d.checks.audit_a2_sequence import compare_sequence
        report = compare_sequence(content["episode"], timeline)
        if not report["matches_requested_sequence"]:
            raise ValueError(f"A2 sequence gate failed: {report['issues']}")
    elif profile == "oeif-b1":
        from listening_2d.checks.validate_full import check_structure
        check_structure(timeline, content)
    elif profile == "oeif-b2":
        from listening_2d.checks.audit_b2_sequence_r3 import compare_sequence
        report = compare_sequence(content["episode"], timeline)
        if not report["matches_requested_sequence"]:
            raise ValueError(f"B2 sequence gate failed: {report['issues']}")
    elif profile == "fide":
        from listening_2d.checks.audit_fide_sequence import compare_sequence
        report = compare_sequence(timeline)
        if not report["ok"]:
            raise ValueError(f"Fide sequence gate failed: {report['issues']}")


def align(build, profile):
    from align_words import align_build, validate_words
    if profile == "tef":
        from listening_2d.preparation.prepare_tef import process
        process(build)
        return
    timeline = read(build / "timeline.json")
    wanted = {"oeif-a2": 4, "oeif-b1": 4, "oeif-b2": 3}
    ids = {f"instruction_{i}" for i in range(1, wanted.get(profile, 0) + 1)}
    ids |= {"checking_instruction"} if profile == "oeif-b2" else {"title"}
    selected = [t for t in timeline["turns"] if
                (t.get("visible", False) if profile == "fide" else t["id"] in ids)]
    if not selected or (profile != "fide" and {t["id"] for t in selected} != ids):
        raise ValueError("Visible narration is missing from the measured timeline.")
    work = build / "alignment_inputs"
    work.mkdir(exist_ok=True)
    atomic_json(work / "timeline.json", {"language": "de", "turns": selected})
    align_build(work)
    result = read(work / "timeline.json")
    measured = {t["id"]: t for t in result["turns"]}
    for turn in selected:
        row = measured[turn["id"]]
        turn.update(words=validate_words(row["words"], turn["text"], turn["wav_duration"]),
                    alignment_key=row["alignment_key"])
    timeline["word_alignment"] = result["word_alignment"]
    atomic_json(build / "timeline.json", timeline)
    atomic_json(build / "word_alignment.json", {"provenance": result["word_alignment"],
                "turns": [{k: t[k] for k in ("id", "start", "words", "alignment_key")} for t in selected]})


def compose(build, profile):
    if profile == "tef":
        from listening_2d.rendering.compose_tef import compose as compose_tef
        compose_tef(build)
        return
    composer = import_module(GERMAN[profile][0]).compose
    kwargs = {"episode": read(build / "sample_content.json")["episode"]} if profile == "fide" else {}
    if os.name != "nt":
        from runtime_config import font_path
        kwargs["fonts"] = {"arial.ttf": font_path(), "arialbd.ttf": font_path(bold=True)}
    composer(build, **kwargs)
    if profile == "oeif-a2":
        from listening_2d.checks.audit_a2_sequence import opening_headings
        for layout in LAYOUTS:
            html = (build / layout / "index.html").read_text(encoding="utf-8")
            if opening_headings(html) != [("h1", "ÖIF A2 Hören")]:
                raise ValueError(f"Wrong A2 opening in {layout}.")


def projects(build):
    paths = [build / "timeline.json", build / "dialogue.wav", build / "composition_receipt.json"]
    for layout in LAYOUTS:
        paths.extend(p for p in (build / layout).rglob("*") if p.is_file()
                     and not {".hyperframes", "node_modules"}.intersection(p.parts))
    return pin(paths)


def check(build, profile):
    from listening_2d.rendering.deliver_tef import run
    files = projects(build)
    if (read(build / "composition_receipt.json")["timeline_sha256"]
            != sha256_file(build / "timeline.json")):
        raise ValueError("Compose again after changing the measured timeline.")
    if profile == "tef":
        from listening_2d.rendering.deliver_tef import check as check_tef
        for layout in LAYOUTS:
            check_tef(build, layout)
            captures = build / f"native_captures_{layout}.json"
            files.update(pin([captures, *(Path(c["native_file"]) for c in read(captures))]))
    else:
        if profile == "oeif-b1":
            from listening_2d.checks.validate_full import check_layouts
            check_layouts(build, read(build / "timeline.json"), read(build / "sample_content.json"))
        for layout in LAYOUTS:
            folder = build / layout
            checker = GERMAN[profile][1]
            if checker:
                run(["node", ROOT / checker, folder / "index.html",
                     build / f"geometry_{layout}.json", layout], build / f"geometry_{layout}.log")
            reports = folder / ".hyperframes" / "artifacts" / "checks"
            previous = set(reports.glob("*.json"))
            run([sys.executable, "-X", "utf8", ROOT / "hyperframes_local.py", "check",
                 folder, "--json", "--at-transitions", "--snapshots", "--no-browser-gpu",
                 "--timeout", "4m"], build / f"check_{layout}.log")
            new_reports = set(reports.glob("*.json")) - previous
            if not new_reports:
                raise ValueError(f"No new browser check report for {layout}.")
            report = max(new_reports, key=lambda p: p.stat().st_mtime_ns)
            summary = read(report)
            if not summary["ok"] or summary.get("browserSkipped", False):
                raise ValueError(f"Browser gate failed: {report}")
            files.update(pin([report]))
        import_module(GERMAN[profile][2]).review(build)
        report = build / "browser_visual_review.json"
        files.update(pin([report, *(build / f"contact_{layout}" / name
                                    for layout, info in read(report)["layouts"].items()
                                    for name in info["browser_frames"])]))
    verify(files)
    atomic_json(build / "workflow_checks.json", files)


def render(build, profile):
    from listening_2d.rendering.deliver_tef import run
    receipt = build / "workflow_checks.json"
    verify(read(receipt))
    review = read(build / "audio_review_resolution.json")
    if (review.get("status") != "pass_with_asr_notes"
            or review.get("audio_manifest_sha256") != sha256_file(build / "audio_manifest.json")):
        raise ValueError("Resolve ASR review for the current measured speech before rendering.")
    speech_report = build / "speech_review_small.json"
    rows = read(speech_report)
    manifest = read(build / "audio_manifest.json")
    expected = {ident: (item["text"], item["sha256"]) for ident, item in manifest.items()
                if item.get("text") and item.get("kind") != "sfx"}
    if (not rows["complete"] or review.get("speech_review_sha256") != sha256_file(speech_report)
            or {row["id"]: (row["expected"], row["audio_sha256"]) for row in rows["turns"]} != expected):
        raise ValueError("A complete small-model ASR review must match the measured audio.")
    visual = read(build / "visual_approval.json")
    if visual.get("workflow_checks_sha256") != sha256_file(receipt):
        raise ValueError("Record inspection of the current native checks and captures.")
    if profile == "tef":
        from listening_2d.rendering.deliver_tef import render as render_tef
        for layout in LAYOUTS:
            render_tef(build, layout)
        return
    duration = read(build / "timeline.json")["duration"]
    for layout in LAYOUTS:
        master, final = (build / f"{prefix}_{layout}.mp4" for prefix in ("render", "production"))
        if master.exists() or final.exists():
            raise ValueError(f"Refusing to overwrite an existing {layout} export.")
        run([sys.executable, "-X", "utf8", ROOT / "hyperframes_local.py", "render",
             build / layout, "--fps", "24", "--quality", "delivery", "--workers", "2",
             "--no-browser-gpu", "--output", master], build / f"render_{layout}.log")
        run(["ffmpeg", "-nostdin", "-v", "error", "-i", master, "-i", build / "dialogue.wav",
             "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac",
             "-b:a", "192k", "-ar", "48000", "-ac", "1", "-t", str(duration),
             "-movflags", "+faststart", final], build / f"mux_{layout}.log")


def encoded(build, profile):
    verify(read(build / "workflow_checks.json"))
    if profile == "tef":
        from listening_2d.rendering.deliver_tef import encoded as encoded_tef
        prefix = "preview"
        for layout in LAYOUTS:
            encoded_tef(build, layout)
        checks = {layout: read(build / f"encoded_checks_{layout}.json") for layout in LAYOUTS}
    else:
        from listening_2d.checks.validate_full import encoded_events
        prefix = "production"
        timeline = read(build / "timeline.json")
        checks = {layout: encoded_events(build, timeline, layout) for layout in LAYOUTS}
        import_module(GERMAN[profile][2]).review(build, encoded=True)
    files = [build / f"{prefix}_{layout}.mp4" for layout in LAYOUTS]
    if profile != "tef":
        report = build / "export_visual_review.json"
        files.extend([report, *(build / f"encoded_{layout}" / f"frame-{i:03d}.png"
                                for layout, info in read(report)["layouts"].items()
                                for i, _ in enumerate(info["export_comparisons"], 1))])
    else:
        files.extend(build / f"encoded_checks_{layout}.json" for layout in LAYOUTS)
    atomic_json(build / "workflow_encoded.json", {"checks": checks, "files": pin(files)})


def freeze(build):
    receipt = build / "workflow_encoded.json"
    verify(read(receipt)["files"])
    verify(read(build / "workflow_checks.json"))
    if read(build / "visual_approval.json").get("workflow_encoded_sha256") != sha256_file(receipt):
        raise ValueError("Record inspection of the current encoded outputs before freezing.")
    files = {p.relative_to(build).as_posix(): sha256_file(p) for p in build.rglob("*")
             if p.is_file() and not {".hyperframes", "node_modules"}.intersection(p.parts)}
    atomic_json(build / "delivery_manifest.json",
                {"workflow": read(build / "workflow.json"), "files": files,
                 "inputs": read(build / "input_pin.json")["files"], "uploaded": False})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("plan", "prepare", "align", "review", "compose", "check",
                                         "render", "encoded", "freeze"))
    parser.add_argument("--profile", choices=PROFILES)
    parser.add_argument("--episode", type=Path)
    parser.add_argument("--build", required=True, type=Path)
    parser.add_argument("--approval", type=Path)
    parser.add_argument("--model", default="small", choices=("small", "medium"))
    args = parser.parse_args(argv)
    if not __debug__:
        parser.error("Run without -O so exam validation assertions remain enabled.")
    build = args.build.resolve()
    if not build.is_relative_to(ROOT / "builds") and build.is_relative_to(ROOT):
        parser.error("Use a named directory under listening_2d/builds or a dedicated external path.")
    if build == ROOT / "builds" or build in ROOT.parents:
        parser.error("Use a dedicated build directory, not a parent or builds root.")
    state = build / "workflow.json"
    if (build / "delivery_manifest.json").exists():
        parser.error("The delivery is frozen. Use a fresh build.")
    if args.stage in ("plan", "prepare"):
        if not args.profile or not args.episode:
            parser.error("Supply --profile and --episode.")
        if args.stage == "prepare" and not args.approval:
            parser.error("Run plan and supply --approval before synthesis.")
        if args.stage == "prepare" and not (build / "episode_plan.json").is_file():
            parser.error("Run plan in this build before synthesis.")
        source = args.episode.resolve(strict=True)
        binding = {"profile": args.profile, "episode": str(source), "episode_sha256": sha256_file(source)}
        if state.exists():
            if read(state) != binding:
                parser.error("Build is bound to another episode or profile; use a fresh build.")
        elif build.exists() and any(build.iterdir()):
            parser.error("Refusing to use a nonempty directory not created by this workflow.")
        build.mkdir(parents=True, exist_ok=True)
        if not state.exists():
            atomic_json(state, binding)
        prepare(build, args.profile, source, args.approval.resolve(strict=True)
                if args.stage == "prepare" else None)
        return
    binding = read(state)
    profile, source = binding["profile"], Path(binding["episode"])
    verify({str(source): binding["episode_sha256"]})
    validate(build, profile, source)
    if args.stage == "review":
        if profile == "tef":
            if args.model != "small":
                parser.error("The TEF adapter currently supports the small model.")
            from listening_2d.preparation.prepare_tef import review
            review(build)
        else:
            from listening_2d.preparation.process_b2 import review
            review(build, args.model)
    elif args.stage == "freeze":
        freeze(build)
    else:
        stages = {"align": align, "compose": compose, "check": check, "render": render, "encoded": encoded}
        stages[args.stage](build, profile)


if __name__ == "__main__":
    main()
