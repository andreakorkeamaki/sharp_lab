from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import threading
from typing import Callable
from urllib.error import URLError
from urllib.request import urlopen

CHUNK_SIZE = 1024 * 1024

ProgressCallback = Callable[[int, int | None], None]


def download_to_path(url: str, destination: Path, progress_callback: ProgressCallback | None = None) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        _download_with_urllib(url, destination, progress_callback=progress_callback)
        return
    except Exception as exc:
        destination.unlink(missing_ok=True)
        if not _is_windows() or not _is_ssl_verification_error(exc):
            raise

    _download_with_windows_fallback(url, destination, progress_callback=progress_callback)


def _download_with_urllib(url: str, destination: Path, progress_callback: ProgressCallback | None = None) -> None:
    with destination.open("wb") as handle:
        with urlopen(url) as response:
            total_header = response.headers.get("Content-Length")
            total_bytes = int(total_header) if total_header and total_header.isdigit() else None
            downloaded = 0

            while True:
                chunk = response.read(CHUNK_SIZE)
                if not chunk:
                    break
                handle.write(chunk)
                downloaded += len(chunk)
                if progress_callback is not None:
                    progress_callback(downloaded, total_bytes)

            if progress_callback is not None:
                progress_callback(downloaded, total_bytes)


def _is_windows() -> bool:
    return os.name == "nt"


def _is_ssl_verification_error(exc: Exception) -> bool:
    visited: set[int] = set()
    current: BaseException | None = exc

    while current is not None and id(current) not in visited:
        visited.add(id(current))
        if isinstance(current, ssl.SSLCertVerificationError):
            return True
        if isinstance(current, URLError) and isinstance(current.reason, ssl.SSLCertVerificationError):
            return True

        message = str(current).lower()
        if "certificate verify failed" in message or "self-signed certificate in certificate chain" in message:
            return True

        if isinstance(current, URLError) and isinstance(current.reason, BaseException):
            current = current.reason
            continue
        current = current.__cause__ or current.__context__

    return False


def _download_with_windows_fallback(
    url: str,
    destination: Path,
    progress_callback: ProgressCallback | None = None,
) -> None:
    errors: list[str] = []

    if progress_callback is not None:
        progress_callback(0, None)

    try:
        _download_with_curl(url, destination, progress_callback=progress_callback)
        return
    except Exception as exc:
        destination.unlink(missing_ok=True)
        errors.append(str(exc))

    try:
        _download_with_powershell(url, destination, progress_callback=progress_callback)
        return
    except Exception as exc:
        destination.unlink(missing_ok=True)
        errors.append(str(exc))

    error_summary = "; ".join(error for error in errors if error) or "No Windows downloader succeeded."
    raise RuntimeError(
        "Python could not verify the model download certificate, and the Windows download fallback failed. "
        f"{error_summary}"
    )


def _download_with_curl(url: str, destination: Path, progress_callback: ProgressCallback | None = None) -> None:
    curl = shutil.which("curl.exe") or shutil.which("curl")
    if curl is None:
        raise RuntimeError("curl.exe is not available on this Windows machine.")

    result = subprocess.run(
        [curl, "--fail", "--location", "--silent", "--show-error", "--output", str(destination), url],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "curl.exe failed to download the file.")

    if progress_callback is not None:
        downloaded = destination.stat().st_size if destination.exists() else 0
        progress_callback(downloaded, downloaded if downloaded else None)


def _download_with_powershell(url: str, destination: Path, progress_callback: ProgressCallback | None = None) -> None:
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if powershell is None:
        raise RuntimeError("PowerShell is not available on this Windows machine.")

    result = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            (
                "$ProgressPreference = 'SilentlyContinue'; "
                f"Invoke-WebRequest -Uri '{_powershell_escape(url)}' -OutFile '{_powershell_escape(str(destination))}'"
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "PowerShell failed to download the file.")

    if progress_callback is not None:
        downloaded = destination.stat().st_size if destination.exists() else 0
        progress_callback(downloaded, downloaded if downloaded else None)


def _powershell_escape(value: str) -> str:
    return value.replace("'", "''")


@dataclass
class DownloadTaskSnapshot:
    kind: str
    status: str
    message: str
    detail: str | None = None
    bytes_downloaded: int = 0
    total_bytes: int | None = None
    percent: float | None = None
    error: str | None = None
    result_path: str | None = None
    started_at: str | None = None
    finished_at: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class TaskReporter:
    def __init__(self, manager: "DownloadTaskManager", kind: str) -> None:
        self._manager = manager
        self._kind = kind

    def download(self, downloaded: int, total: int | None) -> None:
        self._manager._update_progress(self._kind, downloaded, total)

    def status(self, message: str, percent: float | None = None, detail: str | None = None) -> None:
        self._manager._update_status(self._kind, message, percent, detail)


class DownloadTaskManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tasks: dict[str, DownloadTaskSnapshot] = {}

    def get(self, kind: str) -> DownloadTaskSnapshot:
        with self._lock:
            task = self._tasks.get(kind)
            if task is None:
                return DownloadTaskSnapshot(kind=kind, status="idle", message="No download started yet.")
            return DownloadTaskSnapshot(**task.to_dict())

    def start(
        self,
        kind: str,
        *,
        start_message: str,
        worker: Callable[[TaskReporter], Path],
    ) -> DownloadTaskSnapshot:
        with self._lock:
            existing = self._tasks.get(kind)
            if existing is not None and existing.status == "running":
                return DownloadTaskSnapshot(**existing.to_dict())

            task = DownloadTaskSnapshot(
                kind=kind,
                status="running",
                message=start_message,
                started_at=datetime.now(timezone.utc).isoformat(),
            )
            self._tasks[kind] = task

        thread = threading.Thread(target=self._run, args=(kind, worker), daemon=True)
        thread.start()
        return DownloadTaskSnapshot(**task.to_dict())

    def _run(self, kind: str, worker: Callable[[TaskReporter], Path]) -> None:
        reporter = TaskReporter(self, kind)
        try:
            result_path = worker(reporter)
        except Exception as exc:
            self._finish(kind, status="failed", message=str(exc), error=str(exc))
            return

        self._finish(kind, status="completed", message="Download completed.", result_path=str(result_path))

    def _update_progress(self, kind: str, downloaded: int, total: int | None) -> None:
        with self._lock:
            task = self._tasks.get(kind)
            if task is None:
                return
            task.bytes_downloaded = downloaded
            task.total_bytes = total
            task.percent = round(downloaded / total * 100, 1) if total else None
            if total:
                task.message = f"Downloaded {downloaded:,} of {total:,} bytes."
            else:
                task.message = f"Downloaded {downloaded:,} bytes."

    def _update_status(
        self,
        kind: str,
        message: str,
        percent: float | None = None,
        detail: str | None = None,
    ) -> None:
        with self._lock:
            task = self._tasks.get(kind)
            if task is None:
                return
            task.message = message
            task.detail = detail
            task.bytes_downloaded = 0
            task.total_bytes = None
            if percent is not None:
                task.percent = percent

    def _finish(
        self,
        kind: str,
        *,
        status: str,
        message: str,
        error: str | None = None,
        result_path: str | None = None,
    ) -> None:
        with self._lock:
            task = self._tasks.get(kind)
            if task is None:
                return
            task.status = status
            task.message = message
            if status != "running":
                task.detail = None
            task.error = error
            task.result_path = result_path
            task.finished_at = datetime.now(timezone.utc).isoformat()
            if task.total_bytes and task.bytes_downloaded:
                task.percent = round(task.bytes_downloaded / task.total_bytes * 100, 1)
