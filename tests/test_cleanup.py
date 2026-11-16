import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fig.config.state import FigState
from fig.utils.cleanup import CleanupManager
from fig import cli, __version__


class TestCleanupManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

        # Setup mock repo structure
        (self.root / "build").mkdir()
        (self.root / "dist").mkdir()
        (self.root / ".pytest_cache").mkdir()
        (self.root / "subpkg" / "__pycache__").mkdir(parents=True)
        (self.root / "subpkg" / "mod.pyc").write_text("bytecode")
        (self.root / "fig.toml").write_text("clutter")

        # Setup mock releases
        releases_dir = self.root / "releases"
        releases_dir.mkdir()
        (releases_dir / "fig-v0.4.0-windows-amd64").mkdir()
        (releases_dir / f"fig-v{__version__}-windows-amd64").mkdir()

        # Mock FigState in temp directory
        self.mock_fig_home = self.root / ".fig"
        self.mock_fig_home.mkdir()
        (self.mock_fig_home / "config.toml").write_text("test")
        (self.mock_fig_home / "backups").mkdir()
        (self.mock_fig_home / "backups" / "b1.txt").write_text("backup")

        self.state = FigState(fig_home=self.mock_fig_home)
        self.mgr = CleanupManager(self.state)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_clean_repo_artifacts_dry_run(self):
        res = self.mgr.clean_repo_artifacts(repo_root=self.root, clean_releases=True, dry_run=True)
        self.assertIn("fig.toml", res["clutter"])
        self.assertIn("build", res["build"])
        self.assertIn("dist", res["build"])
        self.assertTrue(any("mod.pyc" in c for c in res["caches"]))
        self.assertIn("fig-v0.4.0-windows-amd64", res["releases"])
        self.assertNotIn(f"fig-v{__version__}-windows-amd64", res["releases"])

        # In dry run, files must still exist
        self.assertTrue((self.root / "fig.toml").exists())
        self.assertTrue((self.root / "build").exists())

    def test_clean_repo_artifacts_execute(self):
        res = self.mgr.clean_repo_artifacts(repo_root=self.root, clean_releases=True, dry_run=False)
        self.assertIn("fig.toml", res["clutter"])
        self.assertFalse((self.root / "fig.toml").exists())
        self.assertFalse((self.root / "build").exists())
        self.assertFalse((self.root / "dist").exists())
        self.assertFalse((self.root / "releases" / "fig-v0.4.0-windows-amd64").exists())
        self.assertTrue((self.root / "releases" / f"fig-v{__version__}-windows-amd64").exists())

    def test_purge_user_state(self):
        with patch("fig.utils.cleanup.get_fig_home", return_value=self.mock_fig_home):
            purged = self.mgr.purge_user_state(preserve_backups=False, dry_run=False)
            self.assertTrue(len(purged) > 0)
            self.assertFalse(self.mock_fig_home.exists())

    def test_cli_clean_preview(self):
        with patch.object(sys, "argv", ["fig", "clean", "--preview"]):
            exit_code = cli.main(["clean", "--preview"])
            self.assertEqual(exit_code, 0)

    def test_cli_uninstall_preview(self):
        with patch.object(sys, "argv", ["fig", "uninstall", "--preview"]):
            exit_code = cli.main(["uninstall", "--preview"])
            self.assertEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()
