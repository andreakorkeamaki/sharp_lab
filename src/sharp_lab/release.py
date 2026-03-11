from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Callable
import zipfile

from sharp_lab.downloads import ProgressCallback, download_to_path
from sharp_lab.sharp.integration import DEFAULT_MODEL_URL

RELEASE_MANIFEST_FILE = "sharp_lab.release.json"
DEFAULT_NUGET_URL = "https://aka.ms/nugetclidl"
DEFAULT_PYTHON_PACKAGE = "python"
DEFAULT_PYTHON_VERSION = "3.11.9"
DEFAULT_SHARP_REPO_URL = "https://github.com/apple/ml-sharp.git"
DEFAULT_SHARP_REPO_REF = "1eaa046834b81852261262b41b0919f5c1efdd2e"
DEFAULT_SHARP_SOURCE_URL = f"https://github.com/apple/ml-sharp/archive/{DEFAULT_SHARP_REPO_REF}.zip"


@dataclass(frozen=True)
class ReleaseManifest:
    build_flavor: str = "full"
    runtime_install_mode: str = "archive"
    runtime_archive_url: str | None = None
    python_nuget_url: str | None = None
    python_package: str = DEFAULT_PYTHON_PACKAGE
    python_version: str = DEFAULT_PYTHON_VERSION
    sharp_source_url: str = DEFAULT_SHARP_SOURCE_URL
    sharp_repo_url: str = DEFAULT_SHARP_REPO_URL
    sharp_repo_ref: str = DEFAULT_SHARP_REPO_REF
    model_url: str = DEFAULT_MODEL_URL
    studio_path: str = "/studio"
    setup_path: str = "/setup"

    @classmethod
    def load(cls, base_dir: Path) -> "ReleaseManifest":
        manifest_path = base_dir / RELEASE_MANIFEST_FILE
        if not manifest_path.exists():
            return cls()

        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        return cls(
            build_flavor=str(payload.get("build_flavor", "full")).lower(),
            runtime_install_mode=str(payload.get("runtime_install_mode", "archive")).lower(),
            runtime_archive_url=payload.get("runtime_archive_url"),
            python_nuget_url=payload.get("python_nuget_url"),
            python_package=str(payload.get("python_package", DEFAULT_PYTHON_PACKAGE)),
            python_version=str(payload.get("python_version", DEFAULT_PYTHON_VERSION)),
            sharp_source_url=str(payload.get("sharp_source_url", DEFAULT_SHARP_SOURCE_URL)),
            sharp_repo_url=str(payload.get("sharp_repo_url", DEFAULT_SHARP_REPO_URL)),
            sharp_repo_ref=str(payload.get("sharp_repo_ref", DEFAULT_SHARP_REPO_REF)),
            model_url=str(payload.get("model_url", DEFAULT_MODEL_URL)),
            studio_path=str(payload.get("studio_path", "/studio")),
            setup_path=str(payload.get("setup_path", "/setup")),
        )

    @property
    def is_lite(self) -> bool:
        return self.build_flavor == "lite"

    @property
    def landing_path(self) -> str:
        return self.setup_path if self.is_lite else self.studio_path

    @property
    def can_install_runtime(self) -> bool:
        if self.runtime_install_mode == "windows-local":
            return os.name == "nt"
        if self.runtime_install_mode == "archive":
            return bool(self.runtime_archive_url)
        return False

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["landing_path"] = self.landing_path
        payload["can_install_runtime"] = self.can_install_runtime
        payload["can_download_runtime"] = self.can_install_runtime
        return payload


