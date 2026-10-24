"""Tiny native Blender fixture; no synthesis, rendered frames or delivered media."""

import json
from pathlib import Path
import sys
import wave

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def main():
    import bpy
    from check_v4_scene import check
    from episode_config import read_episode
    from episode_profiles import active_actors
    from prepare_audio import atomic_json, build_timeline
    from produce_v4 import scene_build
    from studio_characters import StudioCharacter

    build = Path(sys.argv[sys.argv.index("--") + 1]).resolve()
    if build == ROOT or ROOT in build.parents and not build.is_relative_to(ROOT / "builds"):
        raise ValueError("Use a new fixture directory under builds or outside the checkout.")
    if build.exists() and any(build.iterdir()):
        raise ValueError("Use an empty fixture directory.")
    build.mkdir(parents=True, exist_ok=True)
    episode = read_episode(ROOT / "episodes/tef_canada_a1.json")
    episode.update(id="synthetic_interview_fixture", intro_seconds=0, outro_seconds=0,
                   task_card=[], pictures={}, cta=[], turns=episode["turns"][:3])
    episode["scene"]["entrance"] = False
    for turn, text in zip(episode["turns"], ("Bonjour Madame.", "Commencez maintenant.", "Bonjour Monsieur.")):
        turn.update(text=text, pause_after=0)
        turn.pop("task_card_delay_seconds", None)
        turn.pop("picture_card_delay_seconds", None)
        turn.pop("picture", None)
        if turn["camera"] == "picture_a":
            turn["camera"] = "candidate_a"
    audio = build / "synthetic_silence.wav"
    with wave.open(str(audio), "wb") as output:
        output.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
        output.writeframes(bytes(6000 * 2))
    info = {"audio": str(audio), "frames": 6000, "sample_rate": 48000}
    timeline = build_timeline(episode, [info] * 3, [[{"start": 0, "end": .125, "value": "X"}]] * 3)
    for turn in timeline["turns"]:
        turn["words"] = [{"word": word, "start": .01 + index * .05,
                          "end": .05 + index * .05, "score": 1}
                         for index, word in enumerate(turn["text"].split())]
    timeline["word_alignment"] = {"synthetic_fixture": True, "language": "fr"}
    with wave.open(str(build / "dialogue.wav"), "wb") as output:
        output.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
        output.writeframes(bytes(timeline["total_frames"] * 2000 * 2))
    atomic_json(build / "episode.json", episode)
    atomic_json(build / "timeline.json", timeline)
    scene_build(build, profile="preview")
    check(build)
    for name in active_actors(episode):
        actor = StudioCharacter.from_scene(name)
        if not actor.root.animation_data or not actor.rig.animation_data.action:
            raise ValueError(f"Active actor was not baked: {name}")
    report = json.loads((build / "scene_checks.json").read_text())
    if set(report["actors"]) != {"candidate_a", "examiner"}:
        raise ValueError("Native scene still checks an inactive actor.")
    if report["cast"]["hidden_objects_checked"] < 10:
        raise ValueError("Native fixture did not hide unused geometry.")
    if any(build.glob("*.mp4")) or any((build / "frames").iterdir()):
        raise ValueError("This fixture must not create rendered video.")
    print("PASS: native interview cast, hidden geometry, baked controls, saved-scene checks; "
          "synthetic fixture only, no synthesis or rendered video.")


if __name__ == "__main__":
    main()
