from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ImageAsset:
    source_path: Path
    managed_path: Path


@dataclass(frozen=True)
class ProcessedAsset:
    source_path: Path
    output_path: Path
    step_name: str
