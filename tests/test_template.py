"""Tests for Template Engine with OS-Specific Declarations."""

import shutil
import tempfile
import unittest
from pathlib import Path

from fig.core.platform import OperatingSystem
from fig.core.template import Template, discover_template, generate_default_template


class TestTemplate(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="fig_test_tpl_"))
        self.repo_dir = self.tmp_dir / "dotfiles"
        self.repo_dir.mkdir()

        # Create mock dotfiles in repo
        (self.repo_dir / ".gitconfig").write_text("[user]\nname = Test", encoding="utf-8")
        (self.repo_dir / "wezterm_win.lua").write_text("powershell=true", encoding="utf-8")
        (self.repo_dir / "wezterm_linux.lua").write_text("bash=true", encoding="utf-8")
        (self.repo_dir / "shared.conf").write_text("common=1", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_os_specific_mappings_resolution(self):
        tpl_path = self.repo_dir / "fig.toml"
        toml_content = """
[meta]
name = "cross-platform-test"

[mappings]
"shared.conf" = "~/shared.conf"

[os.windows.mappings]
"wezterm_win.lua" = "~/.config/wezterm/wezterm.lua"

[os.linux.mappings]
"wezterm_linux.lua" = "~/.config/wezterm/wezterm.lua"
"""
        tpl_path.write_text(toml_content, encoding="utf-8")
        tpl = Template.load(tpl_path)

        # 1. Resolve for Windows
        plan_win = tpl.resolve_plan(self.repo_dir, target_os=OperatingSystem.WINDOWS)
        win_sources = [src.name for src, _ in plan_win]
        self.assertIn("shared.conf", win_sources)
        self.assertIn("wezterm_win.lua", win_sources)
        self.assertNotIn("wezterm_linux.lua", win_sources)

        # 2. Resolve for Linux
        plan_linux = tpl.resolve_plan(self.repo_dir, target_os=OperatingSystem.LINUX)
        linux_sources = [src.name for src, _ in plan_linux]
        self.assertIn("shared.conf", linux_sources)
        self.assertIn("wezterm_linux.lua", linux_sources)
        self.assertNotIn("wezterm_win.lua", linux_sources)

    def test_save_and_load_with_os_mappings(self):
        tpl = Template(
            name="os-save-test",
            mappings={"shared.txt": "~/shared.txt"},
            os_mappings={
                "windows": {"win_tool.ini": "%APPDATA%/tool.ini"},
                "linux": {"lin_tool.ini": "~/.config/tool.ini"},
            },
            presets=["git"],
        )
        out_path = self.repo_dir / "fig.toml"
        tpl.save(out_path)

        loaded = Template.load(out_path)
        self.assertEqual(loaded.name, "os-save-test")
        self.assertIn("shared.txt", loaded.mappings)
        self.assertIn("windows", loaded.os_mappings)
        self.assertIn("win_tool.ini", loaded.os_mappings["windows"])
        self.assertIn("linux", loaded.os_mappings)
        self.assertIn("lin_tool.ini", loaded.os_mappings["linux"])

    def test_auto_generate_template(self):
        tpl = generate_default_template(self.repo_dir)
        self.assertIn("git", tpl.presets)
        self.assertIn(".gitconfig", tpl.mappings)


if __name__ == "__main__":
    unittest.main()
