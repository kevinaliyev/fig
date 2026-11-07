"""CLI End-to-End Tests."""

import io
import os
import sys
import shutil
import tempfile
import unittest
from pathlib import Path
from contextlib import redirect_stdout, redirect_stderr

from fig.cli import main
from fig.core.config import FigState


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

    def test_cli_bootstrap_apply_status_and_restore(self):
        # 1. Bootstrap
        buf = io.StringIO()
        with redirect_stdout(buf):
            ret = main(["bootstrap", str(self.repo_dir)])
            self.assertEqual(ret, 0)
        self.assertTrue(self.dest_ini.exists())
        self.assertEqual(self.dest_ini.read_text(encoding="utf-8"), "color=blue")

        # 2. Status
        buf = io.StringIO()
        with redirect_stdout(buf):
            ret = main(["status"])
            self.assertEqual(ret, 0)
        self.assertIn("[OK]", buf.getvalue())

        # 3. Apply without arguments (should apply active template)
        buf = io.StringIO()
        with redirect_stdout(buf):
            ret = main([])
            self.assertEqual(ret, 0)
        self.assertIn("Already synchronized", buf.getvalue())

        # 4. Backups list
        buf = io.StringIO()
        with redirect_stdout(buf):
            ret = main(["backups"])
            self.assertEqual(ret, 0)
        self.assertIn("Session ID:", buf.getvalue())

        # 5. Restore
        buf = io.StringIO()
        with redirect_stdout(buf):
            ret = main(["restore"])
            self.assertEqual(ret, 0)
        self.assertFalse(self.dest_ini.exists())

    def test_cli_borrow_and_unborrow(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            ret = main(["borrow", str(self.repo_dir)])
            self.assertEqual(ret, 0)
        self.assertTrue(self.dest_ini.exists())

        # Now unborrow
        buf = io.StringIO()
        with redirect_stdout(buf):
            ret = main(["unborrow"])
            self.assertEqual(ret, 0)
        self.assertFalse(self.dest_ini.exists())


if __name__ == "__main__":
    unittest.main()
