from __future__ import annotations

from pathlib import Path

from sharp_lab.config import SharpLabConfig
from sharp_lab.discovery import ImageDiscoveryService
from sharp_lab.export import ExportManager
from sharp_lab.pipeline import PreprocessingPipeline
from sharp_lab.sharp import SharpIntegrationService, SharpRunRecord


class SharpLabApplication:
    """Application facade shared by CLI and future UI adapters."""

    def __init__(self, config: SharpLabConfig) -> None:
        self.config = config
        self.config.ensure_directories()
        self.sharp_service = SharpIntegrationService(
            runs_dir=self.config.paths.runs,
            executable=self.config.sharp.executable,
            checkpoint=self.config.sharp.checkpoint,
            default_device=self.config.sharp.default_device,
        )

    def discover(self, source_dir: Path) -> int:
        imported = ImageDiscoveryService(self.config.paths.imports).import_from(source_dir)
        return len(imported)

    def preprocess(self) -> int:
        result = PreprocessingPipeline(self.config.paths.imports, self.config.paths.processed).run()
        return len(result.processed_assets)

    def export(self, name: str) -> Path:
        return ExportManager(self.config.paths.processed, self.config.paths.exports).create_bundle(name)

    def sharp_plan(self, bundle_dir: Path) -> dict[str, object]:
        return self.sharp_service.plan_submission(bundle_dir)

    def sharp_predict(self, input_path: Path, device: str | None = None) -> SharpRunRecord:
        return self.sharp_service.predict(input_path, device=device)

    def sharp_runs(self) -> list[SharpRunRecord]:
        return self.sharp_service.list_runs()

    def sharp_decimate(
        self,
        run_id: str,
        filename: str,
        ratio: float,
    ) -> tuple[SharpRunRecord, dict[str, object]]:
        run, decimation = self.sharp_service.decimate_run(run_id, filename=filename, ratio=ratio)
        return run, decimation.to_dict()

    def sharp_status(self) -> dict[str, object]:
        return self.sharp_service.installation_status()
