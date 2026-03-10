import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sharp_lab.cli import _resolve_argv


class CLITests(unittest.TestCase):
    def test_packaged_app_defaults_to_studio_without_arguments(self) -> None:
        self.assertEqual(_resolve_argv(None, runtime_argv=[], frozen=True), ["studio"])

    def test_existing_arguments_are_preserved(self) -> None:
        self.assertEqual(_resolve_argv(["sharp", "status"], runtime_argv=[], frozen=True), ["sharp", "status"])
        self.assertEqual(_resolve_argv(None, runtime_argv=["web"], frozen=True), ["web"])
