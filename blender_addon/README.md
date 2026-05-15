# Blender add-on

This folder contains the Blender wrapper for `sharp_lab`.

Build the installable `.zip` from the repo root:

```bash
python scripts/build_blender_addon.py
```

The script writes the archive to `dist/sharp-lab-blender-addon.zip`.

For CI or release builds, point it at a prepared runtime directory:

```bash
python scripts/build_blender_addon.py --runtime-dir runtime --output dist/sharp-lab-blender-addon-macos-<tag>.zip
```

On Windows, build the portable add-on with:

```bash
python scripts/build_blender_addon_windows.py --runtime-dir runtime --python-nupkg dist/python.3.11.9.nupkg --output dist/sharp-lab-blender-addon-windows-<tag>.zip
```

Install it in Blender with:

1. `Edit > Preferences > Add-ons`
2. `Install...`
3. Choose `dist/sharp-lab-blender-addon.zip`
4. Enable `Sharp Lab`

After enabling:

1. Open the `Sharp Lab` tab in the 3D View sidebar.
2. Choose an image or folder in the panel and run SHARP.
3. The add-on prepares the bundled SHARP runtime inside the workspace automatically.
4. If the Apple SHARP checkpoint is not present yet, the first run downloads it into that runtime automatically.
5. The generated `.ply` is imported into the current Blender scene.

You do not need to point Blender manually at `run-sharp` when using the bundled build. The add-on copies the bundled runtime into the workspace automatically and fills the executable and checkpoint paths there. The `Download Model` button is still available if you want to prepare the checkpoint before the first run.
