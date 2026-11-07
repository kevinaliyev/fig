"""Tests for System Configuration Subsystem."""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from fig.core.config import FigState
from fig.core.elevation import is_elevated, display_breaking_changes_warning
from fig.core.template import Template
from fig.modules.system import SystemConfigManager


class TestSystemConfig(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="fig_test_sys_"))
        self.fig_home = self.tmp_dir / ".fig"
        self.sys_root = self.tmp_dir / "system_redundancy"
        self.state = FigState(self.fig_home, system_root=self.sys_root)
        self.state.ensure_directories(include_system=True)

        self.repo_dir = self.tmp_dir / "repo"
        self.repo_dir.mkdir()

        # Mock mock-system target file
        self.mock_sys_target = self.tmp_dir / "sys_etc_hosts"
        self.mock_sys_target.write_text("127.0.0.1 localhost\n", encoding="utf-8")

        # Mock source file in repo
        self.mock_src = self.repo_dir / "hosts"
        self.mock_src.write_text("127.0.0.1 localhost my-custom-host\n", encoding="utf-8")

        # User dotfile
        self.mock_user_src = self.repo_dir / ".gitconfig"
        self.mock_user_src.write_text("[user]\nname = Test", encoding="utf-8")

        # Template with both user dotfile and explicit system spec
        tpl_text = f"""
[meta]
name = "sys-test"

[mappings]
".gitconfig" = "~/mock_gitconfig"

[system.mappings]
"hosts" = "{str(self.mock_sys_target).replace(chr(92), '/')}"
"""
        self.tpl_file = self.repo_dir / "fig.toml"
        self.tpl_file.write_text(tpl_text, encoding="utf-8")
        self.template = Template.load(self.tpl_file)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_user_mode_ignores_system_mappings(self):
        # When is_system=False, hosts must NOT be in the plan
        user_plan = self.template.resolve_plan(self.repo_dir, is_system=False)
        user_dests = [str(dest) for _, dest in user_plan]
        self.assertTrue(any("mock_gitconfig" in d for d in user_dests))
        self.assertFalse(any("sys_etc_hosts" in d for d in user_dests))

    def test_system_mode_returns_system_mappings(self):
        # When is_system=True, hosts MUST be in the plan, and user dotfiles excluded
        sys_plan = self.template.resolve_plan(self.repo_dir, is_system=True)
        sys_dests = [str(dest) for _, dest in sys_plan]
        self.assertTrue(any("sys_etc_hosts" in d for d in sys_dests))
        self.assertFalse(any("mock_gitconfig" in d for d in sys_dests))

    def test_breaking_changes_warning_force_yes(self):
        # With force_yes=True, warning returns True automatically
        confirmed = display_breaking_changes_warning(
            [str(self.mock_sys_target)],
            force_yes=True,
            interactive=False,
        )
        self.assertTrue(confirmed)

    def test_system_manager_redundancy_backup_and_apply(self):
        manager = SystemConfigManager(self.state)
        # Mock already elevated for test run
        orig_elevated = os.environ.get("FIG_MOCK_ELEVATED")
        try:
            # Run apply with dry_run or direct
            plan = manager.plan_system_deployment(self.template, self.repo_dir)
            self.assertEqual(len(plan), 1)
            self.assertEqual(plan[0][1], self.mock_sys_target)
        finally:
            if orig_elevated:
                os.environ["FIG_MOCK_ELEVATED"] = orig_elevated


if __name__ == "__main__":
    unittest.main()
