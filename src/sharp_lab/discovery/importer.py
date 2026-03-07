from __future__ import annotations

from pathlib import Path
import logging
import shutil

from sharp_lab.models import ImageAsset

LOGGER = logging.getLogger(__name__)
SUPPORTED_EXTENSIONS = {".heic", ".jpg", ".jpeg", ".png", ".tif", ".tiff"}


class ImageDiscoveryService:
    def __init__(self, imports_dir: Path) -> None:
        self.imports_dir = imports_dir

    def discover(self, source_dir: Path) -> list[Path]:
        if not source_dir.exists():
            raise FileNotFoundError(f"Source directory does not exist: {source_dir}")

        files = [
            path for path in sorted(source_dir.rglob("*"))
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
        ]
        LOGGER.info("Discovered %s supported images in %s", len(files), source_dir)
        return files

    def import_from(self, source_dir: Path) -> list[ImageAsset]:
        self.imports_dir.mkdir(parents=True, exist_ok=True)
        imported_assets: list[ImageAsset] = []

        for source_path in self.discover(source_dir):
            destination = self.imports_dir / source_path.name.lower().replace(" ", "_")
            destination = _deduplicate_path(destination)
            shutil.copy2(source_path, destination)
            asset = ImageAsset(source_path=source_path, managed_path=destination)
            imported_assets.append(asset)
            LOGGER.debug("Imported %s -> %s", source_path, destination)

        LOGGER.info("Imported %s images into %s", len(imported_assets), self.imports_dir)
        return imported_assets


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