class RuntimeInstallService:
    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir.resolve()

    def install_from_manifest(
        self,
        manifest: ReleaseManifest,
        progress_callback: ProgressCallback | None = None,
        status_callback: Callable[[str, float | None], None] | None = None,
    ) -> Path:
        self.root_dir.mkdir(parents=True, exist_ok=True)
        install_mode = manifest.runtime_install_mode
        if install_mode == "windows-local":
            if os.name != "nt":
                raise RuntimeError("Windows local bootstrap is only available on Windows.")
            return self._install_windows_local(
                manifest,
                progress_callback=progress_callback,
                status_callback=status_callback,
            )
        if install_mode == "archive":
            runtime_archive_url = manifest.runtime_archive_url
            if not runtime_archive_url:
                raise RuntimeError("This build does not declare a runtime download URL.")
            return self.install_from_url(runtime_archive_url, progress_callback=progress_callback)
        raise RuntimeError(f"Unsupported runtime install mode: {install_mode}")

    def install_from_url(self, url: str, progress_callback: ProgressCallback | None = None) -> Path:
        runtime_dir = self.root_dir / "runtime"
        staging_dir = self.root_dir / "runtime.installing"
        self.root_dir.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(dir=self.root_dir) as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            archive_path = temp_dir / "runtime.zip"
            extract_dir = temp_dir / "extract"
            extract_dir.mkdir(parents=True, exist_ok=True)

            download_to_path(url, archive_path, progress_callback=progress_callback)

            with zipfile.ZipFile(archive_path) as archive:
                _safe_extract_zip(archive, extract_dir)

            runtime_source = _find_runtime_dir(extract_dir)

            if staging_dir.exists():
                shutil.rmtree(staging_dir)
            shutil.copytree(runtime_source, staging_dir)
            if runtime_dir.exists():
                shutil.rmtree(runtime_dir)
            staging_dir.replace(runtime_dir)

        return runtime_dir.resolve()

    def _install_windows_local(
        self,
        manifest: ReleaseManifest,
        *,
        progress_callback: ProgressCallback | None = None,
        status_callback: Callable[[str, float | None], None] | None = None,
    ) -> Path:
        runtime_dir = self.root_dir / "runtime"
        staging_dir = self.root_dir / "runtime.installing"
        if staging_dir.exists():
            shutil.rmtree(staging_dir)
        staging_dir.mkdir(parents=True, exist_ok=True)

        try:
            with tempfile.TemporaryDirectory(dir=self.root_dir) as temp_dir_name:
                temp_dir = Path(temp_dir_name)

                self._status(status_callback, "Downloading Python bootstrap tool.", 5)
                nuget_path = temp_dir / "nuget.exe"
                download_to_path(
                    manifest.python_nuget_url or DEFAULT_NUGET_URL,
                    nuget_path,
                    progress_callback=progress_callback,
                )

                self._status(status_callback, "Installing local Python runtime.", 20)
                python_root = temp_dir / "python"
                self._run(
                    [
                        str(nuget_path),
                        "install",
                        manifest.python_package,
                        "-Version",
                        manifest.python_version,
                        "-ExcludeVersion",
                        "-OutputDirectory",
                        str(python_root),
                    ],
                    cwd=temp_dir,
                )

                python_exe = python_root / manifest.python_package / "tools" / "python.exe"
                if not python_exe.exists():
                    raise RuntimeError(f"Python bootstrap did not produce {python_exe}.")

                self._status(status_callback, "Ensuring pip is available.", 35)
                self._run([str(python_exe), "-m", "ensurepip", "--upgrade"], cwd=temp_dir, allow_failure=True)
                self._run([str(python_exe), "-m", "pip", "install", "--upgrade", "pip"], cwd=temp_dir)

                self._status(status_callback, "Downloading pinned Apple SHARP source.", 45)
                source_archive = temp_dir / "ml-sharp.zip"
                download_to_path(manifest.sharp_source_url, source_archive, progress_callback=progress_callback)

                source_dir = temp_dir / "ml-sharp-source"
                source_dir.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(source_archive) as archive:
                    _safe_extract_zip(archive, source_dir)
                sharp_source_root = _find_single_repo_root(source_dir)

                self._status(status_callback, "Installing SHARP dependencies.", 65)
                requirements_path = sharp_source_root / "requirements.txt"
                if requirements_path.exists():
                    self._run(
                        [str(python_exe), "-m", "pip", "install", "-r", str(requirements_path)],
                        cwd=sharp_source_root,
                    )

                self._status(status_callback, "Installing SHARP into the local runtime.", 82)
                self._run([str(python_exe), "-m", "pip", "install", str(sharp_source_root)], cwd=sharp_source_root)

                self._status(status_callback, "Writing local launchers.", 92)
                shutil.copytree(python_root / manifest.python_package, staging_dir / "python", dirs_exist_ok=True)
                _write_local_launchers(staging_dir)
                _copy_runtime_metadata(sharp_source_root, staging_dir, manifest)

                self._status(status_callback, "Validating runtime installation.", 97)
                self._run(["cmd.exe", "/c", str(staging_dir / "run-sharp.cmd"), "--help"], cwd=staging_dir)

                if runtime_dir.exists():
                    shutil.rmtree(runtime_dir)
                staging_dir.replace(runtime_dir)
        except Exception:
            shutil.rmtree(staging_dir, ignore_errors=True)
            raise

        self._status(status_callback, "Runtime installation completed.", 100)
        return runtime_dir.resolve()

    def _run(
        self,
        command: list[str],
        *,
        cwd: Path,
        allow_failure: bool = False,
    ) -> None:
        process = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
        if process.returncode == 0 or allow_failure:
            return
        output = process.stderr.strip() or process.stdout.strip() or f"Command exited with code {process.returncode}."
        raise RuntimeError(output)

    def _status(
        self,
        status_callback: Callable[[str, float | None], None] | None,
        message: str,
        percent: float | None,
    ) -> None:
        if status_callback is not None:
            status_callback(message, percent)


