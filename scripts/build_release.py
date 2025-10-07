"""Build a PyInstaller release including the Playwright Chromium runtime."""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str], *, env: dict[str, str]) -> None:
    print("[build]", " ".join(cmd))
    subprocess.run(cmd, check=True, env=env)


def ensure_playwright(browsers_dir: Path, env: dict[str, str]) -> None:
    browsers_dir.mkdir(parents=True, exist_ok=True)
    run([sys.executable, "-m", "playwright", "install", "chromium"], env=env)


def build_executable(root: Path, dist_dir: Path, build_dir: Path, name: str, *, clean: bool, env: dict[str, str]) -> None:
    spec_path = root / "WTC3Logger.spec"
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(build_dir),
    ]
    if clean:
        cmd.append("--clean")
    cmd.append(str(spec_path))
    run(cmd, env=env)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a distributable build")
    parser.add_argument("--name", default="WTC3Logger", help="Name of the generated application directory")
    parser.add_argument("--clean", action="store_true", help="Remove previous build artifacts before building")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    dist_dir = root / "dist"
    build_dir = root / "build"
    browsers_dir = build_dir / "playwright-browsers"

    env = os.environ.copy()
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers_dir)
    env["WTC3_APP_NAME"] = args.name

    if args.clean:
        shutil.rmtree(dist_dir, ignore_errors=True)
        shutil.rmtree(build_dir, ignore_errors=True)

    build_dir.mkdir(exist_ok=True)
    dist_dir.mkdir(exist_ok=True)

    ensure_playwright(browsers_dir, env)
    build_executable(root, dist_dir, build_dir, args.name, clean=args.clean, env=env)

    print(f"[build] Finished. Artifacts in {dist_dir / args.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
