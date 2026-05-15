from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
from typing import Iterable
import zipfile

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, PointerProperty, StringProperty
from bpy.types import AddonPreferences, Operator, Panel, PropertyGroup
from bpy_extras.io_utils import ImportHelper


_ADDON_DIR = Path(__file__).resolve().parent
_ADDON_PARENT_DIR = _ADDON_DIR.parent
_VENDOR_DIR = _ADDON_DIR / "vendor"
_BUNDLED_RUNTIME_DIR = _ADDON_DIR / "runtime_template"
parent_path = str(_ADDON_PARENT_DIR)
if parent_path not in sys.path:
    sys.path.insert(0, parent_path)
if _VENDOR_DIR.exists():
    vendor_path = str(_VENDOR_DIR)
    if vendor_path not in sys.path:
        sys.path.insert(0, vendor_path)

from sharp_lab.downloads import ProgressCallback, download_to_path  # noqa: E402
from sharp_lab.sharp.integration import DEFAULT_MODEL_FILENAME, SharpIntegrationService  # noqa: E402


bl_info = {
    "name": "Sharp Lab",
    "author": "Andrea Korkeamaki",
    "version": (0, 1, 12),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > Sharp Lab",
    "description": "Run Apple SHARP from Blender and import the generated PLY into the scene.",
    "category": "Import-Export",
}


_MODEL_DOWNLOAD_STATE = {
    "lock": threading.Lock(),
    "active": False,
    "message": "",
    "downloaded": 0,
    "total": None,
    "percent": 0.0,
    "error": "",
    "result_path": "",
}

_RELEASE_REPOSITORY = "andreakorkeamaki/sharp_lab"


def _addon_name() -> str:
    return __package__ or "sharp_lab_blender"


def _addon_prefs(context: bpy.types.Context) -> "SharpLabAddonPreferences":
    return context.preferences.addons[_addon_name()].preferences


def _workspace_root(raw_path: str) -> Path:
    root = Path(raw_path).expanduser()
    return root.resolve() if raw_path.strip() else (Path.home() / "sharp_lab_blender").resolve()


def _runs_dir(workspace_root: Path) -> Path:
    return workspace_root / "runs"


def _runtime_root(workspace_root: Path) -> Path:
    return workspace_root / "runtime"


def _report_lines(message: str) -> list[str]:
    return [line.strip() for line in message.splitlines() if line.strip()]


@dataclass(frozen=True)
class _RunResult:
    run_id: str
    ply_path: Path


def _set_model_download_state(**updates: object) -> None:
    with _MODEL_DOWNLOAD_STATE["lock"]:
        _MODEL_DOWNLOAD_STATE.update(updates)


def _get_model_download_state() -> dict[str, object]:
    with _MODEL_DOWNLOAD_STATE["lock"]:
        return dict(_MODEL_DOWNLOAD_STATE)


def _reset_model_download_state() -> None:
    _set_model_download_state(
        active=False,
        message="",
        downloaded=0,
        total=None,
        percent=0.0,
        error="",
        result_path="",
    )


def _runtime_executable_name() -> str:
    return "run-sharp.exe" if os.name == "nt" else "run-sharp"


def _runtime_executable_candidates(runtime_dir: Path) -> list[Path]:
    if os.name == "nt":
        names = ("run-sharp.exe", "run-sharp.bat", "run-sharp.cmd")
    else:
        names = ("run-sharp",)
    return [runtime_dir / name for name in names]


def _runtime_executable_path(runtime_dir: Path) -> Path:
    candidates = _runtime_executable_candidates(runtime_dir)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _runtime_checkpoint_path(runtime_dir: Path) -> Path:
    return runtime_dir / "models" / DEFAULT_MODEL_FILENAME


def _configured_runtime_path(prefs: "SharpLabAddonPreferences") -> Path:
    if prefs.executable_path.strip():
        return Path(prefs.executable_path).expanduser()
    return _runtime_executable_path(_runtime_root(_workspace_root(prefs.workspace_path)))


def _configured_checkpoint_path(prefs: "SharpLabAddonPreferences") -> Path:
    if prefs.checkpoint_path.strip():
        return Path(prefs.checkpoint_path).expanduser()
    if prefs.executable_path.strip():
        return Path(prefs.executable_path).expanduser().parent / "models" / DEFAULT_MODEL_FILENAME
    return _runtime_checkpoint_path(_runtime_root(_workspace_root(prefs.workspace_path)))


