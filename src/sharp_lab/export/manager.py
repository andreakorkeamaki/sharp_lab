from __future__ import annotations

from pathlib import Path
import json
import logging
import shutil

LOGGER = logging.getLogger(__name__)
SUPPORTED_EXTENSIONS = {".heic", ".jpg", ".jpeg", ".png", ".tif", ".tiff"}


class ExportManager:
    def __init__(self, processed_dir: Path, exports_dir: Path) -> None:
        self.processed_dir = processed_dir
        self.exports_dir = exports_dir

    def create_bundle(self, name: str) -> Path:
        bundle_dir = self.exports_dir / name
        assets_dir = bundle_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)

        copied_files: list[str] = []
        for source_path in sorted(self.processed_dir.iterdir()):
            if not source_path.is_file() or source_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            destination = assets_dir / source_path.name
            shutil.copy2(source_path, destination)
            copied_files.append(destination.name)

        manifest_path = bundle_dir / "export_manifest.json"
        manifest = {
            "bundle_name": name,
            "asset_count": len(copied_files),
            "assets": copied_files,
        }
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        LOGGER.info("Created export bundle %s with %s assets", bundle_dir, len(copied_files))
        return bundle_dir
