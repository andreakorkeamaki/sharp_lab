import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sharp_lab.sharp import SharpRunRecord
from sharp_lab.ui.server import SharpLabRequestHandler, _resolve_page


class UIServerTests(unittest.TestCase):
    def test_serialize_run_url_encodes_artifact_filenames(self) -> None:
        run = SharpRunRecord(
            run_id="20260311T150747Z-splat-3",
            input_path="/tmp/input.jpg",
            output_dir="/tmp/output",
            ply_files=["splat#3 final.ply"],
            device="cpu",
            command=["run-sharp", "predict"],
            return_code=0,
            status="completed",
            created_at="2026-03-11T15:07:47+00:00",
            duration_seconds=1.0,
            log_path="/tmp/sharp.log",
            error=None,
        )

        payload = SharpLabRequestHandler._serialize_run(None, run)

        self.assertEqual(
            payload["viewer_urls"],
            ["/artifacts/20260311T150747Z-splat-3/splat%233%20final.ply"],
        )

    def test_resolve_page_serves_blender_addon_download_page(self) -> None:
        self.assertEqual(_resolve_page(None, "/blender-addon"), "blender-addon.html")


if __name__ == "__main__":
    unittest.main()
