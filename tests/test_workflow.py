import json
import sys
import tempfile
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sharp_lab.discovery import ImageDiscoveryService
from sharp_lab.export import ExportManager
from sharp_lab.pipeline import PreprocessingPipeline
from sharp_lab.sharp import SharpIntegrationService


class WorkflowTests(unittest.TestCase):
    def test_end_to_end_asset_flow(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            source_dir = tmp_path / "source"
            source_dir.mkdir()
            (source_dir / "IMG_0001.HEIC").write_bytes(b"fake-heic-data")
            (source_dir / "notes.txt").write_text("ignore me", encoding="utf-8")

            imports_dir = tmp_path / "imports"
            processed_dir = tmp_path / "processed"
            exports_dir = tmp_path / "exports"

            imported = ImageDiscoveryService(imports_dir).import_from(source_dir)
            self.assertEqual(len(imported), 1)
            self.assertEqual(imported[0].managed_path.name, "img_0001.heic")

            pipeline_result = PreprocessingPipeline(imports_dir, processed_dir).run()
            self.assertEqual(len(pipeline_result.processed_assets), 1)
            manifest = json.loads(pipeline_result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["asset_count"], 1)

            bundle_dir = ExportManager(processed_dir, exports_dir).create_bundle("sharp-ready")
            self.assertTrue((bundle_dir / "assets" / "img_0001.heic").exists())

            plan = SharpIntegrationService().plan_submission(bundle_dir)
            self.assertEqual(plan["status"], "planned")
            self.assertEqual(plan["asset_count"], 1)
