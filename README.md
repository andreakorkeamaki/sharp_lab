# sharp_lab

`sharp_lab` is a local Python toolkit for experimenting with iPhone photos and preparing assets for Apple SHARP workflows. It ships as an installable package with a modular core so the current CLI, local web UI, and any future desktop or hosted frontend can reuse the same services.

## Features

- Installable Python project with `pyproject.toml`
- `src/` layout and console entry point: `sharp-lab`
- Modular services for discovery/import, preprocessing, export, and local SHARP execution
- Config file support with TOML or JSON
- Structured logging setup
- Local web UI for launching SHARP runs and previewing 3DGS output in the browser
- Editor controls for orientation fixes, fly-through navigation, and PLY decimation copies
- Test suite included for local verification
- Clean default project layout for local asset workflows

## Project layout

```text
sharp_lab/
├── pyproject.toml
├── README.md
├── .gitignore
├── web_viewer/
├── src/
│   └── sharp_lab/
│       ├── app.py
│       ├── cli.py
│       ├── config.py
│       ├── discovery/
│       ├── pipeline/
│       ├── export/
│       ├── sharp/
│       └── ui/
└── tests/
```

## Installation

### Download from GitHub releases

For the simplest macOS or Windows install, download the latest release asset from GitHub:

- `sharp-lab-macos.zip`
- `sharp-lab-windows.zip`

Unzip it and run:

```bash
sharp-lab studio
```

That starts the local web UI and opens it in your default browser automatically.

The repo includes a release workflow at `.github/workflows/release.yml`. Pushing a tag like `v0.1.0` builds:

- a source distribution
- a wheel
- a standalone macOS executable zip
- a standalone Windows executable zip

### Install from source

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
runs = "./workspace/runs"

[logging]
level = "INFO"

[sharp]
executable = "/Users/andreakorkeamaki/Desktop/ml-sharp/run-sharp"
checkpoint = "/Users/andreakorkeamaki/Desktop/ml-sharp/models/sharp_2572gikvuh.pt"
default_device = "cpu"

[web]
host = "127.0.0.1"
port = 4173
```

```json
{
  "paths": {
    "workspace": "./workspace",
    "imports": "./workspace/imports",
    "processed": "./workspace/processed",
    "exports": "./workspace/exports",
    "runs": "./workspace/runs"
  },
  "logging": {
    "level": "INFO"
  },
  "sharp": {
    "executable": "/Users/andreakorkeamaki/Desktop/ml-sharp/run-sharp",
    "checkpoint": "/Users/andreakorkeamaki/Desktop/ml-sharp/models/sharp_2572gikvuh.pt",
    "default_device": "cpu"
  },
  "web": {
    "host": "127.0.0.1",
    "port": 4173
  }
}
```

## Core commands

```bash
sharp-lab sharp status
sharp-lab sharp predict --input /Users/andreakorkeamaki/Desktop/applesharp
sharp-lab sharp runs
sharp-lab web
sharp-lab studio
```

What these do:

- `sharp-lab sharp status`
  - Shows whether the local SHARP executable and checkpoint are available.
- `sharp-lab sharp predict --input <path>`
  - Runs the local SHARP CLI and stores a tracked run in `workspace/runs/<run-id>/`.
- `sharp-lab sharp runs`
  - Lists previous local SHARP runs and their manifests.
- `sharp-lab web`
  - Starts the local browser UI so you can run SHARP and inspect generated splats in one place.
- `sharp-lab studio`
  - Starts the local browser UI and opens it automatically in your default browser.

## Local web UI

Start the UI:

```bash
sharp-lab web
```

Then open:

```text
http://127.0.0.1:4173
```

The local UI can:

- trigger SHARP against a local image or folder path
- save each run under `workspace/runs/`
- keep a `run.json` manifest and a `sharp.log` for each run
- preview the generated `.ply` directly in the browser with Spark
- apply quick orientation fixes when the splat appears upside down or mirrored
- create decimated `.ply` copies for lighter exports while keeping the original run output

This UI is local-first. SHARP inference still runs on your machine. The browser is only a frontend.

## Standalone viewer

The repo also includes a static splat viewer in `web_viewer/`. It is useful as a separate experiment or for hosting a viewer-only frontend later, but `sharp-lab web` is the integrated local workflow.

## Architecture notes

The package is organized around reusable services rather than CLI-specific code:

- `sharp_lab.discovery`: source scanning and import logic
- `sharp_lab.pipeline`: preprocessing orchestration and pipeline steps
- `sharp_lab.export`: bundle creation and export manifests
- `sharp_lab.sharp`: local SHARP execution, run tracking, and future Apple SHARP integration
- `sharp_lab.ui`: local web server and packaged browser UI

The CLI is intentionally thin. The web UI calls the same application facade and SHARP service classes used by the CLI.

## Testing

```bash
python -m unittest discover -s tests -v
```

## Future work

- Add real image transforms backed by Pillow or pyvips
- Add metadata extraction for EXIF and capture device details
- Add conversion/export helpers for web-optimized splat formats
- Add desktop or hosted UI adapters on top of the same service layer
