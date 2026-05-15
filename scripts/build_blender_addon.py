from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import zipfile


ROOT = Path(__file__).resolve().parents[1]
ADDON_SOURCE_DIR = ROOT / "blender_addon" / "sharp_lab_blender"
PACKAGE_SOURCE_DIR = ROOT / "src" / "sharp_lab"
BUILD_ROOT = ROOT / "build" / "blender_addon"
DIST_PATH = ROOT / "dist" / "sharp-lab-blender-addon.zip"
ADDON_PACKAGE_NAME = "sharp_lab_blender"
IGNORE_PATTERNS = shutil.ignore_patterns("__pycache__", "*.pyc")
DEFAULT_ML_SHARP_SOURCE_DIR = Path.home() / "Desktop" / "ml-sharp"
DEFAULT_ML_SHARP_VENV_DIR = Path.home() / "Desktop" / ".venvs" / "ml-sharp"
MODEL_FILENAMES = {"sharp_2572gikvuh.pt", "sharp.pt"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the macOS/Linux Blender add-on bundle.")
    parser.add_argument(
        "--runtime-dir",
        help="Portable runtime directory to bundle into the add-on. Defaults to the local ml-sharp template.",
    )
    parser.add_argument(
        "--output",
        help=f"Output zip path. Defaults to {DIST_PATH}.",
    )
    parser.add_argument(
        "--no-runtime-template",
        action="store_true",
        help="Build a lightweight add-on that downloads/prepares the runtime during setup.",
    )
    return parser.parse_args()


def _reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def _remove_bundled_models(destination: Path) -> None:
    for model_filename in MODEL_FILENAMES:
        bundled_model = destination / "models" / model_filename
        if bundled_model.exists():
            bundled_model.unlink()


def _copy_runtime_from_directory(source_dir: Path, destination: Path) -> None:
    if not source_dir.exists():
        raise RuntimeError(f"Runtime directory not found: {source_dir}")

    shutil.copytree(source_dir, destination, ignore=IGNORE_PATTERNS)
    _remove_bundled_models(destination)


def _copy_runtime_from_local_template(destination: Path) -> None:
    source_dir = DEFAULT_ML_SHARP_SOURCE_DIR
    venv_dir = DEFAULT_ML_SHARP_VENV_DIR
    if not source_dir.exists():
        raise RuntimeError(f"Local ml-sharp source not found: {source_dir}")
    if not venv_dir.exists():
        raise RuntimeError(f"Local ml-sharp virtualenv not found: {venv_dir}")

    destination.mkdir(parents=True, exist_ok=True)
    shutil.copytree(venv_dir, destination / ".venv", ignore=IGNORE_PATTERNS)

    models_dir = destination / "models"
    models_dir.mkdir(parents=True, exist_ok=True)

    bootstrap = destination / "sharp_bootstrap.py"
    bootstrap.write_text(
        """from sharp.cli import main_cli

if __name__ == "__main__":
    main_cli()
""",
        encoding="utf-8",
    )

    posix_launcher = destination / "run-sharp"
    posix_launcher.write_text(
        """#!/bin/sh
set -eu

RUNTIME_DIR="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
VENV_DIR="$RUNTIME_DIR/.venv"
export XDG_CACHE_HOME="$RUNTIME_DIR/.cache"
export TORCH_HOME="$RUNTIME_DIR/.cache/torch"
export MPLCONFIGDIR="$RUNTIME_DIR/.cache/matplotlib"

exec "$VENV_DIR/bin/python" "$RUNTIME_DIR/sharp_bootstrap.py" "$@"
""",
        encoding="utf-8",
    )
    posix_launcher.chmod(0o755)

    windows_launcher = destination / "run-sharp.cmd"
    windows_launcher.write_text(
        """@echo off
setlocal
set "RUNTIME_DIR=%~dp0"
if "%RUNTIME_DIR:~-1%"=="\\" set "RUNTIME_DIR=%RUNTIME_DIR:~0,-1%"
set "VENV_DIR=%RUNTIME_DIR%\\.venv"
set "XDG_CACHE_HOME=%RUNTIME_DIR%\\.cache"
set "TORCH_HOME=%RUNTIME_DIR%\\.cache\\torch"
set "MPLCONFIGDIR=%RUNTIME_DIR%\\.cache\\matplotlib"

"%VENV_DIR%\\Scripts\\python.exe" "%RUNTIME_DIR%\\sharp_bootstrap.py" %*
""",
        encoding="utf-8",
    )

    licenses_dir = destination / "licenses"
    licenses_dir.mkdir(parents=True, exist_ok=True)
    for filename in ("LICENSE", "LICENSE_MODEL", "ACKNOWLEDGEMENTS", "README.md"):
        source_path = source_dir / filename
        if source_path.exists():
            shutil.copy2(source_path, licenses_dir / filename)

    _remove_bundled_models(destination)


def build(
    *,
    runtime_dir: Path | None = None,
    output_path: Path = DIST_PATH,
    include_runtime_template: bool = True,
) -> Path:
    staging_root = BUILD_ROOT / ADDON_PACKAGE_NAME
    package_root = BUILD_ROOT / "sharp_lab"
    runtime_root = staging_root / "runtime_template"

    _reset_dir(BUILD_ROOT)
    shutil.copytree(ADDON_SOURCE_DIR, staging_root, ignore=IGNORE_PATTERNS)
    shutil.copytree(PACKAGE_SOURCE_DIR, package_root, ignore=IGNORE_PATTERNS)
    if include_runtime_template:
        if runtime_dir is not None:
            _copy_runtime_from_directory(runtime_dir, runtime_root)
        else:
            _copy_runtime_from_local_template(runtime_root)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()

    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(BUILD_ROOT.rglob("*")):
            if path.is_dir():
                continue
            if "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            archive.write(path, path.relative_to(BUILD_ROOT))

    return output_path


if __name__ == "__main__":
    args = parse_args()
    runtime_dir = Path(args.runtime_dir).expanduser().resolve() if args.runtime_dir else None
    output_path = Path(args.output).expanduser().resolve() if args.output else DIST_PATH
    archive_path = build(
        runtime_dir=runtime_dir,
        output_path=output_path,
        include_runtime_template=not args.no_runtime_template,
    )
    print(f"Built Blender add-on: {archive_path}")
