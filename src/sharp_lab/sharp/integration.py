from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import subprocess
import time

from sharp_lab.sharp.ply import decimate_ply

LOGGER = logging.getLogger(__name__)


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
        executable_exists = bool(self.executable and self.executable.exists())
        checkpoint_exists = bool(self.checkpoint and self.checkpoint.exists())
        return {
            "executable": str(self.executable) if self.executable else None,
            "checkpoint": str(self.checkpoint) if self.checkpoint else None,
            "executable_exists": executable_exists,
            "checkpoint_exists": checkpoint_exists,
            "default_device": self.default_device,
        }

    def predict(self, input_path: Path, device: str | None = None) -> SharpRunRecord:
        if self.runs_dir is None or self.executable is None:
            raise RuntimeError("SHARP service is not configured for local runs.")
        if not input_path.exists():
            raise FileNotFoundError(f"Input path does not exist: {input_path}")
        if not self.executable.exists():
            raise FileNotFoundError(f"SHARP executable not found: {self.executable}")
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
            str(self.executable),
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
