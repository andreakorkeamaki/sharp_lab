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

    def test_sharp_predict_records_run_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            input_path = tmp_path / "sample.jpg"
            input_path.write_bytes(b"fake-jpeg")

            fake_sharp = tmp_path / "run-sharp"
            fake_sharp.write_text(
                """#!/bin/sh
set -eu
output_dir=""
input_path=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    predict)
      shift
      ;;
    -i)
      input_path="$2"
      shift 2
      ;;
    -o)
      output_dir="$2"
      shift 2
      ;;
    -c|--device)
      shift 2
      ;;
    *)
      shift
      ;;
  esac
done
mkdir -p "$output_dir"
stem=$(basename "$input_path")
stem=${stem%.*}
printf 'ply\nformat ascii 1.0\nend_header\n' > "$output_dir/$stem.ply"
printf 'fake sharp completed\n'
""".strip(),
                encoding="utf-8",
            )
            fake_sharp.chmod(0o755)

            service = SharpIntegrationService(
                runs_dir=tmp_path / "runs",
                executable=fake_sharp,
                checkpoint=None,
                default_device="cpu",
            )
            run = service.predict(input_path, device="cpu")

            self.assertEqual(run.status, "completed")
            self.assertEqual(run.ply_files, ["sample.ply"])
            manifest_path = tmp_path / "runs" / run.run_id / "run.json"
            self.assertTrue(manifest_path.exists())
            records = SharpIntegrationService(runs_dir=tmp_path / "runs").list_runs()
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].run_id, run.run_id)
