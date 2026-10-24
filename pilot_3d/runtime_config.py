"""Platform-specific tools and fonts shared by the pipeline and Blender workers."""

import os
from pathlib import Path
import shutil
import sys
from generation_runtime import run_process

ROOT = Path(__file__).resolve().parent
RENDER_DEVICES = ("CPU", "CUDA", "OPTIX", "HIP", "ONEAPI")
RENDER_JOBS = (1, 2, 4, 8)


def tool_path(name):
    override = os.environ.get(f"{name.upper()}_EXE")
    if override:
        return Path(override).expanduser().resolve()
    executable = name + (".exe" if sys.platform == "win32" else "")
    platform = "windows" if sys.platform == "win32" else "linux"
    portable = ROOT / ".tools" / platform / name / executable
    local = ROOT / ".tools" / name / executable
    return next((path for path in (portable, local) if path.is_file()),
                Path(shutil.which(executable) or portable))


def qwen_python():
    override = os.environ.get("QWEN_PYTHON")
    if override:
        return Path(override).expanduser()
    local = ROOT / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    legacy = Path("/home/ronggong/lang/german/.venvs/qwen-tts-test/bin/python")
    return next((path for path in (local, legacy) if path.is_file()), Path(sys.executable))


def font_path(bold=False):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    directories = ([Path(os.environ["DEJAVU_FONT_DIR"])] if os.environ.get("DEJAVU_FONT_DIR") else [
        ROOT / ".tools" / "fonts", Path("/usr/share/fonts/truetype/dejavu"),
        Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts",
    ])
    return next((directory / name for directory in directories if (directory / name).is_file()),
                directories[0] / name)


def caption_fonts(build):
    """Use the exact measured fonts in libass too, without drive-letter escaping."""
    directory = Path(build) / "caption_fonts"
    directory.mkdir(exist_ok=True)
    for bold in (False, True):
        source = font_path(bold)
        if not source.is_file():
            raise FileNotFoundError(f"Missing {source}; run python setup_runtime.py --only fonts.")
        target = directory / source.name
        if not target.is_file() or target.read_bytes() != source.read_bytes():
            shutil.copy2(source, target)


def configure_cycles(bpy, backend):
    scene = bpy.context.scene
    if backend == "CPU":
        if scene.render.engine == "CYCLES":
            scene.cycles.device = "CPU"
        print("Render device: CPU", flush=True)
        return
    if backend not in RENDER_DEVICES:
        raise ValueError(f"Unsupported render device: {backend}")
    if scene.render.engine != "CYCLES":
        raise ValueError("GPU backend selection requires the Cycles engine.")
    preferences = bpy.context.preferences.addons["cycles"].preferences
    preferences.compute_device_type = backend
    preferences.refresh_devices()
    selected = []
    for device in preferences.devices:
        device.use = device.type == backend
        if device.use:
            selected.append(device.name)
    if not selected:
        raise RuntimeError(f"No {backend} GPU available. Check GPU/driver support or use --render-device CPU.")
    scene.cycles.device = "GPU"
    print(f"Render device: {backend}: {', '.join(selected)}", flush=True)


def render_expression(backend, build=None):
    expression = (
        f"import sys; sys.path.insert(0, {str(ROOT)!r}); import bpy; "
        f"from runtime_config import configure_cycles; configure_cycles(bpy, {backend!r}); "
        "bpy.context.scene.render.use_persistent_data=True; "
    )
    if build is not None:
        expression += f"bpy.context.scene.render.filepath={str(Path(build) / 'frames' / 'frame_')!r}; "
    return expression


def check_render_device(backend):
    expression = (
        "import bpy; bpy.context.scene.render.engine='CYCLES'; "
        + render_expression(backend)
    )
    run_process([str(tool_path("blender")), "-b", "--factory-startup", "--disable-autoexec",
                 "--python-exit-code", "1", "--python-expr", expression], check=True)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Check Blender device discovery (not a render benchmark).")
    parser.add_argument("--render-device", choices=RENDER_DEVICES, default="CPU")
    check_render_device(parser.parse_args().render_device)
