from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace
import sys
import tempfile
import unittest
from unittest import mock
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class _FakeOperator:
    def __init__(self) -> None:
        self.reports = []

    def report(self, level, message) -> None:
        self.reports.append((level, message))


def _load_addon_module():
    previous_modules = {
        name: sys.modules.get(name)
        for name in (
            "bpy",
            "bpy.props",
            "bpy.types",
            "bpy_extras",
            "bpy_extras.io_utils",
        )
    }

    bpy = ModuleType("bpy")
    bpy_props = ModuleType("bpy.props")
    bpy_types = ModuleType("bpy.types")
    bpy_extras = ModuleType("bpy_extras")
    bpy_io_utils = ModuleType("bpy_extras.io_utils")

    def fake_property(*args, **kwargs):
        return None

    bpy_props.BoolProperty = fake_property
    bpy_props.EnumProperty = fake_property
    bpy_props.FloatProperty = fake_property
    bpy_props.PointerProperty = fake_property
    bpy_props.StringProperty = fake_property

    bpy_types.AddonPreferences = type("AddonPreferences", (), {})
    bpy_types.Operator = _FakeOperator
    bpy_types.Panel = type("Panel", (), {})
    bpy_types.PropertyGroup = type("PropertyGroup", (), {})
    bpy.types = bpy_types
    bpy.props = bpy_props
    bpy.ops = SimpleNamespace()
    bpy.utils = SimpleNamespace(register_class=lambda cls: None, unregister_class=lambda cls: None)
    bpy_io_utils.ImportHelper = type("ImportHelper", (), {})

    sys.modules["bpy"] = bpy
    sys.modules["bpy.props"] = bpy_props
    sys.modules["bpy.types"] = bpy_types
    sys.modules["bpy_extras"] = bpy_extras
    sys.modules["bpy_extras.io_utils"] = bpy_io_utils

    module_path = ROOT / "blender_addon" / "sharp_lab_blender" / "__init__.py"
    spec = importlib.util.spec_from_file_location("sharp_lab_blender_test", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["sharp_lab_blender_test"] = module
    try:
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.pop("sharp_lab_blender_test", None)
        for name, previous in previous_modules.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous


def _make_context(addon_module, workspace: Path):
    prefs = SimpleNamespace(
        executable_path="",
        checkpoint_path="",
        workspace_path=str(workspace),
        default_device="cpu",
        setup_completed=False,
    )
    props = SimpleNamespace(
        model_download_active=False,
        model_download_percent=0.0,
        model_download_detail="",
        status_message="",
    )
    return SimpleNamespace(
        preferences=SimpleNamespace(
            addons={
                addon_module._addon_name(): SimpleNamespace(preferences=prefs),
                "sharp_lab_blender": SimpleNamespace(preferences=prefs),
            }
        ),
        scene=SimpleNamespace(sharp_lab=props),
    ), prefs, props


class BlenderAddonRuntimeTests(unittest.TestCase):
    def test_macos_bundled_runtime_is_copied_to_workspace(self) -> None:
        addon = _load_addon_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            bundled_runtime = temp_root / "runtime_template"
            (bundled_runtime / ".venv" / "bin").mkdir(parents=True)
            (bundled_runtime / ".venv" / "bin" / "python").write_text("", encoding="utf-8")
            (bundled_runtime / "run-sharp").write_text("#!/bin/sh\n", encoding="utf-8")
            context, prefs, _props = _make_context(addon, temp_root / "workspace")

            with mock.patch.object(addon, "os", SimpleNamespace(name="posix")):
                addon._BUNDLED_RUNTIME_DIR = bundled_runtime
                runtime_dir = addon._ensure_workspace_runtime(context)

            self.assertEqual(runtime_dir, (temp_root / "workspace" / "runtime").resolve())
            self.assertTrue((runtime_dir / "run-sharp").exists())
            self.assertEqual(Path(prefs.executable_path), runtime_dir / "run-sharp")

    def test_windows_bundled_runtime_is_copied_to_workspace(self) -> None:
        addon = _load_addon_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            bundled_runtime = temp_root / "runtime_template"
            (bundled_runtime / "python" / "tools").mkdir(parents=True)
            (bundled_runtime / "python" / "tools" / "python.exe").write_text("", encoding="utf-8")
            (bundled_runtime / "run-sharp.cmd").write_text(
                '"%PYTHON_DIR%\\tools\\python.exe" "%RUNTIME_DIR%\\sharp_bootstrap.py" %*\n',
                encoding="utf-8",
            )
            context, prefs, _props = _make_context(addon, temp_root / "workspace")

            with mock.patch.object(addon, "os", SimpleNamespace(name="nt")):
                addon._BUNDLED_RUNTIME_DIR = bundled_runtime
                runtime_dir = addon._ensure_workspace_runtime(context)

            self.assertEqual(runtime_dir, (temp_root / "workspace" / "runtime").resolve())
            self.assertTrue((runtime_dir / "run-sharp.cmd").exists())
            self.assertEqual(Path(prefs.executable_path), runtime_dir / "run-sharp.cmd")

    def test_download_model_operator_accepts_existing_checkpoint(self) -> None:
        addon = _load_addon_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            runtime_dir = temp_root / "workspace" / "runtime"
            (runtime_dir / "python" / "tools").mkdir(parents=True)
            (runtime_dir / "python" / "tools" / "python.exe").write_text("", encoding="utf-8")
            (runtime_dir / "run-sharp.cmd").write_text(
                '"%PYTHON_DIR%\\tools\\python.exe" "%RUNTIME_DIR%\\sharp_bootstrap.py" %*\n',
                encoding="utf-8",
            )
            checkpoint = runtime_dir / "models" / "sharp_2572gikvuh.pt"
            checkpoint.parent.mkdir(parents=True)
            checkpoint.write_text("model", encoding="utf-8")
            context, prefs, props = _make_context(addon, temp_root / "workspace")

            with mock.patch.object(addon, "os", SimpleNamespace(name="nt")):
                result = addon.SHARPLAB_OT_download_model().execute(context)

            self.assertEqual(result, {"FINISHED"})
            self.assertEqual(Path(prefs.checkpoint_path), checkpoint.resolve())
            self.assertTrue(prefs.setup_completed)
            self.assertEqual(props.status_message, "Apple SHARP model is ready.")

    def test_saved_windows_runtime_is_used_when_bundled_template_is_missing(self) -> None:
        addon = _load_addon_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            runtime_dir = temp_root / "workspace" / "runtime"
            (runtime_dir / "python" / "tools").mkdir(parents=True)
            (runtime_dir / "python" / "tools" / "python.exe").write_text("", encoding="utf-8")
            launcher = runtime_dir / "run-sharp.cmd"
            launcher.write_text(
                '"%PYTHON_DIR%\\tools\\python.exe" "%RUNTIME_DIR%\\sharp_bootstrap.py" %*\n',
                encoding="utf-8",
            )
            checkpoint = runtime_dir / "models" / "sharp_2572gikvuh.pt"
            checkpoint.parent.mkdir(parents=True)
            checkpoint.write_text("model", encoding="utf-8")
            context, prefs, _props = _make_context(addon, temp_root / "workspace")
            prefs.executable_path = str(launcher)
            prefs.checkpoint_path = str(checkpoint)
            missing_template = temp_root / "missing-runtime-template"

            with mock.patch.object(addon, "os", SimpleNamespace(name="nt")):
                addon._BUNDLED_RUNTIME_DIR = missing_template
                resolved_runtime = addon._ensure_workspace_runtime(context)

            self.assertEqual(resolved_runtime, runtime_dir.resolve())
            self.assertEqual(Path(prefs.executable_path), launcher.resolve())
            self.assertEqual(Path(prefs.checkpoint_path), checkpoint.resolve())

    def test_missing_bundled_runtime_downloads_windows_addon_runtime_template(self) -> None:
        addon = _load_addon_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            runtime_archive = temp_root / "runtime.zip"
            with zipfile.ZipFile(runtime_archive, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr(
                    "sharp_lab_blender/runtime_template/run-sharp.cmd",
                    '"%PYTHON_DIR%\\tools\\python.exe" "%RUNTIME_DIR%\\sharp_bootstrap.py" %*\n',
                )
                archive.writestr("sharp_lab_blender/runtime_template/python/tools/python.exe", "")

            context, prefs, _props = _make_context(addon, temp_root / "workspace")
            missing_template = temp_root / "missing-runtime-template"
            downloaded_urls = []

            def fake_download(url, destination, progress_callback=None):
                downloaded_urls.append(url)
                destination.write_bytes(runtime_archive.read_bytes())
                if progress_callback is not None:
                    progress_callback(destination.stat().st_size, destination.stat().st_size)

            with mock.patch.object(addon, "os", SimpleNamespace(name="nt")):
                with mock.patch.object(addon, "download_to_path", side_effect=fake_download):
                    addon._BUNDLED_RUNTIME_DIR = missing_template
                    runtime_dir = addon._ensure_workspace_runtime(context)

            self.assertEqual(runtime_dir, (temp_root / "workspace" / "runtime").resolve())
            self.assertTrue((runtime_dir / "run-sharp.cmd").exists())
            self.assertEqual(Path(prefs.executable_path), runtime_dir / "run-sharp.cmd")
            self.assertEqual(
                downloaded_urls,
                [
                    "https://github.com/andreakorkeamaki/sharp_lab/releases/download/"
                    "v0.1.15/sharp-lab-blender-addon-windows-v0.1.15.zip"
                ],
            )


if __name__ == "__main__":
    unittest.main()
