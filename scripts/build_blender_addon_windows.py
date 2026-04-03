from __future__ import annotations

from pathlib import Path
import argparse
import json
import shutil
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
ADDON_SOURCE_DIR = ROOT / "blender_addon" / "sharp_lab_blender"
PACKAGE_SOURCE_DIR = ROOT / "src" / "sharp_lab"
WINDOWS_RUNTIME_ARCHIVE = ROOT / "dist" / "sharp-lab-runtime-windows-v0.1.7.zip"
WINDOWS_PYTHON_NUPKG = ROOT / "dist" / "python.3.11.9.nupkg"
BUILD_ROOT = ROOT / "build" / "blender_addon_windows"
DIST_PATH = ROOT / "dist" / "sharp-lab-blender-addon-windows.zip"
ADDON_PACKAGE_NAME = "sharp_lab_blender"
IGNORE_PATTERNS = shutil.ignore_patterns("__pycache__", "*.pyc")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the Windows Blender add-on bundle.")
    parser.add_argument(
        "--runtime-dir",
        help="Runtime directory produced by scripts/build_ml_sharp_runtime.py.",
    )
    parser.add_argument(
        "--runtime-archive",
        help=f"Prebuilt Windows runtime archive. Defaults to {WINDOWS_RUNTIME_ARCHIVE}.",
    )
    parser.add_argument(
        "--python-nupkg",
        help=f"Portable Python NuGet package. Defaults to {WINDOWS_PYTHON_NUPKG}.",
    )
    parser.add_argument(
        "--output",
        help=f"Output zip path. Defaults to {DIST_PATH}.",
    )
    return parser.parse_args()


def _reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def _safe_extract_zip(archive_path: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive_path) as archive:
        destination = destination.resolve()
        for member in archive.infolist():
            target = (destination / member.filename).resolve()
            if target != destination and destination not in target.parents:
                raise RuntimeError(f"Unsafe archive member path: {member.filename}")
        archive.extractall(destination)


def _copy_site_packages(source_runtime_dir: Path, destination_python_dir: Path) -> None:
    source_site_packages = source_runtime_dir / ".venv" / "Lib" / "site-packages"
    destination_site_packages = destination_python_dir / "tools" / "Lib" / "site-packages"
    if not source_site_packages.exists():
        raise RuntimeError(f"Missing source site-packages: {source_site_packages}")

    if destination_site_packages.exists():
        shutil.rmtree(destination_site_packages)
    shutil.copytree(source_site_packages, destination_site_packages, ignore=IGNORE_PATTERNS)

    editable_pth = destination_site_packages / "__editable__.sharp_lab-0.1.7.pth"
    if editable_pth.exists():
        editable_pth.unlink()


def _write_windows_launchers(runtime_dir: Path) -> None:
    bootstrap = runtime_dir / "sharp_bootstrap.py"
    bootstrap.write_text(
        """from sharp.cli import main_cli

if __name__ == "__main__":
    main_cli()
""",
        encoding="utf-8",
    )

    windows_launcher = runtime_dir / "run-sharp.cmd"
    windows_launcher.write_text(
        """@echo off
setlocal
set "RUNTIME_DIR=%~dp0"
if "%RUNTIME_DIR:~-1%"=="\\" set "RUNTIME_DIR=%RUNTIME_DIR:~0,-1%"
set "PYTHON_DIR=%RUNTIME_DIR%\\python"
set "XDG_CACHE_HOME=%RUNTIME_DIR%\\.cache"
set "TORCH_HOME=%RUNTIME_DIR%\\.cache\\torch"
set "MPLCONFIGDIR=%RUNTIME_DIR%\\.cache\\matplotlib"

"%PYTHON_DIR%\\tools\\python.exe" "%RUNTIME_DIR%\\sharp_bootstrap.py" %*
""",
        encoding="utf-8",
    )


