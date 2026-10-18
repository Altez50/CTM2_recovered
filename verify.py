#!/usr/bin/env python3
"""Install (optionally) and run the complete CTM P0 quality gate."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CURRENT = ROOT / "current"
WEB = CURRENT / "web-client"


def run(command: list[str], cwd: Path = ROOT) -> None:
    print(f"\n> {' '.join(command)}", flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def executable(name: str) -> str:
    candidates = [name]
    if sys.platform == "win32":
        candidates.insert(0, f"{name}.cmd")
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    raise SystemExit(f"Required executable not found: {name}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install", action="store_true", help="install Python, Node, and Chromium dependencies first")
    parser.add_argument("--skip-e2e", action="store_true", help="skip Playwright (useful for backend-only iteration)")
    parser.add_argument("--ut", action="store_true", help="also reconcile posted debt accruals with the configured local 1C reference (Windows)")
    args = parser.parse_args()

    if args.ut and sys.platform != "win32":
        parser.error("--ut requires Windows and the matching 1C COM connector")

    npm = executable("npm")
    npx = executable("npx")
    if args.install:
        run([sys.executable, "-m", "pip", "install", "-r", "api/requirements-dev.txt"], CURRENT)
        if args.ut:
            run([sys.executable, "-m", "pip", "install", "-r", "runner/trade_harness/requirements.txt"])
        run([npm, "ci"], WEB)
        run([npx, "playwright", "install", "chromium"], WEB)

    run([sys.executable, "-m", "compileall", "-q", "api"], CURRENT)
    run([sys.executable, "-m", "compileall", "-q", "runner"], ROOT)
    run([sys.executable, "runner/trade_harness/suite.py", "validate"])
    run([sys.executable, "-m", "pytest"], CURRENT)
    if args.ut:
        run([executable("powershell"), "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(ROOT / "runner" / "trade_harness" / "run.ps1"),
             "-PythonPath", sys.executable])
    run([npm, "run", "build"], WEB)
    if not args.skip_e2e:
        run([npm, "run", "test:e2e"], WEB)
    print("\nCTM quality gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
