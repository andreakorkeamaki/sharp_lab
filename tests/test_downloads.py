from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sharp_lab.downloads import DownloadTaskManager


class DownloadTests(unittest.TestCase):
    def test_task_manager_tracks_progress_and_completion(self) -> None:
        manager = DownloadTaskManager()

        with tempfile.TemporaryDirectory() as temp_dir:
            target_path = Path(temp_dir) / "download.bin"

            def worker(reporter):
                reporter.download(5, 10)
                time.sleep(0.02)
                target_path.write_bytes(b"payload")
                reporter.status("Finishing install.", 90)
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


if __name__ == "__main__":
    unittest.main()
