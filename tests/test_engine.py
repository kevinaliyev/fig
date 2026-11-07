"""End-to-End Integration Tests for Fig Engine."""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from fig.core.config import FigState
from fig.core.engine import FigEngine


class TestFigEngineIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="fig_test_e2e_"))

        # Setup mock FIG_HOME
        self.fig_home = self.tmp_dir / ".fig"
        self.state = FigState(self.fig_home)
        self.engine = FigEngine(self.state)

        # Setup mock user dotfile repo
        self.repo_dir = self.tmp_dir / "dotfiles"
        self.repo_dir.mkdir()
        (self.repo_dir / ".gitconfig").write_text("[user]\nname = Jane", encoding="utf-8")
        (self.repo_dir / ".zshrc").write_text("export THEME=awesome", encoding="utf-8")

        # Mock target system destination directory (acting as mock $HOME)
        self.mock_sys_home = self.tmp_dir / "mock_home"
        self.mock_sys_home.mkdir()

        # Existing file on system that will conflict
        self.existing_sys_zshrc = self.mock_sys_home / ".zshrc"
        self.existing_sys_zshrc.write_text("export OLD_SETTING=1", encoding="utf-8")

        # Write custom template to point to our mock home
        tpl_content = f"""
[meta]
name = "test-repo"

[settings]
link_mode = "auto"
backup_on_collision = true

[mappings]
".gitconfig" = "{str(self.mock_sys_home / '.gitconfig').replace(chr(92), '/')}"
".zshrc" = "{str(self.existing_sys_zshrc).replace(chr(92), '/')}"
"""
        (self.repo_dir / "fig.toml").write_text(tpl_content, encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_bootstrap_idempotent_apply_and_restore(self):
        # 1. Bootstrap
        res_boot = self.engine.bootstrap(self.repo_dir)
        self.assertTrue(res_boot.is_success)
        self.assertIsNotNone(res_boot.backup_id)
        # Should have backed up .zshrc
        self.assertEqual(len(res_boot.backed_up), 1)

        # Destination .zshrc should now have the dotfile repo content
        self.assertEqual(self.existing_sys_zshrc.read_text(encoding="utf-8"), "export THEME=awesome")
        # Destination .gitconfig should now exist
        target_gitconfig = self.mock_sys_home / ".gitconfig"
        self.assertTrue(target_gitconfig.exists())
        self.assertEqual(target_gitconfig.read_text(encoding="utf-8"), "[user]\nname = Jane")

        # 2. Idempotent Apply (running apply right after bootstrap)
        res_apply = self.engine.apply()
        self.assertTrue(res_apply.is_success)
        # Both files should be ALREADY_LINKED
        self.assertEqual(len(res_apply.already_linked), 2)
        self.assertEqual(len(res_apply.created), 0)

        # 3. Status check
        st = self.engine.status()
        self.assertIsNotNone(st.get("active_template"))
        self.assertEqual(len(st.get("mappings", [])), 2)

        # 4. Restore
        restored, removed_new = self.engine.restore_backup(res_boot.backup_id)
        # Original .zshrc should be back!
        self.assertEqual(self.existing_sys_zshrc.read_text(encoding="utf-8"), "export OLD_SETTING=1")
        # Newly created .gitconfig should be removed!
        self.assertFalse(target_gitconfig.exists())


if __name__ == "__main__":
    unittest.main()
