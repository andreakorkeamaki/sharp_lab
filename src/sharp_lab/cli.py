from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from sharp_lab.app import SharpLabApplication
from sharp_lab.config import SharpLabConfig
from sharp_lab.logging_utils import setup_logging

LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sharp-lab", description="Asset preparation tools for local SHARP experiments.")
    parser.add_argument("--config", help="Path to a sharp_lab TOML config file.")
    parser.add_argument("--log-level", help="Override configured log level.")

    subparsers = parser.add_subparsers(dest="command", required=True)

    discover_parser = subparsers.add_parser("discover", help="Discover and import supported images.")
    discover_parser.add_argument("--source", required=True, help="Directory to scan for image files.")

    subparsers.add_parser("preprocess", help="Run the preprocessing pipeline.")

    export_parser = subparsers.add_parser("export", help="Create an export bundle from processed assets.")
    export_parser.add_argument("--name", required=True, help="Export bundle name.")

    sharp_parser = subparsers.add_parser("sharp", help="Future SHARP integration commands.")
    sharp_subparsers = sharp_parser.add_subparsers(dest="sharp_command", required=True)
    sharp_plan_parser = sharp_subparsers.add_parser("plan", help="Create a SHARP submission plan from a bundle.")
    sharp_plan_parser.add_argument("--bundle", required=True, help="Bundle directory to inspect.")

    subparsers.add_parser("config-path", help="Show the resolved config file path.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    config = SharpLabConfig.load(args.config)
    setup_logging(args.log_level or config.logging.level)
    app = SharpLabApplication(config)

    if args.command == "discover":
        imported_count = app.discover(Path(args.source).expanduser())
        print(f"Imported {imported_count} image(s) into {config.paths.imports}")
        return 0

    if args.command == "preprocess":
        processed_count = app.preprocess()
        print(f"Processed {processed_count} image(s) into {config.paths.processed}")
        return 0

    if args.command == "export":
        bundle_dir = app.export(args.name)
        print(f"Created export bundle at {bundle_dir}")
        return 0

    if args.command == "sharp":
        if args.sharp_command == "plan":
            plan = app.sharp_plan(Path(args.bundle).expanduser())
            print(json.dumps(plan, indent=2))
            return 0

    if args.command == "config-path":
        resolved = config.config_file or (Path.cwd() / "sharp_lab.toml")
        print(resolved)
        return 0

    LOGGER.error("Unknown command: %s", args.command)
    return 1
