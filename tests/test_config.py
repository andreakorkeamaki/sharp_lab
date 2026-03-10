import sys
import tempfile
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sharp_lab.config import SharpLabConfig


class ConfigTests(unittest.TestCase):
    def test_default_config_uses_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            config = SharpLabConfig.load(base_dir=tmp_path)

            self.assertEqual(config.paths.workspace, (tmp_path / "workspace").resolve())
            self.assertEqual(config.paths.imports, (tmp_path / "workspace" / "imports").resolve())
            self.assertEqual(config.paths.runs, (tmp_path / "workspace" / "runs").resolve())
            self.assertEqual(config.logging.level, "INFO")
            self.assertEqual(config.web.port, 4173)

    def test_default_config_prefers_portable_runtime_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            runtime_dir = tmp_path / "runtime"
            runtime_models = runtime_dir / "models"
            runtime_models.mkdir(parents=True)

            executable_name = "run-sharp.exe" if sys.platform == "win32" else "run-sharp"
            executable_path = runtime_dir / executable_name
            executable_path.write_text("", encoding="utf-8")
            checkpoint_path = runtime_models / "sharp_2572gikvuh.pt"
            checkpoint_path.write_text("", encoding="utf-8")

            config = SharpLabConfig.default(base_dir=tmp_path)

            self.assertEqual(config.sharp.executable, executable_path.resolve())
            self.assertEqual(config.sharp.checkpoint, checkpoint_path.resolve())

    def test_load_json_config_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            config_path = tmp_path / "sharp_lab.json"
            config_path.write_text(
                """
{
  "paths": {
    "workspace": "./lab",
    "imports": "./lab/incoming",
    "runs": "./lab/runs"
  },
  "logging": {
    "level": "debug"
  },
  "sharp": {
    "executable": "./tools/run-sharp",
    "checkpoint": "./models/sharp.pt",
    "default_device": "mps"
  },
  "web": {
    "host": "0.0.0.0",
    "port": 9000
  }
}
""".strip(),
                encoding="utf-8",
            )

            config = SharpLabConfig.load(config_path, base_dir=tmp_path)

            self.assertEqual(config.paths.workspace, (tmp_path / "lab").resolve())
            self.assertEqual(config.paths.imports, (tmp_path / "lab" / "incoming").resolve())
            self.assertEqual(config.paths.processed, (tmp_path / "lab" / "processed").resolve())
            self.assertEqual(config.paths.runs, (tmp_path / "lab" / "runs").resolve())
            self.assertEqual(config.logging.level, "DEBUG")
            self.assertEqual(config.sharp.executable, (tmp_path / "tools" / "run-sharp").resolve())
            self.assertEqual(config.sharp.checkpoint, (tmp_path / "models" / "sharp.pt").resolve())
            self.assertEqual(config.sharp.default_device, "mps")
            self.assertEqual(config.web.host, "0.0.0.0")
            self.assertEqual(config.web.port, 9000)
