from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    tomllib = None

DEFAULT_CONFIG_FILE = "sharp_lab.toml"
FALLBACK_CONFIG_FILE = "sharp_lab.json"


@dataclass
class PathConfig:
    workspace: Path
    imports: Path
    processed: Path
    exports: Path
    runs: Path


@dataclass
class LoggingConfig:
    level: str = "INFO"


@dataclass
class SharpConfig:
    executable: Path
    checkpoint: Path | None = None
    default_device: str = "cpu"


@dataclass
class WebConfig:
    host: str = "127.0.0.1"
    port: int = 4173


@dataclass
class SharpLabConfig:
    paths: PathConfig
    logging: LoggingConfig
    sharp: SharpConfig
    web: WebConfig
    config_file: Path | None = None

    @classmethod
    def default(cls, base_dir: Path | None = None) -> "SharpLabConfig":
        root = (base_dir or Path.cwd()).resolve()
        workspace = root / "workspace"
        default_sharp_root = Path.home() / "Desktop" / "ml-sharp"
        default_executable = default_sharp_root / "run-sharp"
        default_checkpoint = default_sharp_root / "models" / "sharp_2572gikvuh.pt"
        checkpoint = default_checkpoint if default_checkpoint.exists() else None
        return cls(
            paths=PathConfig(
                workspace=workspace,
                imports=workspace / "imports",
                processed=workspace / "processed",
                exports=workspace / "exports",
                runs=workspace / "runs",
            ),
            logging=LoggingConfig(),
            sharp=SharpConfig(
                executable=default_executable,
                checkpoint=checkpoint,
                default_device="cpu",
            ),
            web=WebConfig(),
            config_file=None,
        )

    @classmethod
    def load(cls, config_path: str | Path | None = None, base_dir: Path | None = None) -> "SharpLabConfig":
        default_config = cls.default(base_dir=base_dir)
        root = (base_dir or Path.cwd()).resolve()
        resolved_path = _select_config_path(config_path, root)

        if not resolved_path.exists():
            default_config.config_file = resolved_path
            return default_config

        raw = _load_config_data(resolved_path)

        path_section = raw.get("paths", {})
        logging_section = raw.get("logging", {})
        sharp_section = raw.get("sharp", {})
        web_section = raw.get("web", {})

        workspace = _resolve_path(path_section.get("workspace", default_config.paths.workspace), root)
        imports = _resolve_path(path_section.get("imports", workspace / "imports"), root)
        processed = _resolve_path(path_section.get("processed", workspace / "processed"), root)
        exports = _resolve_path(path_section.get("exports", workspace / "exports"), root)
        runs = _resolve_path(path_section.get("runs", workspace / "runs"), root)

        executable = _resolve_path(sharp_section.get("executable", default_config.sharp.executable), root)
        checkpoint_value = sharp_section.get("checkpoint")
        checkpoint = default_config.sharp.checkpoint
        if checkpoint_value is not None:
            checkpoint = _resolve_path(checkpoint_value, root)

        return cls(
            paths=PathConfig(
                workspace=workspace,
                imports=imports,
                processed=processed,
                exports=exports,
                runs=runs,
            ),
            logging=LoggingConfig(level=str(logging_section.get("level", "INFO")).upper()),
            sharp=SharpConfig(
                executable=executable,
                checkpoint=checkpoint,
                default_device=str(sharp_section.get("default_device", default_config.sharp.default_device)),
            ),
            web=WebConfig(
                host=str(web_section.get("host", default_config.web.host)),
                port=int(web_section.get("port", default_config.web.port)),
            ),
            config_file=resolved_path.resolve(),
        )

    def ensure_directories(self) -> None:
        for path in (
            self.paths.workspace,
            self.paths.imports,
            self.paths.processed,
            self.paths.exports,
            self.paths.runs,
        ):
            path.mkdir(parents=True, exist_ok=True)


def _resolve_path(value: str | Path, root: Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (root / path).resolve()


def _select_config_path(config_path: str | Path | None, root: Path) -> Path:
    if config_path:
        return Path(config_path).expanduser()

    toml_path = root / DEFAULT_CONFIG_FILE
    json_path = root / FALLBACK_CONFIG_FILE
    if toml_path.exists():
        return toml_path
    if json_path.exists():
        return json_path
    return toml_path


def _load_config_data(config_path: Path) -> dict[str, object]:
    if config_path.suffix.lower() == ".json":
        return json.loads(config_path.read_text(encoding="utf-8"))

    if config_path.suffix.lower() == ".toml":
        if tomllib is None:
            raise RuntimeError(
                "TOML config requires Python 3.11+ in this environment. "
                "Use sharp_lab.json or pass a JSON config file."
            )
        with config_path.open("rb") as handle:
            return tomllib.load(handle)

    raise ValueError(f"Unsupported config format: {config_path.suffix}")
