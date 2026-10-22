"""Generated-run locations and read-only compatibility with the old flat layout."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent
BUILDS = ROOT / "builds"


def legacy_run_name(name):
    if name == "build":
        return "pilot_v1"
    if name.startswith("build_") and len(name) > len("build_"):
        return name[len("build_"):]
    return None


def build_directory(path):
    """Place a project-level run name in builds; preserve explicit other paths."""
    path = Path(path).resolve()
    if path.parent == ROOT and path != BUILDS:
        path = (BUILDS / (legacy_run_name(path.name) or path.name)).resolve()
    if path in (ROOT, BUILDS) or path in ROOT.parents:
        raise ValueError("Use a dedicated output directory, not the project, builds root or an ancestor.")
    return path


def resolve_build_reference(path):
    """Find moved runs without editing the paths recorded in frozen artifacts."""
    path = Path(path).resolve()
    if path.exists() or not path.is_relative_to(ROOT):
        return path
    relative = path.relative_to(ROOT)
    if relative.parts:
        name = legacy_run_name(relative.parts[0])
        if name is not None:
            relocated = (BUILDS / name / Path(*relative.parts[1:])).resolve()
            if relocated.is_relative_to(BUILDS) and relocated.exists():
                return relocated
    return path