def _setup_status(prefs: "SharpLabAddonPreferences") -> dict[str, object]:
    runtime_path = _configured_runtime_path(prefs)
    checkpoint_path = _configured_checkpoint_path(prefs)
    runtime_ready = runtime_path.exists()
    checkpoint_ready = checkpoint_path.exists()
    return {
        "runtime_path": runtime_path,
        "checkpoint_path": checkpoint_path,
        "bundled_runtime": _bundled_runtime_available(),
        "runtime_ready": runtime_ready,
        "checkpoint_ready": checkpoint_ready,
        "setup_complete": runtime_ready and checkpoint_ready,
    }


def _set_setup_completed(prefs: "SharpLabAddonPreferences", completed: bool) -> None:
    prefs.setup_completed = completed


def _bundled_runtime_available() -> bool:
    return any(candidate.exists() for candidate in _runtime_executable_candidates(_BUNDLED_RUNTIME_DIR))


def _addon_version_tag() -> str:
    return "v" + ".".join(str(part) for part in bl_info["version"])


def _runtime_platform_slug() -> str:
    return "windows" if os.name == "nt" else "macos"


def _release_runtime_archive_url() -> str:
    tag = _addon_version_tag()
    platform_slug = _runtime_platform_slug()
    filename = f"sharp-lab-runtime-{platform_slug}-{tag}.zip"
    return f"https://github.com/{_RELEASE_REPOSITORY}/releases/download/{tag}/{filename}"


def _safe_extract_zip(archive_path: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive_path) as archive:
        destination = destination.resolve()
        for member in archive.infolist():
            target = (destination / member.filename).resolve()
            if target != destination and destination not in target.parents:
                raise RuntimeError(f"Unsafe runtime archive member path: {member.filename}")
        archive.extractall(destination)


def _find_runtime_dir(extract_dir: Path) -> Path:
    direct = extract_dir / "runtime"
    if direct.is_dir():
        return direct

    candidates = [path for path in extract_dir.rglob("runtime") if path.is_dir()]
    if not candidates:
        raise RuntimeError("The downloaded SHARP runtime archive did not contain a runtime folder.")
    return sorted(candidates, key=lambda path: len(path.parts))[0]


def _install_runtime_from_release_archive(
    runtime_dir: Path,
    progress_callback: ProgressCallback | None = None,
) -> Path:
    workspace_root = runtime_dir.parent
    staging_dir = workspace_root / "runtime.installing"
    workspace_root.mkdir(parents=True, exist_ok=True)
    if staging_dir.exists():
        shutil.rmtree(staging_dir, ignore_errors=True)

    with tempfile.TemporaryDirectory(dir=workspace_root) as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        archive_path = temp_dir / "runtime.zip"
        extract_dir = temp_dir / "extract"
        extract_dir.mkdir(parents=True, exist_ok=True)

        download_to_path(_release_runtime_archive_url(), archive_path, progress_callback=progress_callback)
        _safe_extract_zip(archive_path, extract_dir)
        runtime_source = _find_runtime_dir(extract_dir)
        shutil.copytree(runtime_source, staging_dir)

    if runtime_dir.exists():
        shutil.rmtree(runtime_dir, ignore_errors=True)
    staging_dir.replace(runtime_dir)
    _repair_posix_runtime_permissions(runtime_dir)
    return runtime_dir.resolve()


def _runtime_is_portable(runtime_dir: Path) -> bool:
    if os.name == "nt":
        launcher = runtime_dir / "run-sharp.cmd"
        python_exe = runtime_dir / "python" / "tools" / "python.exe"
        if not launcher.exists() or not python_exe.exists():
            return False
        try:
            launcher_text = launcher.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return False
        return r"%PYTHON_DIR%\tools\python.exe" in launcher_text

    launcher = runtime_dir / "run-sharp"
    python_bin = runtime_dir / ".venv" / "bin" / "python"
    return launcher.exists() and python_bin.exists()


def _repair_posix_runtime_permissions(runtime_dir: Path) -> None:
    if os.name == "nt":
        return

    for launcher in _runtime_executable_candidates(runtime_dir):
        if launcher.exists():
            launcher.chmod(0o755)

    venv_bin_dir = runtime_dir / ".venv" / "bin"
    if venv_bin_dir.exists():
        for path in venv_bin_dir.iterdir():
            if path.is_file():
                path.chmod(0o755)


