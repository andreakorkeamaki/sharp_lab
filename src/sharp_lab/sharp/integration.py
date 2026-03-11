from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

from sharp_lab.downloads import ProgressCallback, download_to_path
from sharp_lab.sharp.ply import decimate_ply

LOGGER = logging.getLogger(__name__)
DEFAULT_MODEL_FILENAME = "sharp_2572gikvuh.pt"
DEFAULT_MODEL_URL = "https://ml-site.cdn-apple.com/models/sharp/sharp_2572gikvuh.pt"
WINDOWS_REPLACE_RETRIES = 10
WINDOWS_REPLACE_DELAY_SECONDS = 0.35


@dataclass
class SharpRunRecord:
    run_id: str
    input_path: str
    output_dir: str
    ply_files: list[str]
    device: str
    command: list[str]
    return_code: int
    status: str
    created_at: str
    duration_seconds: float
    log_path: str
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class SharpDecimationRecord:
    run_id: str
    source_file: str
    output_file: str
    ratio: float
    original_vertices: int
    decimated_vertices: int
    output_path: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class SharpIntegrationService:
    """Boundary for local Apple SHARP execution and run tracking."""

    def __init__(
        self,
        runs_dir: Path | None = None,
        executable: Path | None = None,
        checkpoint: Path | None = None,
        default_device: str = "cpu",
    ) -> None:
        self.runs_dir = runs_dir
        self.executable = executable
        self.checkpoint = checkpoint
        self.default_device = default_device

    def plan_submission(self, bundle_dir: Path) -> dict[str, object]:
        assets_dir = bundle_dir / "assets"
        asset_count = len([path for path in assets_dir.iterdir()]) if assets_dir.exists() else 0
        return {
            "status": "planned",
            "bundle_dir": str(bundle_dir),
            "asset_count": asset_count,
            "next_steps": [
                "Validate export metadata",
                "Attach SHARP-specific annotations",
                "Implement authenticated upload workflow",
            ],
        }

    def installation_status(self) -> dict[str, object]:
        executable_path = self._resolve_executable_path()
        executable_exists = bool(executable_path and executable_path.exists())
        checkpoint_exists = bool(self.checkpoint and self.checkpoint.exists())
        preferred_checkpoint = self.preferred_checkpoint_path()
        can_download_checkpoint = executable_exists and preferred_checkpoint is not None
        model_cache_dir = self.preferred_model_cache_dir()
        checkpoint_mode = "bundled"
        checkpoint_hint = "The bundled SHARP checkpoint is ready."
        runtime_ready = executable_exists
        predict_ready = executable_exists and (checkpoint_exists or self.checkpoint is None)

        if not executable_exists:
            checkpoint_mode = "runtime-missing"
            checkpoint_hint = "Add the SHARP runtime before this app can run predictions."
        elif checkpoint_exists:
            checkpoint_mode = "bundled"
            checkpoint_hint = "The SHARP checkpoint is bundled locally."
        elif self.checkpoint is not None and can_download_checkpoint:
            checkpoint_mode = "download-required"
            checkpoint_hint = "Download the Apple SHARP model into the configured checkpoint path before predicting."
        elif can_download_checkpoint:
            checkpoint_mode = "download-available"
            checkpoint_hint = (
                "Download the Apple SHARP model now, or let the SHARP CLI download it automatically on the first run."
            )
        elif self.checkpoint is None:
            checkpoint_mode = "auto-download"
            checkpoint_hint = (
                "The SHARP CLI will download the model checkpoint automatically on the first prediction run."
            )
        else:
            checkpoint_mode = "configured-missing"
            checkpoint_hint = "The configured checkpoint path does not exist."

        return {
            "executable": str(executable_path) if executable_path else None,
            "checkpoint": str(self.checkpoint) if self.checkpoint else None,
            "preferred_checkpoint": str(preferred_checkpoint) if preferred_checkpoint else None,
            "executable_exists": executable_exists,
            "checkpoint_exists": checkpoint_exists,
            "runtime_ready": runtime_ready,
            "predict_ready": predict_ready,
            "checkpoint_mode": checkpoint_mode,
            "checkpoint_hint": checkpoint_hint,
            "model_cache_dir": str(model_cache_dir),
            "can_download_checkpoint": can_download_checkpoint,
            "default_model_url": DEFAULT_MODEL_URL,
            "default_device": self.default_device,
        }

    def preferred_checkpoint_path(self) -> Path | None:
        if self.checkpoint is not None:
            return self.checkpoint.resolve()
        executable_path = self._resolve_executable_path()
        if executable_path is None:
            return None
        return (executable_path.resolve().parent / "models" / DEFAULT_MODEL_FILENAME).resolve()

    def preferred_model_cache_dir(self) -> Path:
        executable_path = self._resolve_executable_path()
        if executable_path is None:
            return (Path.home() / ".cache" / "torch" / "hub" / "checkpoints").resolve()
        return (executable_path.resolve().parent / ".cache" / "torch" / "hub" / "checkpoints").resolve()

    def download_default_checkpoint(
        self,
        url: str = DEFAULT_MODEL_URL,
        progress_callback: ProgressCallback | None = None,
    ) -> Path:
        executable_path = self._resolve_executable_path()
        if executable_path is None or not executable_path.exists():
            raise RuntimeError("The SHARP runtime is not installed on this machine yet.")

        target_path = self.preferred_checkpoint_path()
        if target_path is None:
            raise RuntimeError("Could not determine where to save the SHARP checkpoint.")

        target_path.parent.mkdir(parents=True, exist_ok=True)
        file_descriptor, temp_name = tempfile.mkstemp(dir=target_path.parent)
        temp_path = Path(temp_name)
        try:
            os.close(file_descriptor)
            download_to_path(url, temp_path, progress_callback=progress_callback)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise

        self._replace_checkpoint_file(temp_path, target_path)
        self.checkpoint = target_path.resolve()
        LOGGER.info("Downloaded SHARP checkpoint to %s", self.checkpoint)
        return self.checkpoint

    def _replace_checkpoint_file(self, source_path: Path, target_path: Path) -> None:
        attempts = WINDOWS_REPLACE_RETRIES if os.name == "nt" else 1
        last_error: OSError | None = None

        for attempt in range(attempts):
            try:
                os.replace(source_path, target_path)
                return
            except OSError as exc:
                last_error = exc
                if os.name != "nt":
                    break
                if attempt == attempts - 1:
                    break
                time.sleep(WINDOWS_REPLACE_DELAY_SECONDS)

        source_path.unlink(missing_ok=True)
        if last_error is not None:
            raise RuntimeError(
                f"Could not save the Apple SHARP model to {target_path}: {last_error}"
            ) from last_error
        raise RuntimeError(f"Could not save the Apple SHARP model to {target_path}.")

    def predict(self, input_path: Path, device: str | None = None) -> SharpRunRecord:
        executable_path = self._resolve_executable_path()
        if self.runs_dir is None or executable_path is None:
            raise RuntimeError("SHARP service is not configured for local runs.")
        if not input_path.exists():
            raise FileNotFoundError(f"Input path does not exist: {input_path}")
        if not executable_path.exists():
            raise FileNotFoundError(f"SHARP executable not found: {executable_path}")
        if self.checkpoint is not None and not self.checkpoint.exists():
            raise FileNotFoundError(f"SHARP checkpoint not found: {self.checkpoint}")

        run_id = self._create_run_id(input_path)
        run_dir = self.runs_dir / run_id
        output_dir = run_dir / "output"
        log_path = run_dir / "sharp.log"
        run_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)

        chosen_device = device or self.default_device
        command = [
            str(executable_path),
            "predict",
            "-i",
            str(input_path),
            "-o",
            str(output_dir),
            "--device",
            chosen_device,
        ]
        if self.checkpoint is not None:
            command.extend(["-c", str(self.checkpoint)])

        LOGGER.info("Running SHARP command: %s", " ".join(command))
        started_at = datetime.now(timezone.utc)
        started = time.perf_counter()
        process = subprocess.run(command, capture_output=True, text=True, check=False)
        duration_seconds = round(time.perf_counter() - started, 3)
        combined_output = process.stdout
        if process.stderr:
            combined_output = f"{combined_output}\n{process.stderr}" if combined_output else process.stderr
        log_path.write_text(combined_output, encoding="utf-8")

        ply_files = sorted(path.name for path in output_dir.glob("*.ply"))
        status = "completed" if process.returncode == 0 and ply_files else "failed"
        error = None if status == "completed" else self._extract_error(process, ply_files)

        record = SharpRunRecord(
            run_id=run_id,
            input_path=str(input_path.resolve()),
            output_dir=str(output_dir.resolve()),
            ply_files=ply_files,
            device=chosen_device,
            command=command,
            return_code=process.returncode,
            status=status,
            created_at=started_at.isoformat(),
            duration_seconds=duration_seconds,
            log_path=str(log_path.resolve()),
            error=error,
        )
        self._write_manifest(run_dir, record)

        if status != "completed":
            raise RuntimeError(error or "SHARP prediction failed.")
        return record

    def _resolve_executable_path(self) -> Path | None:
        if self.executable is None:
            return None
        if self.executable.exists():
            self.executable = self.executable.resolve()
            return self.executable

        parent = self.executable.parent
        if os.name == "nt":
            candidate_names = ("run-sharp.exe", "run-sharp.bat", "run-sharp.cmd")
        else:
            candidate_names = ("run-sharp",)

        for candidate_name in candidate_names:
            candidate = parent / candidate_name
            if candidate.exists():
                self.executable = candidate.resolve()
                return self.executable
        return self.executable

    def list_runs(self) -> list[SharpRunRecord]:
        if self.runs_dir is None or not self.runs_dir.exists():
            return []

        records: list[SharpRunRecord] = []
        for manifest_path in sorted(self.runs_dir.glob("*/run.json"), reverse=True):
            try:
                payload = json.loads(manifest_path.read_text(encoding="utf-8"))
                records.append(SharpRunRecord(**payload))
            except (OSError, json.JSONDecodeError, TypeError) as exc:
                LOGGER.warning("Skipping unreadable run manifest %s: %s", manifest_path, exc)
        return records

    def get_run(self, run_id: str) -> SharpRunRecord:
        if self.runs_dir is None:
            raise RuntimeError("SHARP runs directory is not configured.")

        manifest_path = self.runs_dir / run_id / "run.json"
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise FileNotFoundError(f"Run manifest not found for {run_id}.") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Run manifest is unreadable for {run_id}.") from exc
        return SharpRunRecord(**payload)

    def artifact_path(self, run_id: str, filename: str) -> Path:
        if self.runs_dir is None:
            raise RuntimeError("SHARP runs directory is not configured.")
        candidate = (self.runs_dir / run_id / "output" / filename).resolve()
        output_root = (self.runs_dir / run_id / "output").resolve()
        if output_root not in candidate.parents:
            raise FileNotFoundError("Artifact path escapes the run directory.")
        if not candidate.exists() or not candidate.is_file():
            raise FileNotFoundError(f"Artifact not found: {filename}")
        return candidate

    def decimate_run(
        self,
        run_id: str,
        filename: str,
        ratio: float,
    ) -> tuple[SharpRunRecord, SharpDecimationRecord]:
        run = self.get_run(run_id)
        if filename not in run.ply_files:
            raise FileNotFoundError(f"Run {run_id} does not contain {filename}.")

        source_path = self.artifact_path(run_id, filename)
        ratio_percent = round(ratio * 100, 2)
        ratio_slug = str(int(ratio_percent)) if ratio_percent.is_integer() else str(ratio_percent).replace(".", "-")
        output_name = f"{source_path.stem}-decimated-{ratio_slug}{source_path.suffix}"
        output_path = source_path.with_name(output_name)
        decimated = decimate_ply(source_path, output_path, ratio)

        if output_name not in run.ply_files:
            run.ply_files.append(output_name)
            self._write_manifest(self.runs_dir / run_id, run)

        decimation = SharpDecimationRecord(
            run_id=run_id,
            source_file=filename,
            output_file=output_name,
            ratio=ratio,
            original_vertices=decimated.original_vertices,
            decimated_vertices=decimated.decimated_vertices,
            output_path=str(output_path.resolve()),
        )
        refreshed_run = self.get_run(run_id)
        return refreshed_run, decimation

    def _create_run_id(self, input_path: Path) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        slug = input_path.stem if input_path.is_file() else input_path.name
        safe_slug = "".join(character.lower() if character.isalnum() else "-" for character in slug).strip("-")
        safe_slug = safe_slug or "sharp-run"
        return f"{stamp}-{safe_slug}"

    def _write_manifest(self, run_dir: Path, record: SharpRunRecord) -> None:
        manifest_path = run_dir / "run.json"
        manifest_path.write_text(json.dumps(record.to_dict(), indent=2), encoding="utf-8")

    def _extract_error(self, process: subprocess.CompletedProcess[str], ply_files: list[str]) -> str:
        if process.returncode != 0:
            stderr = process.stderr.strip() if process.stderr else ""
            stdout = process.stdout.strip() if process.stdout else ""
            return stderr or stdout or f"SHARP exited with code {process.returncode}."
        if not ply_files:
            return "SHARP completed without producing any .ply output files."
        return "Unknown SHARP execution failure."
