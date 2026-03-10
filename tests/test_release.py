from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sharp_lab.release import RELEASE_MANIFEST_FILE, ReleaseManifest, RuntimeInstallService


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
            self.assertTrue(manifest.to_dict()["can_download_runtime"])

    def test_runtime_install_service_extracts_runtime_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive_bytes = io.BytesIO()
            with zipfile.ZipFile(archive_bytes, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("runtime/run-sharp.cmd", "@echo off\r\n")
                archive.writestr("runtime/models/.keep", "")

            archive_bytes.seek(0)
            service = RuntimeInstallService(root)

            with mock.patch("sharp_lab.release.urlopen", return_value=archive_bytes):
                runtime_path = service.install_from_url("https://example.com/runtime.zip")

            self.assertEqual(runtime_path, (root / "runtime").resolve())
            self.assertTrue((root / "runtime" / "run-sharp.cmd").exists())


if __name__ == "__main__":
    unittest.main()