def _ensure_workspace_runtime(
    context: bpy.types.Context,
    progress_callback: ProgressCallback | None = None,
) -> Path:
    prefs = _addon_prefs(context)
    configured_executable = Path(prefs.executable_path).expanduser() if prefs.executable_path.strip() else None
    if configured_executable is not None and configured_executable.exists():
        runtime_dir = configured_executable.parent.resolve()
        _repair_posix_runtime_permissions(runtime_dir)
        prefs.executable_path = str(configured_executable.resolve())
        checkpoint_path = _configured_checkpoint_path(prefs)
        if checkpoint_path.exists():
            prefs.checkpoint_path = str(checkpoint_path.resolve())
        return runtime_dir

    workspace_root = _workspace_root(prefs.workspace_path)
    runtime_dir = _runtime_root(workspace_root)
    runtime_executable = _runtime_executable_path(runtime_dir)
    if runtime_executable.exists() and _runtime_is_portable(runtime_dir):
        _repair_posix_runtime_permissions(runtime_dir)
        prefs.executable_path = str(runtime_executable)
        checkpoint_path = _runtime_checkpoint_path(runtime_dir)
        if checkpoint_path.exists():
            prefs.checkpoint_path = str(checkpoint_path)
        return runtime_dir

    workspace_root.mkdir(parents=True, exist_ok=True)
    staging_dir = workspace_root / "runtime.installing"
    if staging_dir.exists():
        shutil.rmtree(staging_dir, ignore_errors=True)
    if _bundled_runtime_available():
        shutil.copytree(_BUNDLED_RUNTIME_DIR, staging_dir)
        if runtime_dir.exists():
            shutil.rmtree(runtime_dir, ignore_errors=True)
        staging_dir.replace(runtime_dir)
        _repair_posix_runtime_permissions(runtime_dir)
    else:
        runtime_dir = _install_runtime_from_release_archive(runtime_dir, progress_callback=progress_callback)

    runtime_executable = _runtime_executable_path(runtime_dir)
    prefs.executable_path = str(runtime_executable)
    checkpoint_path = _runtime_checkpoint_path(runtime_dir)
    if checkpoint_path.exists():
        prefs.checkpoint_path = str(checkpoint_path)
    return runtime_dir


def _build_service(context: bpy.types.Context, ensure_runtime: bool = False) -> SharpIntegrationService:
    prefs = _addon_prefs(context)
    workspace_root = _workspace_root(prefs.workspace_path)
    runs_dir = _runs_dir(workspace_root)
    runs_dir.mkdir(parents=True, exist_ok=True)

    executable = Path(prefs.executable_path).expanduser() if prefs.executable_path.strip() else None
    if ensure_runtime and (executable is None or not executable.exists()):
        runtime_dir = _ensure_workspace_runtime(context)
        executable = _runtime_executable_path(runtime_dir)
    checkpoint = Path(prefs.checkpoint_path).expanduser() if prefs.checkpoint_path.strip() else None
    return SharpIntegrationService(
        runs_dir=runs_dir,
        executable=executable,
        checkpoint=checkpoint,
        default_device=prefs.default_device,
    )


def _build_download_service(executable: Path, checkpoint: Path | None, default_device: str) -> SharpIntegrationService:
    return SharpIntegrationService(
        runs_dir=None,
        executable=executable,
        checkpoint=checkpoint,
        default_device=default_device,
    )


def _ensure_model_checkpoint(
    context: bpy.types.Context,
    progress_callback=None,
) -> Path:
    prefs = _addon_prefs(context)
    runtime_dir = _ensure_workspace_runtime(context, progress_callback=progress_callback)
    checkpoint = _configured_checkpoint_path(prefs)
    if checkpoint.exists():
        prefs.checkpoint_path = str(checkpoint.resolve())
        _set_setup_completed(prefs, True)
        return checkpoint.resolve()

    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    prefs.checkpoint_path = str(checkpoint)
    executable = _configured_runtime_path(prefs)
    service = _build_download_service(executable, checkpoint, prefs.default_device)
    downloaded = service.download_default_checkpoint(progress_callback=progress_callback)
    prefs.checkpoint_path = str(downloaded)
    _set_setup_completed(prefs, True)
    return downloaded


