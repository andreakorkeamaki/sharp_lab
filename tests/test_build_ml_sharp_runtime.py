from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest


def load_build_runtime_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "build_ml_sharp_runtime.py"
    spec = importlib.util.spec_from_file_location("build_ml_sharp_runtime", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BuildMlSharpRuntimeTests(unittest.TestCase):
    def test_write_launchers_use_local_python_bootstrap(self) -> None:
        module = load_build_runtime_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            runtime_dir = Path(temp_dir)

            module.write_launchers(runtime_dir)

            bootstrap = (runtime_dir / "sharp_bootstrap.py").read_text(encoding="utf-8")
            windows_launcher = (runtime_dir / "run-sharp.cmd").read_text(encoding="utf-8")
            posix_launcher = (runtime_dir / "run-sharp").read_text(encoding="utf-8")

            self.assertIn("from sharp.cli import main_cli", bootstrap)
            self.assertIn('"%VENV_DIR%\\Scripts\\python.exe" "%RUNTIME_DIR%\\sharp_bootstrap.py" %*', windows_launcher)
            self.assertNotIn("sharp.exe", windows_launcher)
            self.assertIn('exec "$VENV_DIR/bin/python" "$RUNTIME_DIR/sharp_bootstrap.py" "$@"', posix_launcher)


if __name__ == "__main__":
    unittest.main()
