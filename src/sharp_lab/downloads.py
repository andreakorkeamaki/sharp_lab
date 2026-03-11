from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
import threading
from typing import Callable
from urllib.request import urlopen

CHUNK_SIZE = 1024 * 1024

ProgressCallback = Callable[[int, int | None], None]


def download_to_path(url: str, destination: Path, progress_callback: ProgressCallback | None = None) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
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


@dataclass
class DownloadTaskSnapshot:
    kind: str
    status: str
    message: str
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

    def status(self, message: str, percent: float | None = None) -> None:
        self._manager._update_status(self._kind, message, percent)


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

    def _update_status(self, kind: str, message: str, percent: float | None = None) -> None:
        with self._lock:
            task = self._tasks.get(kind)
            if task is None:
                return
            task.message = message
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
            task.error = error
            task.result_path = result_path
            task.finished_at = datetime.now(timezone.utc).isoformat()
            if task.total_bytes and task.bytes_downloaded:
                task.percent = round(task.bytes_downloaded / task.total_bytes * 100, 1)
