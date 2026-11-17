"""Tests for Pathspec and Repository Scanner."""

import shutil
import tempfile
import unittest
from pathlib import Path

from fig.builder.scanner import RepoScanner, parse_pathspec_file


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
        res, is_sys, meta = parse_pathspec_file(ps_file)
        self.assertEqual(res.get("universal"), "~/.local/share/my_app")
        self.assertFalse(is_sys)

    def test_parse_pathspec_multi_platform(self):
        ps_file = self.repo_dir / "pathspec.txt"
        content = """
# App pathspec
windows = %APPDATA%/my_app
linux = ~/.config/my_app
macos = ~/Library/Application Support/my_app
link_mode = symlink
type = dir
"""
        ps_file.write_text(content, encoding="utf-8")
        res, is_sys, meta = parse_pathspec_file(ps_file)
        self.assertEqual(res.get("windows"), "%APPDATA%/my_app")
        self.assertEqual(res.get("linux"), "~/.config/my_app")
        self.assertEqual(res.get("macos"), "~/Library/Application Support/my_app")
        self.assertEqual(meta.get("link_mode"), "symlink")
        self.assertTrue(meta.get("is_directory"))

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

    def test_scan_standard_application_packages(self):
        # 1. Directory packages default to ~/.config/<dirname> with children
        (self.repo_dir / "git").mkdir()
        (self.repo_dir / "git" / ".gitconfig").write_text("[user]\nname=test")

        (self.repo_dir / "pwsh").mkdir()
        (self.repo_dir / "pwsh" / "profile.ps1").write_text("# pwsh profile")

        (self.repo_dir / "wezterm").mkdir()
        (self.repo_dir / "wezterm" / "wezterm.lua").write_text("-- wezterm config")

        # 2. Standalone root file defaults to ~/ ($HOME)
        (self.repo_dir / ".bashrc").write_text("export BASH=1")

        scanner = RepoScanner(self.repo_dir)
        configs = scanner.scan()

        apps = {c.app_name.lower(): c for c in configs}
        self.assertIn("git", apps)
        self.assertEqual(apps["git"].dest_expr, "~/.config/git")
        self.assertTrue(apps["git"].is_directory)
        self.assertTrue(apps["git"].is_expandable)
        self.assertEqual(len(apps["git"].children), 1)
        self.assertEqual(apps["git"].children[0].dest_expr, "~/.gitconfig")

        self.assertIn("pwsh", apps)
        self.assertEqual(apps["pwsh"].dest_expr, "~/.config/pwsh")
        self.assertTrue(apps["pwsh"].is_directory)
        self.assertTrue(apps["pwsh"].is_expandable)

        self.assertIn("wezterm", apps)
        self.assertEqual(apps["wezterm"].dest_expr, "~/.config/wezterm")
        self.assertTrue(apps["wezterm"].is_directory)

        # Standalone root file
        self.assertIn("bashrc", apps)
        self.assertEqual(apps["bashrc"].dest_expr, "~/.bashrc")
        self.assertFalse(apps["bashrc"].is_directory)

        # Verify no duplicate entries for the same app
        names = [c.app_name.lower() for c in configs]
        self.assertEqual(len(names), len(set(names)))

    def test_scan_preserves_package_root_and_prefix_setup(self):
        # Even if a package has a nested .config/<app> folder, the package root
        # must remain the top-level directory, preserving all prefix/first-layer files.
        nvim_root = self.repo_dir / "nvim"
        nvim_root.mkdir()
        (nvim_root / "init.lua").write_text("-- root init", encoding="utf-8")
        (nvim_root / "lazy-lock.json").write_text("{}", encoding="utf-8")
        (nvim_root / "lua" / "config").mkdir(parents=True)
        (nvim_root / "lua" / "config" / "lazy.lua").write_text("-- lazy config", encoding="utf-8")
        # Nested mirror folder
        nested = nvim_root / ".config" / "nvim"
        nested.mkdir(parents=True)
        (nested / "nested.lua").write_text("-- nested", encoding="utf-8")

        scanner = RepoScanner(self.repo_dir)
        configs = scanner.scan()
        apps = {c.app_name.lower(): c for c in configs}

        self.assertIn("nvim", apps)
        nvim_pkg = apps["nvim"]
        # Source must be the root directory 'nvim', not 'nvim/.config/nvim'
        self.assertEqual(nvim_pkg.source_rel, "nvim")
        self.assertEqual(nvim_pkg.dest_expr, "~/.config/nvim")
        # Packages without divergent home-level siblings stay packed as a whole directory
        self.assertTrue(nvim_pkg.link_as_dir)
        # Must scan all files including root layer (init.lua, lazy-lock.json, etc.)
        self.assertEqual(nvim_pkg.child_count, 4)
        child_sources = [c.source_rel for c in nvim_pkg.children]
        self.assertIn("nvim/init.lua", child_sources)
        self.assertIn("nvim/lazy-lock.json", child_sources)

        from fig.builder import get_all_leaf_items
        leaf_sources = {c.source_rel: c.dest_expr for c in get_all_leaf_items(nvim_pkg)}
        self.assertIn("nvim/lua/config/lazy.lua", leaf_sources)
        self.assertEqual(leaf_sources["nvim/lua/config/lazy.lua"], "~/.config/nvim/lua/config/lazy.lua")
        self.assertIn("nvim/.config/nvim/nested.lua", leaf_sources)

    def test_scan_auto_rationalizes_mixed_home_and_dot_config(self):
        git_dir = self.repo_dir / "git"
        (git_dir / ".config").mkdir(parents=True)
        (git_dir / ".gitconfig").write_text("[user]\nname = Test\n", encoding="utf-8")
        (git_dir / ".config" / ".gitconfig").write_text("[include]\n", encoding="utf-8")
        (git_dir / ".config" / "ignore").write_text("*.log\n", encoding="utf-8")
        (git_dir / ".config" / "attributes").write_text("* text=auto\n", encoding="utf-8")

        scanner = RepoScanner(self.repo_dir)
        configs = scanner.scan()
        apps = {c.app_name.lower(): c for c in configs}

        self.assertIn("git", apps)
        git_pkg = apps["git"]
        # Mixed home + .config destinations must auto-unpack the package
        self.assertFalse(git_pkg.link_as_dir)

        from fig.builder import get_all_leaf_items, build_template_from_items
        leaves = {c.source_rel: c.dest_expr for c in get_all_leaf_items(git_pkg)}
        self.assertEqual(leaves.get("git/.gitconfig"), "~/.gitconfig")
        self.assertEqual(leaves.get("git/.config/.gitconfig"), "~/.config/git/.gitconfig")
        self.assertEqual(leaves.get("git/.config/ignore"), "~/.config/git/ignore")
        self.assertEqual(leaves.get("git/.config/attributes"), "~/.config/git/attributes")

        tpl = build_template_from_items(self.repo_dir, configs)
        self.assertEqual(tpl.mappings.get("git/.gitconfig"), "~/.gitconfig")
        self.assertEqual(tpl.mappings.get("git/.config/ignore"), "~/.config/git/ignore")
        self.assertEqual(tpl.mappings.get("git/.config/attributes"), "~/.config/git/attributes")

    def test_scan_nested_pathspec_and_relative_key_value_mappings(self):
        # 1. Single pathspec.txt with relative file & dir key-value pairs
        git_dir = self.repo_dir / "git"
        (git_dir / ".config").mkdir(parents=True)
        (git_dir / ".gitconfig").write_text("[user]\nname = Test\n", encoding="utf-8")
        (git_dir / ".config" / "config").write_text("[core]\n", encoding="utf-8")
        (git_dir / ".config" / "ignore").write_text("*.tmp\n", encoding="utf-8")
        (git_dir / "pathspec.txt").write_text(
            ".gitconfig = ~/.gitconfig\n"
            ".config = ~/.config/git\n"
            ".config/ignore = ~/.config/git/global_ignore\n",
            encoding="utf-8",
        )

        # 2. Nested pathspec.txt inside a subdirectory
        pkg_dir = self.repo_dir / "my_pkg"
        (pkg_dir / "sub").mkdir(parents=True)
        (pkg_dir / "root.conf").write_text("root=1\n", encoding="utf-8")
        (pkg_dir / "sub" / "nested.conf").write_text("nested=1\n", encoding="utf-8")
        (pkg_dir / "sub" / "pathspec.txt").write_text("~/custom_sub\n", encoding="utf-8")

        scanner = RepoScanner(self.repo_dir)
        configs = scanner.scan()
        apps = {c.app_name: c for c in configs}

        from fig.builder import get_all_leaf_items
        git_leaves = {c.source_rel: c.dest_expr for c in get_all_leaf_items(apps["git"])}
        self.assertFalse(apps["git"].link_as_dir)
        self.assertEqual(git_leaves.get("git/.gitconfig"), "~/.gitconfig")
        self.assertEqual(git_leaves.get("git/.config/config"), "~/.config/git/config")
        self.assertEqual(git_leaves.get("git/.config/ignore"), "~/.config/git/global_ignore")
        # pathspec.txt itself must be ignored and never included as a leaf
        self.assertNotIn("git/pathspec.txt", git_leaves)

        pkg_leaves = {c.source_rel: c.dest_expr for c in get_all_leaf_items(apps["my_pkg"])}
        self.assertFalse(apps["my_pkg"].link_as_dir)
        self.assertEqual(pkg_leaves.get("my_pkg/root.conf"), "~/.config/my_pkg/root.conf")
        self.assertEqual(pkg_leaves.get("my_pkg/sub/nested.conf"), "~/custom_sub/nested.conf")
        self.assertNotIn("my_pkg/sub/pathspec.txt", pkg_leaves)


if __name__ == "__main__":
    unittest.main()
