# sharp_lab

`sharp_lab` is a local Python toolkit for experimenting with iPhone photos and preparing assets for Apple SHARP workflows. It ships as an installable package with a modular core so the current CLI can later sit beside a desktop or web UI without rewriting the processing logic.

## Features

- Installable Python project with `pyproject.toml`
- `src/` layout and console entry point: `sharp-lab`
- Modular services for discovery/import, preprocessing, export, and future SHARP integration
- Config file support with TOML or JSON
- Structured logging setup
- Test suite included for local verification
- Clean default project layout for local asset workflows

## Project layout

```text
sharp_lab/
├── pyproject.toml
├── README.md
├── .gitignore
├── src/
│   └── sharp_lab/
│       ├── cli.py
│       ├── config.py
│       ├── logging_utils.py
│       ├── discovery/
│       ├── pipeline/
│       ├── export/
│       ├── sharp/
│       └── ui/
└── tests/
```

## Installation

```bash
cd sharp_lab
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

## Quick start

Create a config file if you want to override defaults. `sharp_lab` prefers `sharp_lab.toml`, and also supports `sharp_lab.json` for environments where TOML parsing is not available:

```toml
# sharp_lab.toml
[paths]
workspace = "./workspace"
imports = "./workspace/imports"
processed = "./workspace/processed"
exports = "./workspace/exports"

[logging]
level = "INFO"
```

```json
{
  "paths": {
    "workspace": "./workspace",
    "imports": "./workspace/imports",
    "processed": "./workspace/processed",
    "exports": "./workspace/exports"
  },
  "logging": {
    "level": "INFO"
  }
}
```

Then run example commands:

```bash
sharp-lab discover --source ~/Pictures/iPhone
sharp-lab preprocess
sharp-lab export --name sharp-ready
sharp-lab sharp plan --bundle ./workspace/exports/sharp-ready
```

## Commands

- `sharp-lab discover --source <dir>`
  - Finds supported image files and copies them into the managed imports area.
- `sharp-lab preprocess`
  - Runs the default preprocessing pipeline against imported assets.
- `sharp-lab export --name <bundle-name>`
  - Creates an export bundle with processed assets and a manifest.
- `sharp-lab sharp plan --bundle <dir>`
  - Produces a placeholder SHARP submission plan for future integration work.
- `sharp-lab config-path`
  - Shows the resolved config file location.

## Architecture notes

The package is organized around reusable services rather than CLI-specific code:

- `sharp_lab.discovery`: source scanning and import logic
- `sharp_lab.pipeline`: preprocessing orchestration and pipeline steps
- `sharp_lab.export`: bundle creation and export manifests
- `sharp_lab.sharp`: placeholder boundary for future Apple SHARP integration
- `sharp_lab.ui`: reserved integration point for future UI adapters

The CLI is intentionally thin. A future UI can call the same service classes directly.

## Testing

```bash
python -m unittest discover -s tests -v
```

## Future work

- Add real image transforms backed by Pillow or pyvips
- Add metadata extraction for EXIF and capture device details
- Add concrete SHARP upload/auth flows
- Add desktop or web UI adapters on top of the service layer