def _import_ply(filepath: Path) -> None:
    if hasattr(bpy.ops.wm, "ply_import"):
        bpy.ops.wm.ply_import(filepath=str(filepath))
        return
    if hasattr(bpy.ops.import_mesh, "ply"):
        bpy.ops.import_mesh.ply(filepath=str(filepath))
        return
    raise RuntimeError("This Blender build does not expose a PLY import operator.")


def _first_ply_path(record) -> Path:
    if not record.ply_files:
        raise RuntimeError("SHARP completed but did not produce any PLY files.")
    return Path(record.output_dir) / record.ply_files[0]


def _run_sharp(context: bpy.types.Context, input_path: Path) -> _RunResult:
    service = _build_service(context)
    record = service.predict(input_path, device=_addon_prefs(context).default_device)
    return _RunResult(run_id=record.run_id, ply_path=_first_ply_path(record))


class SharpLabAddonPreferences(AddonPreferences):
    bl_idname = _addon_name()

    executable_path: StringProperty(
        name="SHARP Executable",
        subtype="FILE_PATH",
        description="Path to run-sharp or run-sharp.exe",
        default="",
    )
    checkpoint_path: StringProperty(
        name="Checkpoint",
        subtype="FILE_PATH",
        description="Optional path to the SHARP checkpoint file",
        default="",
    )
    workspace_path: StringProperty(
        name="Workspace",
        subtype="DIR_PATH",
        description="Directory where Sharp Lab stores SHARP runs for Blender",
        default="~/sharp_lab_blender",
    )
    default_device: EnumProperty(
        name="Device",
        items=(
            ("cpu", "CPU", "Run SHARP on the CPU"),
            ("mps", "MPS", "Run SHARP on Apple Metal"),
            ("cuda", "CUDA", "Run SHARP on CUDA"),
        ),
        default="cpu",
    )
    setup_completed: BoolProperty(
        name="Setup Completed",
        description="Whether the bundled runtime and model checkpoint have been prepared",
        default=False,
    )

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        layout.label(text="Bundled builds fill these paths automatically on first run.", icon="INFO")
        layout.use_property_split = True
        layout.prop(self, "executable_path")
        layout.prop(self, "checkpoint_path")
        layout.prop(self, "workspace_path")
        layout.prop(self, "default_device")


class SharpLabSceneProperties(PropertyGroup):
    input_path: StringProperty(
        name="Input",
        subtype="FILE_PATH",
        description="Image file or folder to process with SHARP",
        default="",
    )
    last_run_id: StringProperty(
        name="Last Run",
        default="",
    )
    last_ply_path: StringProperty(
        name="Last PLY",
        default="",
    )
    auto_import: BoolProperty(
        name="Import PLY After Run",
        description="Import the generated PLY into the current scene automatically",
        default=True,
    )
    status_message: StringProperty(
        name="Status",
        default="",
    )
    model_download_active: BoolProperty(
        name="Model Download Active",
        default=False,
    )
    model_download_percent: FloatProperty(
        name="Model Download Percent",
        default=0.0,
        min=0.0,
        max=100.0,
        subtype="PERCENTAGE",
    )
    model_download_detail: StringProperty(
        name="Model Download Detail",
        default="",
    )


class SHARPLAB_OT_pick_image(Operator, ImportHelper):
    bl_idname = "sharplab.pick_image"
    bl_label = "Choose Image"
    bl_description = "Choose the source image to process"

    filename_ext = ""
    filter_glob: StringProperty(
        default="*.jpg;*.jpeg;*.png;*.heic;*.heif;*.tif;*.tiff;*.webp",
        options={"HIDDEN"},
    )

    def execute(self, context: bpy.types.Context) -> set[str]:
        context.scene.sharp_lab.input_path = self.filepath
        return {"FINISHED"}


class SHARPLAB_OT_pick_folder(Operator, ImportHelper):
    bl_idname = "sharplab.pick_folder"
    bl_label = "Choose Folder"
    bl_description = "Choose the source folder to process"

    filename_ext = ""
    use_filter_folder = True
    filter_glob: StringProperty(default="", options={"HIDDEN"})

    def execute(self, context: bpy.types.Context) -> set[str]:
        selected = self.filepath or self.directory
        context.scene.sharp_lab.input_path = selected
        return {"FINISHED"}