def _copy_runtime_metadata(source_runtime_dir: Path, destination_runtime_dir: Path) -> None:
    for filename in ("build-info.json",):
        source_path = source_runtime_dir / filename
        if source_path.exists():
            payload = json.loads(source_path.read_text(encoding="utf-8"))
            payload["portable_python_layout"] = "nuget-tools"
            (destination_runtime_dir / filename).write_text(json.dumps(payload, indent=2), encoding="utf-8")

    source_licenses = source_runtime_dir / "licenses"
    destination_licenses = destination_runtime_dir / "licenses"
    if source_licenses.exists():
        shutil.copytree(source_licenses, destination_licenses, ignore=IGNORE_PATTERNS)

    (destination_runtime_dir / "models").mkdir(parents=True, exist_ok=True)


def build_portable_runtime(
    destination_runtime_dir: Path,
    *,
    runtime_source_dir: Path | None = None,
    runtime_archive_path: Path = WINDOWS_RUNTIME_ARCHIVE,
    python_nupkg_path: Path = WINDOWS_PYTHON_NUPKG,
) -> None:
    if runtime_source_dir is None:
        if not runtime_archive_path.exists():
            raise RuntimeError(f"Missing Windows runtime archive: {runtime_archive_path}")
    elif not runtime_source_dir.exists():
        raise RuntimeError(f"Missing Windows runtime directory: {runtime_source_dir}")
    if not python_nupkg_path.exists():
        raise RuntimeError(f"Missing Windows Python package: {python_nupkg_path}")

    with tempfile.TemporaryDirectory(dir=BUILD_ROOT) as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        extracted_runtime_root = temp_dir / "runtime_source"
        extracted_python_root = temp_dir / "python_nupkg"
        if runtime_source_dir is not None:
            shutil.copytree(runtime_source_dir, extracted_runtime_root)
        else:
            _safe_extract_zip(runtime_archive_path, extracted_runtime_root)
        _safe_extract_zip(python_nupkg_path, extracted_python_root)

        source_runtime_dir = extracted_runtime_root / "runtime" if (extracted_runtime_root / "runtime").exists() else extracted_runtime_root
        if not source_runtime_dir.exists():
            raise RuntimeError("The Windows runtime archive does not contain a runtime/ directory.")

        destination_runtime_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(extracted_python_root, destination_runtime_dir / "python", ignore=IGNORE_PATTERNS)
        _copy_site_packages(source_runtime_dir, destination_runtime_dir / "python")
        _write_windows_launchers(destination_runtime_dir)
        _copy_runtime_metadata(source_runtime_dir, destination_runtime_dir)


def build(
    *,
    runtime_source_dir: Path | None = None,
    runtime_archive_path: Path = WINDOWS_RUNTIME_ARCHIVE,
    python_nupkg_path: Path = WINDOWS_PYTHON_NUPKG,
    output_path: Path = DIST_PATH,
) -> Path:
    staging_root = BUILD_ROOT / ADDON_PACKAGE_NAME
    package_root = BUILD_ROOT / "sharp_lab"
    runtime_root = staging_root / "runtime_template"

    _reset_dir(BUILD_ROOT)
    shutil.copytree(ADDON_SOURCE_DIR, staging_root, ignore=IGNORE_PATTERNS)
    shutil.copytree(PACKAGE_SOURCE_DIR, package_root, ignore=IGNORE_PATTERNS)
    build_portable_runtime(
        runtime_root,
        runtime_source_dir=runtime_source_dir,
        runtime_archive_path=runtime_archive_path,
        python_nupkg_path=python_nupkg_path,
    )

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
    runtime_source_dir = Path(args.runtime_dir).expanduser().resolve() if args.runtime_dir else None
    runtime_archive_path = Path(args.runtime_archive).expanduser().resolve() if args.runtime_archive else WINDOWS_RUNTIME_ARCHIVE
    python_nupkg_path = Path(args.python_nupkg).expanduser().resolve() if args.python_nupkg else WINDOWS_PYTHON_NUPKG
    output_path = Path(args.output).expanduser().resolve() if args.output else DIST_PATH
    archive_path = build(
        runtime_source_dir=runtime_source_dir,
        runtime_archive_path=runtime_archive_path,
        python_nupkg_path=python_nupkg_path,
        output_path=output_path,
    )
    print(f"Built Windows Blender add-on: {archive_path}")
