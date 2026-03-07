from __future__ import annotations

from pathlib import Path


class SharpIntegrationService:
    """Placeholder boundary for future Apple SHARP integration work."""

    def plan_submission(self, bundle_dir: Path) -> dict[str, object]:
        assets_dir = bundle_dir / "assets"
        asset_count = len([path for path in assets_dir.iterdir()]) if assets_dir.exists() else 0
        return {
            "status": "planned",
            "bundle_dir": str(bundle_dir),
            "asset_count": asset_count,
            "next_steps": [
                "Validate export metadata",
                "Attach SHARP-specific annotations",
                "Implement authenticated upload workflow",
            ],
        }
