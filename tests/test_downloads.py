from __future__ import annotations

from pathlib import Path
import ssl
import sys
import tempfile
import time
import unittest
from unittest import mock
from urllib.error import URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sharp_lab.downloads import DownloadTaskManager, download_to_path


class DownloadTests(unittest.TestCase):
    def test_task_manager_tracks_progress_and_completion(self) -> None:
        manager = DownloadTaskManager()

        with tempfile.TemporaryDirectory() as temp_dir:
            target_path = Path(temp_dir) / "download.bin"

            def worker(reporter):
                reporter.download(5, 10)
                time.sleep(0.02)
                target_path.write_bytes(b"payload")
                reporter.status("Finishing install.", 90, "Installing torch (821.6 MB)")
                reporter.download(10, 10)
                return target_path

            manager.start("model", start_message="Starting model download.", worker=worker)

            deadline = time.time() + 1
            snapshot = manager.get("model")
            while snapshot.status == "running" and time.time() < deadline:
                time.sleep(0.01)
                snapshot = manager.get("model")

            self.assertEqual(snapshot.status, "completed")
            self.assertEqual(snapshot.percent, 100.0)
            self.assertEqual(snapshot.result_path, str(target_path))
            self.assertIsNone(snapshot.detail)

    def test_download_to_path_uses_windows_fallback_for_ssl_errors(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "sharp.pt"

            with (
                mock.patch("sharp_lab.downloads._is_windows", return_value=True),
                mock.patch(
                    "sharp_lab.downloads._download_with_urllib",
                    side_effect=ssl.SSLCertVerificationError("certificate verify failed"),
                ),
                mock.patch("sharp_lab.downloads._download_with_windows_fallback") as fallback,
            ):
                def write_payload(url, target, progress_callback=None):
                    target.write_bytes(b"model")
                    if progress_callback is not None:
                        progress_callback(5, 5)

                fallback.side_effect = write_payload
                download_to_path("https://example.invalid/model.pt", destination)

            self.assertTrue(destination.exists())
            self.assertEqual(destination.read_bytes(), b"model")

    def test_download_to_path_does_not_hide_non_ssl_errors(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "sharp.pt"

            with (
                mock.patch("sharp_lab.downloads._is_windows", return_value=True),
                mock.patch(
                    "sharp_lab.downloads._download_with_urllib",
                    side_effect=RuntimeError("connection reset"),
                ),
                mock.patch("sharp_lab.downloads._download_with_windows_fallback") as fallback,
            ):
                with self.assertRaisesRegex(RuntimeError, "connection reset"):
                    download_to_path("https://example.invalid/model.pt", destination)

            fallback.assert_not_called()

    def test_download_to_path_detects_ssl_verification_errors_wrapped_in_url_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "sharp.pt"

            with (
                mock.patch("sharp_lab.downloads._is_windows", return_value=True),
                mock.patch(
                    "sharp_lab.downloads._download_with_urllib",
                    side_effect=URLError(ssl.SSLCertVerificationError("self-signed certificate in certificate chain")),
                ),
                mock.patch("sharp_lab.downloads._download_with_windows_fallback") as fallback,
            ):
                fallback.side_effect = lambda url, target, progress_callback=None: target.write_bytes(b"model")
                download_to_path("https://example.invalid/model.pt", destination)

            fallback.assert_called_once()
            self.assertEqual(destination.read_bytes(), b"model")


if __name__ == "__main__":
    unittest.main()
