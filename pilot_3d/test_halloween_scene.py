"""Silent native Halloween dressing fixture; no speech or video is generated."""

import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from runtime_config import qwen_python


def main():
    import bpy
    from check_v4_scene import check
    from prepare_audio import atomic_json
    from produce_v4 import scene_build

    build = Path(sys.argv[sys.argv.index("--") + 1]).resolve()
    subprocess.run([str(qwen_python()), str(ROOT / "test_dressing_scene.py"), "--prepare", str(build)],
                   cwd=ROOT, check=True)
    episode = json.loads((build / "episode.json").read_text(encoding="utf-8"))
    halloween = json.loads((ROOT / "episodes/dtz_b1_halloween_fest.json").read_text(encoding="utf-8"))
    episode["scene"]["dressing"] = halloween["scene"]["dressing"]
    atomic_json(build / "episode.json", episode)
    scene_build(build, profile="preview")
    bpy.ops.wm.open_mainfile(filepath=str(build / "studio.blend"))
    check(build)
    print("PASS: synthetic Halloween dressing and animated native scene checks.")


if __name__ == "__main__":
    main()
