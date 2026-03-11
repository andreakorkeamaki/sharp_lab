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

For the simplest macOS or Windows install, download the latest full release asset from GitHub:

- `sharp-lab-macos.zip`
- `sharp-lab-windows.zip`

The release workflow now also produces:

- `sharp-lab-macos-lite.zip`
- `sharp-lab-windows-lite.zip`
- `sharp-lab-runtime-macos.zip`
- `sharp-lab-runtime-windows.zip`

Unzip it and launch:

- Windows: double-click `Sharp Lab.exe`
- macOS: open `Sharp Lab`

The full packaged app starts the local studio UI and opens it in your default browser automatically. The Lite build opens a setup-first page instead. On Windows, the Lite setup now bootstraps a local Python runtime and installs SHARP into the app folder on demand, instead of relying on a bundled virtual environment. Each release zip also includes `sharp_lab.example.json` so you can override paths without editing source code.

The release workflow now builds a bundled `ml-sharp` runtime from the pinned Apple source revision. The full app zip includes it directly, while the Lite zip keeps the initial download smaller. On Windows, the Lite release bootstraps Python and SHARP locally on first setup; on other platforms, the Lite flow can still fetch a portable runtime archive. The model checkpoint itself is still optional, because the app can download it during onboarding.

If you want to prepare the runtime bundle manually instead, use a top-level `runtime/` folder before building the release:

```text
runtime/
├── run-sharp          # macOS/Linux
├── run-sharp.exe      # Windows
└── models/
    └── sharp_2572gikvuh.pt
```

When that folder exists, the release workflow bundles it into the downloadable zip and the app auto-detects it on launch. Otherwise the workflow creates the runtime bundle itself from `apple/ml-sharp`.

If the SHARP executable is present but the checkpoint file is not bundled, the app now offers a first-run "Download Apple Model" action in the UI. In the Lite build, the setup page also offers an "Install Runtime" action before you enter the studio. On Windows, that action performs a full local bootstrap of Python and SHARP inside the app folder, then validates the install before unlocking the studio. You can also let the SHARP CLI download the checkpoint automatically on the first prediction run and cache it under `~/.cache/torch/hub/checkpoints/`.

The repo includes a release workflow at `.github/workflows/release.yml`. Pushing a tag like `v0.1.5` builds:

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
executable = "./runtime/run-sharp"
checkpoint = "./runtime/models/sharp_2572gikvuh.pt"
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
    "executable": "./runtime/run-sharp",
    "checkpoint": "./runtime/models/sharp_2572gikvuh.pt",
    "default_device": "cpu"
  },
  "web": {
    "host": "127.0.0.1",
    "port": 4173
  }
}
```

On Windows, use `./runtime/run-sharp.exe` if you create a config file manually. The packaged app also checks for `run-sharp.exe` automatically.

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
