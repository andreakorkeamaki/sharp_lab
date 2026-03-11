from __future__ import annotations

import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sharp_lab.release import RELEASE_MANIFEST_FILE, ReleaseManifest, RuntimeInstallService, _parse_install_output_line


class FakeDownloadResponse(io.BytesIO):
    def __init__(self, payload: bytes) -> None:
        super().__init__(payload)
        self.headers = {"Content-Length": str(len(payload))}

    def __enter__(self) -> "FakeDownloadResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


class ReleaseTests(unittest.TestCase):
    def test_load_release_manifest_defaults_to_full(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest = ReleaseManifest.load(Path(temp_dir))

            self.assertEqual(manifest.build_flavor, "full")
            self.assertFalse(manifest.is_lite)
            self.assertEqual(manifest.landing_path, "/studio")
            self.assertFalse(manifest.to_dict()["can_download_runtime"])

    def test_load_release_manifest_reads_lite_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / RELEASE_MANIFEST_FILE).write_text(
                json.dumps(
                    {
                        "build_flavor": "lite",
                        "runtime_archive_url": "https://example.com/runtime.zip",
                        "studio_path": "/studio",
                        "setup_path": "/setup",
                    }
                ),
                encoding="utf-8",
            )

            manifest = ReleaseManifest.load(root)

            self.assertTrue(manifest.is_lite)
            self.assertEqual(manifest.landing_path, "/setup")
            self.assertEqual(manifest.runtime_install_mode, "archive")
            self.assertEqual(manifest.to_dict()["can_install_runtime"], bool(manifest.runtime_archive_url))

    def test_load_release_manifest_reads_windows_local_bootstrap_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / RELEASE_MANIFEST_FILE).write_text(
                json.dumps(
                    {
                        "build_flavor": "lite",
                        "runtime_install_mode": "windows-local",
                        "python_nuget_url": "https://aka.ms/nugetclidl",
                        "python_package": "python",
                        "python_version": "3.11.9",
                    }
                ),
                encoding="utf-8",
            )

            manifest = ReleaseManifest.load(root)

            self.assertEqual(manifest.runtime_install_mode, "windows-local")
            self.assertEqual(manifest.python_package, "python")
            self.assertEqual(manifest.python_version, "3.11.9")
            self.assertEqual(manifest.to_dict()["can_install_runtime"], os.name == "nt")

    def test_runtime_install_service_extracts_runtime_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive_bytes = io.BytesIO()
            with zipfile.ZipFile(archive_bytes, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("runtime/run-sharp.cmd", "@echo off\r\n")
                archive.writestr("runtime/models/.keep", "")

            archive_bytes.seek(0)
            service = RuntimeInstallService(root)

            with mock.patch(
                "sharp_lab.downloads.urlopen",
                return_value=FakeDownloadResponse(archive_bytes.getvalue()),
            ):
                runtime_path = service.install_from_url("https://example.com/runtime.zip")

            self.assertEqual(runtime_path, (root / "runtime").resolve())
            self.assertTrue((root / "runtime" / "run-sharp.cmd").exists())

    def test_runtime_install_service_accepts_nested_runtime_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive_bytes = io.BytesIO()
            with zipfile.ZipFile(archive_bytes, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("sharp-lab-runtime-windows-v0.1.3/runtime/run-sharp.cmd", "@echo off\r\n")
                archive.writestr("sharp-lab-runtime-windows-v0.1.3/runtime/models/.keep", "")

            archive_bytes.seek(0)
            service = RuntimeInstallService(root)

            with mock.patch(
                "sharp_lab.downloads.urlopen",
                return_value=FakeDownloadResponse(archive_bytes.getvalue()),
            ):
                runtime_path = service.install_from_url("https://example.com/runtime.zip")

            self.assertEqual(runtime_path, (root / "runtime").resolve())
            self.assertTrue((root / "runtime" / "run-sharp.cmd").exists())

    def test_runtime_install_service_bootstraps_windows_runtime_locally(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            service = RuntimeInstallService(root)
            manifest = ReleaseManifest(
                build_flavor="lite",
                runtime_install_mode="windows-local",
                python_nuget_url="https://aka.ms/nugetclidl",
                python_package="python",
                python_version="3.11.9",
                sharp_source_url="https://example.com/ml-sharp.zip",
                sharp_repo_ref="abc123",
            )

            source_archive = io.BytesIO()
            with zipfile.ZipFile(source_archive, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("ml-sharp-abc123/requirements.txt", "numpy\n")
                archive.writestr("ml-sharp-abc123/LICENSE", "license\n")
                archive.writestr("ml-sharp-abc123/README.md", "readme\n")
            source_archive.seek(0)

            def fake_run(command, cwd=None, capture_output=True, text=True, check=False):
                if "nuget.exe" in command[0]:
                    output_dir = Path(command[command.index("-OutputDirectory") + 1])
                    python_exe = output_dir / "python" / "tools" / "python.exe"
                    python_exe.parent.mkdir(parents=True, exist_ok=True)
                    python_exe.write_text("", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

            with mock.patch(
                "sharp_lab.downloads.urlopen",
                side_effect=[
                    FakeDownloadResponse(b"nuget-binary"),
                    FakeDownloadResponse(source_archive.getvalue()),
                ],
            ):
                with mock.patch("sharp_lab.release.subprocess.run", side_effect=fake_run):
                    runtime_path = service._install_windows_local(manifest)

            self.assertEqual(runtime_path, (root / "runtime").resolve())
            self.assertTrue((runtime_path / "python" / "tools" / "python.exe").exists())
            self.assertTrue((runtime_path / "run-sharp.cmd").exists())
            self.assertTrue((runtime_path / "sharp_bootstrap.py").exists())
            build_info = json.loads((runtime_path / "build-info.json").read_text(encoding="utf-8"))
            self.assertEqual(build_info["sharp_repo_ref"], "abc123")

    def test_parse_install_output_line_keeps_download_sizes(self) -> None:
        detail = _parse_install_output_line("Downloading torch-2.8.0-cp311.whl (821.6 MB)")
        self.assertEqual(detail, "Downloading torch-2.8.0-cp311.whl (821.6 MB)")

    def test_parse_install_output_line_ignores_noise(self) -> None:
        detail = _parse_install_output_line("   ")
        self.assertIsNone(detail)


if __name__ == "__main__":
    unittest.main()
