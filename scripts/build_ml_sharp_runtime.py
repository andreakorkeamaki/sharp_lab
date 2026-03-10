from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

DEFAULT_REPO_URL = "https://github.com/apple/ml-sharp.git"
DEFAULT_REPO_REF = "1eaa046834b81852261262b41b0919f5c1efdd2e"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a self-contained ml-sharp runtime for release bundles.")
    parser.add_argument("--runtime-dir", required=True, help="Directory where the runtime bundle should be written.")
    parser.add_argument("--repo-url", default=DEFAULT_REPO_URL, help="Git URL for the apple/ml-sharp source.")
    parser.add_argument("--repo-ref", default=DEFAULT_REPO_REF, help="Git ref or commit to check out.")
    parser.add_argument("--source-dir", help="Use a local ml-sharp checkout instead of cloning.")
    return parser.parse_args()


def run(command: list[str], cwd: Path | None = None) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def clone_source(repo_url: str, repo_ref: str, source_dir: Path) -> None:
    run(["git", "clone", repo_url, str(source_dir)])
    run(["git", "checkout", repo_ref], cwd=source_dir)


def prepare_source_tree(args: argparse.Namespace) -> tuple[Path, bool]:
    if args.source_dir:
        return Path(args.source_dir).expanduser().resolve(), False

    temp_dir = Path(tempfile.mkdtemp(prefix="ml-sharp-source-"))
    source_dir = temp_dir / "ml-sharp"
    clone_source(args.repo_url, args.repo_ref, source_dir)
    return source_dir, True


def venv_python(venv_dir: Path) -> Path:
    if sys.platform == "win32":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def sharp_entrypoint(venv_dir: Path) -> Path:
    if sys.platform == "win32":
        return venv_dir / "Scripts" / "sharp.exe"
    return venv_dir / "bin" / "sharp"


def write_launchers(runtime_dir: Path) -> None:
    posix_launcher = runtime_dir / "run-sharp"
    posix_launcher.write_text(
        """#!/bin/sh
set -eu

RUNTIME_DIR="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
VENV_DIR="$RUNTIME_DIR/.venv"
export XDG_CACHE_HOME="$RUNTIME_DIR/.cache"
export TORCH_HOME="$RUNTIME_DIR/.cache/torch"
export MPLCONFIGDIR="$RUNTIME_DIR/.cache/matplotlib"

exec "$VENV_DIR/bin/sharp" "$@"
""",
        encoding="utf-8",
    )
    posix_launcher.chmod(0o755)

    windows_launcher = runtime_dir / "run-sharp.cmd"
    windows_launcher.write_text(
        """@echo off
setlocal
set "RUNTIME_DIR=%~dp0"
if "%RUNTIME_DIR:~-1%"=="\\" set "RUNTIME_DIR=%RUNTIME_DIR:~0,-1%"
set "VENV_DIR=%RUNTIME_DIR%\\.venv"
set "XDG_CACHE_HOME=%RUNTIME_DIR%\\.cache"
set "TORCH_HOME=%RUNTIME_DIR%\\.cache\\torch"
set "MPLCONFIGDIR=%RUNTIME_DIR%\\.cache\\matplotlib"

"%VENV_DIR%\\Scripts\\sharp.exe" %*
""",
        encoding="utf-8",
    )


def copy_runtime_metadata(source_dir: Path, runtime_dir: Path, repo_url: str, repo_ref: str) -> None:
    licenses_dir = runtime_dir / "licenses"
    licenses_dir.mkdir(parents=True, exist_ok=True)
    for filename in ("LICENSE", "LICENSE_MODEL", "ACKNOWLEDGEMENTS", "README.md"):
        source_path = source_dir / filename
        if source_path.exists():
            shutil.copy2(source_path, licenses_dir / filename)

    build_info = {
        "repo_url": repo_url,
        "repo_ref": repo_ref,
        "source_dir": str(source_dir),
    }
    (runtime_dir / "build-info.json").write_text(json.dumps(build_info, indent=2), encoding="utf-8")


def build_runtime(source_dir: Path, runtime_dir: Path, repo_url: str, repo_ref: str) -> None:
    if runtime_dir.exists():
        shutil.rmtree(runtime_dir)
    runtime_dir.mkdir(parents=True)

    venv_dir = runtime_dir / ".venv"
    run([sys.executable, "-m", "venv", str(venv_dir)])
    python_bin = venv_python(venv_dir)

    run([str(python_bin), "-m", "pip", "install", "--upgrade", "pip"])
    run([str(python_bin), "-m", "pip", "install", "-r", str(source_dir / "requirements.txt")])
    run([str(python_bin), "-m", "pip", "install", str(source_dir)])
    run([str(sharp_entrypoint(venv_dir)), "--help"])

    write_launchers(runtime_dir)
    copy_runtime_metadata(source_dir, runtime_dir, repo_url=repo_url, repo_ref=repo_ref)


def main() -> int:
    args = parse_args()
    runtime_dir = Path(args.runtime_dir).expanduser().resolve()
    source_dir, should_cleanup = prepare_source_tree(args)

    try:
        build_runtime(source_dir, runtime_dir, repo_url=args.repo_url, repo_ref=args.repo_ref)
    finally:
        if should_cleanup:
            shutil.rmtree(source_dir.parent, ignore_errors=True)

    print(runtime_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
