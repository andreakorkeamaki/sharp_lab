from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def _load_module(name: str, relative_path: str):
    module_path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


MAC_BUILDER = _load_module("build_blender_addon_script", "scripts/build_blender_addon.py")
WINDOWS_BUILDER = _load_module("build_blender_addon_windows_script", "scripts/build_blender_addon_windows.py")


class BlenderAddonBuildTests(unittest.TestCase):
    def test_mac_builder_copies_runtime_dir_and_drops_bundled_models(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime_dir = Path(temp_dir) / "runtime"
            (runtime_dir / ".venv" / "bin").mkdir(parents=True)
            (runtime_dir / ".venv" / "bin" / "python").write_text("", encoding="utf-8")
            (runtime_dir / "run-sharp").write_text("#!/bin/sh\n", encoding="utf-8")
            (runtime_dir / "models").mkdir()
            (runtime_dir / "models" / "sharp.pt").write_text("model", encoding="utf-8")

            destination = Path(temp_dir) / "copied-runtime"
            MAC_BUILDER._copy_runtime_from_directory(runtime_dir, destination)

            self.assertTrue((destination / "run-sharp").exists())
            self.assertFalse((destination / "models" / "sharp.pt").exists())

    def test_windows_builder_creates_portable_runtime_from_runtime_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            runtime_dir = temp_root / "runtime"
            site_packages = runtime_dir / ".venv" / "Lib" / "site-packages"
            site_packages.mkdir(parents=True)
            (site_packages / "sharp_lab_placeholder.py").write_text("value = 1\n", encoding="utf-8")
            (site_packages / "__editable__.sharp_lab-0.1.7.pth").write_text("remove me\n", encoding="utf-8")
            (runtime_dir / "build-info.json").write_text('{"name":"runtime"}', encoding="utf-8")
            (runtime_dir / "licenses").mkdir()
            (runtime_dir / "licenses" / "README.md").write_text("license", encoding="utf-8")

            nupkg_path = temp_root / "python.3.11.9.nupkg"
            with zipfile.ZipFile(nupkg_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("tools/python.exe", "")

            destination = temp_root / "portable-runtime"
            WINDOWS_BUILDER._reset_dir(WINDOWS_BUILDER.BUILD_ROOT)
            WINDOWS_BUILDER.build_portable_runtime(
                destination,
                runtime_source_dir=runtime_dir,
                python_nupkg_path=nupkg_path,
            )

            self.assertTrue((destination / "python" / "tools" / "python.exe").exists())
            self.assertTrue((destination / "python" / "tools" / "Lib" / "site-packages" / "sharp_lab_placeholder.py").exists())
            self.assertFalse((destination / "python" / "tools" / "Lib" / "site-packages" / "__editable__.sharp_lab-0.1.7.pth").exists())
            self.assertTrue((destination / "run-sharp.cmd").exists())


if __name__ == "__main__":
    unittest.main()
