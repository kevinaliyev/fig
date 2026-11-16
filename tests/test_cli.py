"""CLI End-to-End Tests with Refactored Command Names."""

import io
import os
import sys
import shutil
import tempfile
import unittest
from pathlib import Path
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch

from fig import __version__
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
        self.assertIn(f"fig {__version__}", buf.getvalue())

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

    @patch("fig.cli.clone_remote_repo")
    def test_cli_bootstrap_remote_git_url(self, mock_clone):
        mock_clone.return_value = self.repo_dir
        buf = io.StringIO()
        with redirect_stdout(buf):
            ret = main(["bootstrap", "gh:octocat/dotfiles", "--dest", str(self.tmp_dir / "custom_dest")])
            self.assertEqual(ret, 0)
        mock_clone.assert_called_once()
        args, kwargs = mock_clone.call_args
        self.assertEqual(args[0], "gh:octocat/dotfiles")
        self.assertEqual(kwargs.get("dest_dir"), (self.tmp_dir / "custom_dest").resolve())

    @patch("fig.cli.run_rebuilder")
    def test_cli_rebuild_command(self, mock_rebuilder):
        mock_rebuilder.return_value = self.repo_dir / "fig.toml"
        ret = main(["rebuild"])
        self.assertEqual(ret, 0)
        mock_rebuilder.assert_called_once()

    def test_cli_apply_cwd_vs_active_template_refresh(self):
        # 1. Bootstrap template first
        main(["bootstrap", str(self.repo_dir)])

        # 2. Run 'apply' from outside repo_dir (cwd has no fig.toml)
        buf = io.StringIO()
        with redirect_stdout(buf):
            ret = main(["apply"])
            self.assertEqual(ret, 0)
        output = buf.getvalue()
        self.assertIn("No 'fig.toml' found in current directory", output)
        self.assertIn("Refreshing current active template", output)

        # 3. Create a separate folder with its own fig.toml and cd into it
        other_repo = self.tmp_dir / "other_dotfiles"
        other_repo.mkdir()
        dest_other = self.mock_home / "other.ini"
        (other_repo / "other.ini").write_text("setting=1", encoding="utf-8")
        other_tpl = f"""
[meta]
name = "other-test"
[mappings]
"other.ini" = "{str(dest_other).replace(chr(92), '/')}"
"""
        (other_repo / "fig.toml").write_text(other_tpl, encoding="utf-8")

        orig_cwd = os.getcwd()
        try:
            os.chdir(str(other_repo))
            buf2 = io.StringIO()
            with redirect_stdout(buf2):
                ret2 = main(["apply"])
                self.assertEqual(ret2, 0)
            output2 = buf2.getvalue()
            self.assertIn("Found 'fig.toml' in current working directory", output2)
            self.assertTrue(dest_other.exists())
        finally:
            os.chdir(orig_cwd)


if __name__ == "__main__":
    unittest.main()