class SHARPLAB_OT_run(Operator):
    bl_idname = "sharplab.run"
    bl_label = "Run SHARP"
    bl_description = "Run Apple SHARP on the selected input"

    def execute(self, context: bpy.types.Context) -> set[str]:
        props = context.scene.sharp_lab
        prefs = _addon_prefs(context)
        input_raw = props.input_path.strip()
        if not input_raw:
            self.report({"ERROR"}, "Choose an input image or folder first.")
            return {"CANCELLED"}

        input_path = Path(input_raw).expanduser()
        if not input_path.exists():
            self.report({"ERROR"}, f"Input path does not exist: {input_path}")
            return {"CANCELLED"}

        progress_started = False
        try:
            runtime_dir = _ensure_workspace_runtime(context)
            executable = _configured_runtime_path(prefs)
            prefs.executable_path = str(executable)
            checkpoint = _configured_checkpoint_path(prefs)
            if not checkpoint.exists():
                props.status_message = "Downloading Apple SHARP model before the first run..."
                self.report({"INFO"}, "Downloading Apple SHARP model before the first run.")
                context.window_manager.progress_begin(0, 100)
                progress_started = True

                def progress_callback(downloaded: int, total: int | None) -> None:
                    percent = round(downloaded / total * 100, 1) if total else 0.0
                    props.model_download_active = True
                    props.model_download_percent = percent
                    props.model_download_detail = (
                        f"{downloaded:,} / {total:,} bytes" if total else f"{downloaded:,} bytes"
                    )
                    context.window_manager.progress_update(int(percent))

                checkpoint = _ensure_model_checkpoint(context, progress_callback=progress_callback)
                props.model_download_active = False
                props.model_download_percent = 100.0
                props.model_download_detail = ""
                props.status_message = f"Apple SHARP model ready at {checkpoint}."
            else:
                prefs.checkpoint_path = str(checkpoint.resolve())
                _set_setup_completed(prefs, True)

            props.status_message = "Running SHARP..."
            result = _run_sharp(context, input_path)
            props.last_run_id = result.run_id
            props.last_ply_path = str(result.ply_path)
            props.status_message = f"SHARP run {result.run_id} completed."
            if props.auto_import:
                _import_ply(result.ply_path)
        except Exception as exc:  # Blender operators need surfaced UI errors.
            props.status_message = str(exc)
            for line in _report_lines(str(exc))[:3]:
                self.report({"ERROR"}, line)
            return {"CANCELLED"}
        finally:
            if progress_started:
                context.window_manager.progress_end()
                props.model_download_active = False

        self.report({"INFO"}, f"SHARP run {result.run_id} completed.")
        return {"FINISHED"}


