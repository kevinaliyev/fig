"""Tests for Pathspec and Repository Scanner."""

import shutil
import tempfile
import unittest
from pathlib import Path

from fig.modules.scanner import RepoScanner, parse_pathspec_file


class TestScanner(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="fig_test_scan_"))
        self.repo_dir = self.tmp_dir / "my_dotfiles"
        self.repo_dir.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_parse_pathspec_single_line(self):
        ps_file = self.repo_dir / "pathspec.txt"
        ps_file.write_text("~/.local/share/my_app\n", encoding="utf-8")
        res, is_sys = parse_pathspec_file(ps_file)
        self.assertEqual(res.get("universal"), "~/.local/share/my_app")
        self.assertFalse(is_sys)

    def test_parse_pathspec_multi_platform(self):
        ps_file = self.repo_dir / "pathspec.txt"
        content = """
# App pathspec
windows = %APPDATA%/my_app
linux = ~/.config/my_app
macos = ~/Library/Application Support/my_app
"""
        ps_file.write_text(content, encoding="utf-8")
        res, is_sys = parse_pathspec_file(ps_file)
        self.assertEqual(res.get("windows"), "%APPDATA%/my_app")
        self.assertEqual(res.get("linux"), "~/.config/my_app")
        self.assertEqual(res.get("macos"), "~/Library/Application Support/my_app")

    def test_scan_nested_nvim_directory(self):
        # Create nvim with nested dirs
        nvim_dir = self.repo_dir / "nvim"
        (nvim_dir / "lua" / "config").mkdir(parents=True)
        (nvim_dir / "init.lua").write_text("-- init lua", encoding="utf-8")
        (nvim_dir / "lua" / "config" / "settings.lua").write_text("-- settings", encoding="utf-8")

        scanner = RepoScanner(self.repo_dir)
        configs = scanner.scan()

        # Nvim should be detected as a directory link, not individual file links
        nvim_items = [c for c in configs if c.app_name.lower() in ("nvim", "neovim")]
        self.assertTrue(len(nvim_items) > 0)
        self.assertTrue(any(c.is_directory for c in nvim_items))

    def test_scan_with_pathspec_directory(self):
        custom_app = self.repo_dir / "nonstandard_tool"
        custom_app.mkdir()
        (custom_app / "settings.json").write_text("{}", encoding="utf-8")
        (custom_app / "pathspec.txt").write_text("~/.opt/nonstandard_tool\n", encoding="utf-8")

        scanner = RepoScanner(self.repo_dir)
        configs = scanner.scan()

        tool_items = [c for c in configs if c.app_name == "nonstandard_tool"]
        self.assertEqual(len(tool_items), 1)
        self.assertEqual(tool_items[0].dest_expr, "~/.opt/nonstandard_tool")
        self.assertEqual(tool_items[0].detection_source, "pathspec.txt")


if __name__ == "__main__":
    unittest.main()
