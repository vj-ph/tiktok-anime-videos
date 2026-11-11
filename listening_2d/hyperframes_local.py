"""Run the pinned local CLI with uploads, telemetry and skill updates disabled."""

import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent

if __name__ == "__main__":
    env = dict(os.environ)
    env.update({
        "HYPERFRAMES_NO_TELEMETRY": "1", "DO_NOT_TRACK": "1",
        "HYPERFRAMES_NO_UPDATE_CHECK": "1", "HYPERFRAMES_NO_AUTO_INSTALL": "1",
        "HYPERFRAMES_SKIP_SKILLS": "1", "HYPERFRAMES_NO_ORPHAN_CLEANUP": "1",
    })
    chrome = Path(env.get("PROGRAMFILES", r"C:\Program Files")) / "Google" / "Chrome" / "Application" / "chrome.exe"
    if chrome.is_file():
        env.setdefault("HYPERFRAMES_BROWSER_PATH", str(chrome))
    allowed = {"check", "snapshot", "render", "doctor", "lint", "info", "compositions", "docs"}
    if len(sys.argv) < 2 or sys.argv[1] not in allowed:
        raise SystemExit("Choose a local check, snapshot, render or diagnostic command.")
    binary = ROOT / "node_modules" / ".bin" / "hyperframes.cmd"
    raise SystemExit(subprocess.run([str(binary), *sys.argv[1:]], env=env).returncode)
