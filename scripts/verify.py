"""Run project checks with its pinned Python environment and portable Node 24."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from launcher.supervisor import data_directory


def main():
    node = data_directory() / "runtimes/node-v24.21.0-win-x64/node.exe"
    if not node.is_file():
        raise SystemExit("Portable Node 24 is missing; run setup.bat first.")
    env = dict(os.environ, PYTHONPATH=str(ROOT / "backend"), PATH=str(node.parent) + os.pathsep + os.environ.get("PATH", ""))
    subprocess.run([sys.executable, "-m", "pytest", "backend/tests", "tests", "-q"], cwd=ROOT, env=env, check=True)
    npm = node.parent / "node_modules/npm/bin/npm-cli.js"
    for arguments in (("test",), ("run", "build"), ("audit", "--audit-level=high")):
        subprocess.run([str(node), str(npm), *arguments], cwd=ROOT / "frontend", env=env, check=True)
    print("All automated checks passed. Real model and Funnel checks are separate explicit acceptance steps.")


if __name__ == "__main__":
    main()