def _safe_extract_zip(archive: zipfile.ZipFile, destination: Path) -> None:
    destination = destination.resolve()
    for member in archive.infolist():
        member_path = (destination / member.filename).resolve()
        if member_path != destination and destination not in member_path.parents:
            raise RuntimeError(f"Unsafe archive member path: {member.filename}")
    archive.extractall(destination)


def _find_runtime_dir(extract_dir: Path) -> Path:
    direct = extract_dir / "runtime"
    if direct.is_dir():
        return direct

    candidates = [path for path in extract_dir.rglob("runtime") if path.is_dir()]
    if not candidates:
        raise RuntimeError("The downloaded runtime archive did not contain a runtime/ folder.")
    if len(candidates) == 1:
        return candidates[0]

    exact_children = [path for path in candidates if path.parent == extract_dir]
    if exact_children:
        return exact_children[0]
    return sorted(candidates, key=lambda path: len(path.parts))[0]


def _find_single_repo_root(extract_dir: Path) -> Path:
    directories = [path for path in extract_dir.iterdir() if path.is_dir()]
    if len(directories) == 1:
        return directories[0]
    if (extract_dir / "requirements.txt").exists():
        return extract_dir
    raise RuntimeError("Could not determine the extracted SHARP source directory.")


def _write_local_launchers(runtime_dir: Path) -> None:
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

    posix_launcher = runtime_dir / "run-sharp"
    posix_launcher.write_text(
        """#!/bin/sh
set -eu

RUNTIME_DIR="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
PYTHON_DIR="$RUNTIME_DIR/python"
export XDG_CACHE_HOME="$RUNTIME_DIR/.cache"
export TORCH_HOME="$RUNTIME_DIR/.cache/torch"
export MPLCONFIGDIR="$RUNTIME_DIR/.cache/matplotlib"

exec "$PYTHON_DIR/tools/python.exe" "$RUNTIME_DIR/sharp_bootstrap.py" "$@"
""",
        encoding="utf-8",
    )
    posix_launcher.chmod(0o755)


def _copy_runtime_metadata(source_dir: Path, runtime_dir: Path, manifest: ReleaseManifest) -> None:
    licenses_dir = runtime_dir / "licenses"
    licenses_dir.mkdir(parents=True, exist_ok=True)
    for filename in ("LICENSE", "LICENSE_MODEL", "ACKNOWLEDGEMENTS", "README.md"):
        source_path = source_dir / filename
        if source_path.exists():
            shutil.copy2(source_path, licenses_dir / filename)

    build_info = {
        "sharp_repo_url": manifest.sharp_repo_url,
        "sharp_repo_ref": manifest.sharp_repo_ref,
        "sharp_source_url": manifest.sharp_source_url,
        "python_package": manifest.python_package,
        "python_version": manifest.python_version,
    }
    (runtime_dir / "build-info.json").write_text(json.dumps(build_info, indent=2), encoding="utf-8")
