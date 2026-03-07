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
            self.assertEqual(config.logging.level, "INFO")

    def test_load_json_config_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            config_path = tmp_path / "sharp_lab.json"
            config_path.write_text(
                """
{
  "paths": {
    "workspace": "./lab",
    "imports": "./lab/incoming"
  },
  "logging": {
    "level": "debug"
  }
}
""".strip(),
                encoding="utf-8",
            )

            config = SharpLabConfig.load(config_path, base_dir=tmp_path)

            self.assertEqual(config.paths.workspace, (tmp_path / "lab").resolve())
            self.assertEqual(config.paths.imports, (tmp_path / "lab" / "incoming").resolve())
            self.assertEqual(config.paths.processed, (tmp_path / "lab" / "processed").resolve())
            self.assertEqual(config.logging.level, "DEBUG")
