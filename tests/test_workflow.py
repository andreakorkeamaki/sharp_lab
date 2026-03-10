import io
import json
import os
import sys
import tempfile
from pathlib import Path
import unittest
from unittest import mock

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

    def test_installation_status_marks_missing_checkpoint_as_auto_download(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            fake_sharp = tmp_path / "run-sharp"
            fake_sharp.write_text("#!/bin/sh\n", encoding="utf-8")
            fake_sharp.chmod(0o755)

            status = SharpIntegrationService(
                runs_dir=tmp_path / "runs",
                executable=fake_sharp,
                checkpoint=None,
                default_device="cpu",
            ).installation_status()

            self.assertTrue(status["executable_exists"])
            self.assertFalse(status["checkpoint_exists"])
            self.assertTrue(status["runtime_ready"])
            self.assertEqual(status["checkpoint_mode"], "download-available")
            self.assertTrue(status["can_download_checkpoint"])
            self.assertTrue(status["preferred_checkpoint"].endswith("models/sharp_2572gikvuh.pt"))

    def test_download_default_checkpoint_saves_model_next_to_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            fake_sharp = tmp_path / "run-sharp"
            fake_sharp.write_text("#!/bin/sh\n", encoding="utf-8")
            fake_sharp.chmod(0o755)

            service = SharpIntegrationService(
                runs_dir=tmp_path / "runs",
                executable=fake_sharp,
                checkpoint=None,
                default_device="cpu",
            )

            with mock.patch("sharp_lab.sharp.integration.urlopen", return_value=io.BytesIO(b"fake-model-weights")):
                checkpoint_path = service.download_default_checkpoint()

            self.assertTrue(checkpoint_path.exists())
            self.assertEqual(checkpoint_path.read_bytes(), b"fake-model-weights")
            self.assertEqual(service.checkpoint, checkpoint_path.resolve())

    def test_replace_checkpoint_file_retries_after_transient_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            service = SharpIntegrationService()
            source_path = tmp_path / "checkpoint.part"
            target_path = tmp_path / "sharp_2572gikvuh.pt"
            source_path.write_bytes(b"weights")

            attempts = {"count": 0}
            original_replace = os.replace

            def flaky_replace(source: Path, target: Path) -> None:
                attempts["count"] += 1
                if attempts["count"] < 3:
                    raise PermissionError("WinError 32: locked")
                original_replace(source, target)

            with mock.patch("sharp_lab.sharp.integration.os.name", "nt"):
                with mock.patch("sharp_lab.sharp.integration.os.replace", side_effect=flaky_replace):
                    with mock.patch("sharp_lab.sharp.integration.time.sleep"):
                        service._replace_checkpoint_file(source_path, target_path)

            self.assertEqual(attempts["count"], 3)
            self.assertTrue(target_path.exists())
            self.assertEqual(target_path.read_bytes(), b"weights")

    def test_sharp_decimate_creates_variant_and_updates_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            run_dir = tmp_path / "runs" / "20260310T120000Z-sample"
            output_dir = run_dir / "output"
            output_dir.mkdir(parents=True)

            ply_path = output_dir / "sample.ply"
            ply_path.write_text(
                "\n".join(
                    [
                        "ply",
                        "format ascii 1.0",
                        "element vertex 4",
                        "property float x",
                        "property float y",
                        "property float z",
                        "end_header",
                        "0 0 0",
                        "1 0 0",
                        "2 0 0",
                        "3 0 0",
                    ]
                )
                + "\n",
                encoding="ascii",
            )

            manifest_path = run_dir / "run.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "run_id": "20260310T120000Z-sample",
                        "input_path": str((tmp_path / "sample.jpg").resolve()),
                        "output_dir": str(output_dir.resolve()),
                        "ply_files": ["sample.ply"],
                        "device": "cpu",
                        "command": ["run-sharp", "predict"],
                        "return_code": 0,
                        "status": "completed",
                        "created_at": "2026-03-10T12:00:00+00:00",
                        "duration_seconds": 1.2,
                        "log_path": str((run_dir / "sharp.log").resolve()),
                        "error": None,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

            service = SharpIntegrationService(runs_dir=tmp_path / "runs")
            updated_run, decimation = service.decimate_run(
                "20260310T120000Z-sample",
                filename="sample.ply",
                ratio=0.5,
            )

            self.assertEqual(decimation.output_file, "sample-decimated-50.ply")
            self.assertEqual(decimation.original_vertices, 4)
            self.assertEqual(decimation.decimated_vertices, 2)
            self.assertEqual(updated_run.ply_files, ["sample.ply", "sample-decimated-50.ply"])

            decimated_path = output_dir / "sample-decimated-50.ply"
            self.assertTrue(decimated_path.exists())
            decimated_lines = decimated_path.read_text(encoding="ascii").splitlines()
            self.assertIn("element vertex 2", decimated_lines)
            self.assertEqual(decimated_lines[-2:], ["0 0 0", "2 0 0"])
