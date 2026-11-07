"""CLI End-to-End Tests with Refactored Command Names."""

import io
import os
import sys
import shutil
import tempfile
import unittest
from pathlib import Path
from contextlib import redirect_stdout, redirect_stderr

from fig.cli import main


class TestCLI(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="fig_test_cli_"))
        self.mock_home = self.tmp_dir / "user_home"
        self.mock_home.mkdir()

        # Set FIG_HOME env var so CLI uses our isolated directory
        self.fig_home = self.tmp_dir / "fig_home"
        os.environ["FIG_HOME"] = str(self.fig_home)

        # Mock dotfiles repo
        self.repo_dir = self.tmp_dir / "my_dotfiles"
        self.repo_dir.mkdir()
        (self.repo_dir / "config.ini").write_text("color=blue", encoding="utf-8")

        # Mock destination
        self.dest_ini = self.mock_home / "app_config.ini"

        # Template
        tpl = f"""
[meta]
name = "cli-test"

[mappings]
"config.ini" = "{str(self.dest_ini).replace(chr(92), '/')}"
"""
        (self.repo_dir / "fig.toml").write_text(tpl, encoding="utf-8")

    def tearDown(self):
        if "FIG_HOME" in os.environ:
            del os.environ["FIG_HOME"]
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_cli_version_and_help(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            with self.assertRaises(SystemExit) as cm:
                main(["--version"])
            self.assertEqual(cm.exception.code, 0)
        self.assertIn("fig 0.1.0", buf.getvalue())

    def test_cli_bootstrap_sync_check_and_undo(self):
        # 1. Bootstrap
        buf = io.StringIO()
        with redirect_stdout(buf):
            ret = main(["bootstrap", str(self.repo_dir)])
            self.assertEqual(ret, 0)
        self.assertTrue(self.dest_ini.exists())
        self.assertEqual(self.dest_ini.read_text(encoding="utf-8"), "color=blue")

        # 2. Check (replaces status)
        buf = io.StringIO()
        with redirect_stdout(buf):
            ret = main(["check"])
            self.assertEqual(ret, 0)
        self.assertIn("[OK]", buf.getvalue())

        # 3. Preview (replaces diff)
        buf = io.StringIO()
        with redirect_stdout(buf):
            ret = main(["preview"])
            self.assertEqual(ret, 0)
        self.assertIn("Preview Plan", buf.getvalue())

        # 4. Sync (or bare 'fig')
        buf = io.StringIO()
        with redirect_stdout(buf):
            ret = main(["sync"])
            self.assertEqual(ret, 0)
        self.assertIn("Already synchronized", buf.getvalue())

        # 5. History (replaces backups)
        buf = io.StringIO()
        with redirect_stdout(buf):
            ret = main(["history"])
            self.assertEqual(ret, 0)
        self.assertIn("Session ID:", buf.getvalue())

        # 6. Undo (replaces restore)
        buf = io.StringIO()
        with redirect_stdout(buf):
            ret = main(["undo"])
            self.assertEqual(ret, 0)
        self.assertFalse(self.dest_ini.exists())

    def test_cli_temp_and_revert(self):
        # Temp (replaces borrow)
        buf = io.StringIO()
        with redirect_stdout(buf):
            ret = main(["temp", str(self.repo_dir)])
            self.assertEqual(ret, 0)
        self.assertTrue(self.dest_ini.exists())

        # Revert (replaces unborrow)
        buf = io.StringIO()
        with redirect_stdout(buf):
            ret = main(["revert"])
            self.assertEqual(ret, 0)
        self.assertFalse(self.dest_ini.exists())


if __name__ == "__main__":
    unittest.main()