class SHARPLAB_OT_download_model(Operator):
    bl_idname = "sharplab.download_model"
    bl_label = "Download Model"
    bl_description = "Download the Apple SHARP checkpoint into the configured runtime"

    _timer: bpy.types.Timer | None = None

    def _redraw(self, context: bpy.types.Context) -> None:
        for window in context.window_manager.windows:
            screen = window.screen
            if screen is None:
                continue
            for area in screen.areas:
                area.tag_redraw()

    def _sync_state(self, context: bpy.types.Context) -> dict[str, object]:
        props = context.scene.sharp_lab
        prefs = _addon_prefs(context)
        state = _get_model_download_state()
        props.model_download_active = bool(state["active"])
        props.model_download_percent = float(state["percent"])
        total = state["total"]
        downloaded = int(state["downloaded"])
        if total:
            detail = f"{downloaded:,} / {int(total):,} bytes"
        elif downloaded:
            detail = f"{downloaded:,} bytes"
        else:
            detail = ""
        message = str(state["message"])
        props.model_download_detail = detail
        props.status_message = message or props.status_message
        if state["result_path"]:
            prefs.checkpoint_path = str(state["result_path"])
            _set_setup_completed(prefs, True)
        return state

    def _finish(self, context: bpy.types.Context) -> set[str]:
        wm = context.window_manager
        props = context.scene.sharp_lab
        state = self._sync_state(context)
        if self._timer is not None:
            wm.event_timer_remove(self._timer)
            self._timer = None
        wm.progress_end()
        props.model_download_active = False
        self._redraw(context)

        if state["error"]:
            for line in _report_lines(str(state["error"]))[:3]:
                self.report({"ERROR"}, line)
            _reset_model_download_state()
            return {"CANCELLED"}

        if state["result_path"]:
            self.report({"INFO"}, "Apple SHARP model downloaded.")
        _reset_model_download_state()
        return {"FINISHED"}

    def modal(self, context: bpy.types.Context, event: bpy.types.Event) -> set[str]:
        if event.type != "TIMER":
            return {"PASS_THROUGH"}

        state = self._sync_state(context)
        context.window_manager.progress_update(int(float(state["percent"])))
        self._redraw(context)
        if not state["active"]:
            return self._finish(context)
        return {"RUNNING_MODAL"}

    def execute(self, context: bpy.types.Context) -> set[str]:
        props = context.scene.sharp_lab
        prefs = _addon_prefs(context)
        state = _get_model_download_state()
        if state["active"]:
            self.report({"INFO"}, "The Apple SHARP model download is already running.")
            return {"CANCELLED"}

        try:
            runtime_dir = _ensure_workspace_runtime(context)
            executable = _configured_runtime_path(prefs)
            prefs.executable_path = str(executable)
            checkpoint = _configured_checkpoint_path(prefs)
            if checkpoint.exists():
                prefs.checkpoint_path = str(checkpoint.resolve())
                _set_setup_completed(prefs, True)
                props.status_message = "Apple SHARP model is ready."
                self.report({"INFO"}, "Apple SHARP model is already downloaded.")
                return {"FINISHED"}
        except Exception as exc:
            props.status_message = str(exc)
            for line in _report_lines(str(exc))[:3]:
                self.report({"ERROR"}, line)
            return {"CANCELLED"}

        _reset_model_download_state()
        props.model_download_active = True
        props.model_download_percent = 0.0
        props.model_download_detail = ""
        props.status_message = "Starting Apple SHARP model download..."

        service = _build_download_service(executable, checkpoint, prefs.default_device)

        def progress_callback(downloaded: int, total: int | None) -> None:
            percent = round(downloaded / total * 100, 1) if total else 0.0
            if total:
                message = f"Downloading Apple SHARP model... {percent:.1f}%"
            else:
                message = "Downloading Apple SHARP model..."
            _set_model_download_state(
                downloaded=downloaded,
                total=total,
                percent=percent,
                message=message,
            )

        def worker() -> None:
            try:
                checkpoint_path = service.download_default_checkpoint(progress_callback=progress_callback)
            except Exception as exc:
                _set_model_download_state(active=False, error=str(exc), message=str(exc))
                return
            _set_model_download_state(
                active=False,
                error="",
                result_path=str(checkpoint_path),
                percent=100.0,
                message=f"Model downloaded to {checkpoint_path}",
            )

        _set_model_download_state(active=True, message="Starting Apple SHARP model download...")
        threading.Thread(target=worker, daemon=True).start()
        wm = context.window_manager
        wm.progress_begin(0, 100)
        self._timer = wm.event_timer_add(0.2, window=context.window)
        wm.modal_handler_add(self)
        self._redraw(context)
        return {"RUNNING_MODAL"}


class SHARPLAB_OT_import_last_ply(Operator):
    bl_idname = "sharplab.import_last_ply"
    bl_label = "Import Last PLY"
    bl_description = "Import the PLY generated by the latest SHARP run"

    def execute(self, context: bpy.types.Context) -> set[str]:
        ply_raw = context.scene.sharp_lab.last_ply_path.strip()
        if not ply_raw:
            self.report({"ERROR"}, "No generated PLY is available yet.")
            return {"CANCELLED"}

        ply_path = Path(ply_raw).expanduser()
        if not ply_path.exists():
            self.report({"ERROR"}, f"PLY file not found: {ply_path}")
            return {"CANCELLED"}

        try:
            _import_ply(ply_path)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        self.report({"INFO"}, f"Imported {ply_path.name}")
        return {"FINISHED"}


class SHARPLAB_OT_open_preferences(Operator):
    bl_idname = "sharplab.open_preferences"
    bl_label = "Open Add-on Preferences"
    bl_description = "Open Blender preferences for this add-on"

    def execute(self, context: bpy.types.Context) -> set[str]:
        bpy.ops.preferences.addon_show(module=_addon_name())
        return {"FINISHED"}


