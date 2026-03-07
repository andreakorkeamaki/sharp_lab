from __future__ import annotations

from pathlib import Path

from sharp_lab.config import SharpLabConfig
from sharp_lab.discovery import ImageDiscoveryService
from sharp_lab.export import ExportManager
from sharp_lab.pipeline import PreprocessingPipeline
from sharp_lab.sharp import SharpIntegrationService


class SharpLabApplication:
    """Application facade shared by the CLI and future UI adapters."""

    def __init__(self, config: SharpLabConfig) -> None:
        self.config = config
        self.config.ensure_directories()

    def discover(self, source_dir: Path) -> int:
        imported = ImageDiscoveryService(self.config.paths.imports).import_from(source_dir)
        return len(imported)

    def preprocess(self) -> int:
        result = PreprocessingPipeline(self.config.paths.imports, self.config.paths.processed).run()
        return len(result.processed_assets)

    def export(self, name: str) -> Path:
        return ExportManager(self.config.paths.processed, self.config.paths.exports).create_bundle(name)

    def sharp_plan(self, bundle_dir: Path) -> dict[str, object]:
        return SharpIntegrationService().plan_submission(bundle_dir)
