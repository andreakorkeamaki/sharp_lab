from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import logging
import shutil

from sharp_lab.models import ProcessedAsset

LOGGER = logging.getLogger(__name__)
SUPPORTED_EXTENSIONS = {".heic", ".jpg", ".jpeg", ".png", ".tif", ".tiff"}


class PipelineStep:
    name = "base"

    def run(self, source_path: Path, output_dir: Path) -> ProcessedAsset:
        raise NotImplementedError


class CopyNormalizeStep(PipelineStep):
    name = "copy-normalize"

    def run(self, source_path: Path, output_dir: Path) -> ProcessedAsset:
        sanitized_name = source_path.name.lower().replace(" ", "_")
        destination = output_dir / sanitized_name
        destination = _deduplicate_path(destination)
        shutil.copy2(source_path, destination)
        return ProcessedAsset(source_path=source_path, output_path=destination, step_name=self.name)


@dataclass
class PipelineRunResult:
    processed_assets: list[ProcessedAsset]
    manifest_path: Path


class PreprocessingPipeline:
    def __init__(self, imports_dir: Path, processed_dir: Path, steps: list[PipelineStep] | None = None) -> None:
        self.imports_dir = imports_dir
        self.processed_dir = processed_dir
        self.steps = steps or [CopyNormalizeStep()]

    def run(self) -> PipelineRunResult:
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        processed_assets: list[ProcessedAsset] = []

        inputs = [
            path for path in sorted(self.imports_dir.iterdir())
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
        ]
        LOGGER.info("Running preprocessing pipeline for %s images", len(inputs))

        for source_path in inputs:
            current_source = source_path
            last_asset: ProcessedAsset | None = None
            for step in self.steps:
                last_asset = step.run(current_source, self.processed_dir)
                current_source = last_asset.output_path
            if last_asset is not None:
                processed_assets.append(last_asset)

        manifest_path = self.processed_dir / "manifest.json"
        manifest = {
            "asset_count": len(processed_assets),
            "assets": [
                {
                    "source_path": str(asset.source_path),
                    "output_path": str(asset.output_path),
                    "step": asset.step_name,
                }
                for asset in processed_assets
            ],
        }
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        LOGGER.info("Wrote preprocessing manifest to %s", manifest_path)
        return PipelineRunResult(processed_assets=processed_assets, manifest_path=manifest_path)


def _deduplicate_path(path: Path) -> Path:
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    counter = 1
    while True:
        candidate = path.with_name(f"{stem}_{counter}{suffix}")
        if not candidate.exists():
            return candidate
        counter += 1
