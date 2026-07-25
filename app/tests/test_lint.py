import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase


class RuffLintTest(SimpleTestCase):
    """Run ruff over the codebase so lint failures fail the test suite.

    Ruff is configured via ``app/ruff.toml``. Wiring it into ``manage.py test``
    keeps a single command as the source of truth for both behaviour and style.

    Uses ``SimpleTestCase`` (no database needed) so it runs even in a lean
    environment and stays fast.
    """

    def test_ruff_check_passes(self):
        # tests/ sits directly under app/, so its parent is the app root
        # (/app inside the dev container, where ruff.toml lives).
        app_root = Path(__file__).resolve().parent.parent

        result = subprocess.run(
            [sys.executable, "-m", "ruff", "check", "."],
            cwd=app_root,
            capture_output=True,
            text=True,
        )

        self.assertEqual(
            result.returncode,
            0,
            "ruff found lint errors (run `ruff check . --fix` to auto-fix):\n"
            f"{result.stdout}\n{result.stderr}",
        )
