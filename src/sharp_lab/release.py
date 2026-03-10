from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import shutil
import tempfile
from urllib.request import urlopen
import zipfile

from sharp_lab.sharp.integration import DEFAULT_MODEL_URL

RELEASE_MANIFEST_FILE = "sharp_lab.release.json"


@dataclass(frozen=True)
class ReleaseManifest:
    build_flavor: str = "full"
    runtime_archive_url: str | None = None
    model_url: str = DEFAULT_MODEL_URL
    studio_path: str = "/studio"
    setup_path: str = "/setup"

    @classmethod
    def load(cls, base_dir: Path) -> "ReleaseManifest":
        manifest_path = base_dir / RELEASE_MANIFEST_FILE
        if not manifest_path.exists():
            return cls()

        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        return cls(
            build_flavor=str(payload.get("build_flavor", "full")).lower(),
            runtime_archive_url=payload.get("runtime_archive_url"),
            model_url=str(payload.get("model_url", DEFAULT_MODEL_URL)),
            studio_path=str(payload.get("studio_path", "/studio")),
            setup_path=str(payload.get("setup_path", "/setup")),
        )

    @property
    def is_lite(self) -> bool:
        return self.build_flavor == "lite"

    @property
    def landing_path(self) -> str:
        return self.setup_path if self.is_lite else self.studio_path

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["landing_path"] = self.landing_path
        payload["can_download_runtime"] = bool(self.runtime_archive_url)
        return payload


class RuntimeInstallService:
    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir.resolve()

    def install_from_url(self, url: str) -> Path:
        runtime_dir = self.root_dir / "runtime"
        staging_dir = self.root_dir / "runtime.installing"

        with tempfile.TemporaryDirectory(dir=self.root_dir) as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            archive_path = temp_dir / "runtime.zip"
            extract_dir = temp_dir / "extract"
            extract_dir.mkdir(parents=True, exist_ok=True)

            with urlopen(url) as response:
                archive_path.write_bytes(response.read())

            with zipfile.ZipFile(archive_path) as archive:
                _safe_extract_zip(archive, extract_dir)

            runtime_source = extract_dir / "runtime"
            if not runtime_source.exists():
                raise RuntimeError("The downloaded runtime archive did not contain a runtime/ folder.")

            if staging_dir.exists():
                shutil.rmtree(staging_dir)
            shutil.copytree(runtime_source, staging_dir)
            if runtime_dir.exists():
                shutil.rmtree(runtime_dir)
            staging_dir.replace(runtime_dir)

        return runtime_dir.resolve()


def _safe_extract_zip(archive: zipfile.ZipFile, destination: Path) -> None:
    destination = destination.resolve()
    for member in archive.infolist():
        member_path = (destination / member.filename).resolve()
        if member_path != destination and destination not in member_path.parents:
            raise RuntimeError(f"Unsafe archive member path: {member.filename}")
    archive.extractall(destination)