class SHARPLAB_PT_panel(Panel):
    bl_label = "Sharp Lab"
    bl_idname = "SHARPLAB_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Sharp Lab"

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        props = context.scene.sharp_lab
        prefs = _addon_prefs(context)
        setup = _setup_status(prefs)
        configured_runtime = setup["runtime_path"]
        configured_checkpoint = setup["checkpoint_path"]
        bundled_runtime = bool(setup["bundled_runtime"])
        runtime_ready = bool(setup["runtime_ready"])
        checkpoint_ready = bool(setup["checkpoint_ready"])

        if not setup["setup_complete"]:
            setup_box = layout.box()
            setup_box.label(text="Sharp Lab Setup", icon="PREFERENCES")
            setup_box.label(text="Prepare the local runtime and Apple SHARP model once.")
            setup_box.label(text=f"Bundled Runtime: {'included' if bundled_runtime else 'missing'}")
            if runtime_ready:
                setup_box.label(text=f"Runtime: ready ({configured_runtime.name})")
            elif bundled_runtime:
                setup_box.label(text="Runtime: will be copied to your workspace")
            else:
                setup_box.label(text="Runtime: missing from this add-on package")
            setup_box.label(text=f"Model: {'ready' if checkpoint_ready else 'will be downloaded'}")
            setup_box.label(text=f"Workspace: {_workspace_root(prefs.workspace_path)}")
            setup_box.operator(
                "sharplab.download_model",
                icon="IMPORT",
                text="Set Up Sharp Lab" if not props.model_download_active else "Setting Up...",
            )
            setup_box.operator("sharplab.open_preferences", text="Advanced Settings", icon="PREFERENCES")

            if props.model_download_active or props.model_download_percent > 0:
                progress_box = layout.box()
                progress_box.label(text="Setup Progress")
                progress_box.prop(props, "model_download_percent", text="")
                if props.model_download_detail:
                    progress_box.label(text=props.model_download_detail)

            if props.status_message:
                info_box = layout.box()
                info_box.label(text="Status")
                for line in _report_lines(props.status_message)[:3]:
                    info_box.label(text=line)
            return

        col = layout.column(align=True)
        col.prop(props, "input_path")
        row = col.row(align=True)
        row.operator("sharplab.pick_image", text="Image")
        row.operator("sharplab.pick_folder", text="Folder")

        col = layout.column(align=True)
        col.prop(props, "auto_import")
        col.operator("sharplab.run", icon="PLAY")

        status_box = layout.box()
        status_box.label(text="Configuration")
        status_box.label(text=f"Bundled Runtime: {'included' if bundled_runtime else 'not needed'}")
        if runtime_ready:
            status_box.label(text=f"Runtime: ready ({configured_runtime.name})")
        elif bundled_runtime:
            status_box.label(text="Runtime: will prepare automatically")
        else:
            status_box.label(text="Runtime: missing")
        status_box.label(text=f"Model: {'ready' if checkpoint_ready else 'will download on run'}")
        status_box.label(text=f"Workspace: {_workspace_root(prefs.workspace_path)}")
        status_box.operator(
            "sharplab.download_model",
            icon="URL",
            text="Download Model" if not props.model_download_active else "Downloading Model...",
        )
        status_box.operator("sharplab.open_preferences", text="Edit Preferences", icon="PREFERENCES")

        if props.model_download_active or props.model_download_percent > 0:
            progress_box = layout.box()
            progress_box.label(text="Model Download")
            progress_box.prop(props, "model_download_percent", text="")
            if props.model_download_detail:
                progress_box.label(text=props.model_download_detail)

        if props.status_message:
            info_box = layout.box()
            info_box.label(text="Status")
            for line in _report_lines(props.status_message)[:3]:
                info_box.label(text=line)

        if props.last_run_id:
            result_box = layout.box()
            result_box.label(text=f"Last Run: {props.last_run_id}")
            if props.last_ply_path:
                result_box.label(text=Path(props.last_ply_path).name)
                result_box.operator("sharplab.import_last_ply", icon="IMPORT")


_CLASSES: Iterable[type] = (
    SharpLabAddonPreferences,
    SharpLabSceneProperties,
    SHARPLAB_OT_pick_image,
    SHARPLAB_OT_pick_folder,
    SHARPLAB_OT_run,
    SHARPLAB_OT_download_model,
    SHARPLAB_OT_import_last_ply,
    SHARPLAB_OT_open_preferences,
    SHARPLAB_PT_panel,
)


def register() -> None:
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.sharp_lab = PointerProperty(type=SharpLabSceneProperties)


def unregister() -> None:
    del bpy.types.Scene.sharp_lab
    for cls in reversed(tuple(_CLASSES)):
        bpy.utils.unregister_class(cls)
