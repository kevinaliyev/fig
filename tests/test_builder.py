"""Tests for Builder Module."""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from fig.builder.scanner import DiscoveredConfig
from fig.builder import (
    build_template_from_items,
    run_builder,
    parse_indices,
    get_pathspec_suggestions,
)
from fig.config.platform import CURRENT_OS, expand_pathspec_shorthand
from fig.config.state import FigState
from fig.config.template import Template


class TestBuilder(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="fig_test_bld_"))
        self.fig_home = self.tmp_dir / "fig_home"
        os.environ["FIG_HOME"] = str(self.fig_home)
        self.repo_dir = self.tmp_dir / "dotfiles"
        self.repo_dir.mkdir()
        (self.repo_dir / ".gitconfig").write_text("[user]\nname = Jane", encoding="utf-8")
        (self.repo_dir / ".zshrc").write_text("export FOO=1", encoding="utf-8")

    def tearDown(self):
        if "FIG_HOME" in os.environ:
            del os.environ["FIG_HOME"]
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_parse_indices(self):
        self.assertEqual(parse_indices(["1", "3", "5"], 10), [0, 2, 4])
        self.assertEqual(parse_indices(["#2", "#4"], 5), [1, 3])
        # Duplicate removal and ignoring out-of-bounds/invalid
        self.assertEqual(parse_indices(["1", "1", "99", "abc", "2"], 5), [0, 1])

    def test_expand_pathspec_shorthand(self):
        self.assertEqual(expand_pathspec_shorthand(".config/nvim"), "~/.config/nvim")
        self.assertEqual(expand_pathspec_shorthand("config/wezterm"), "~/.config/wezterm")
        self.assertEqual(expand_pathspec_shorthand("@docs/PowerShell/profile.ps1"), "~/Documents/PowerShell/profile.ps1")
        self.assertEqual(expand_pathspec_shorthand("Documents/foo"), "~/Documents/foo")
        self.assertEqual(expand_pathspec_shorthand("@home/.bashrc"), "~/.bashrc")

    def test_build_template_with_exclusions(self):
        items = [
            DiscoveredConfig(
                app_name="git",
                source_rel=".gitconfig",
                dest_expr="~/.gitconfig",
                is_directory=False,
                is_excluded=False,
            ),
            DiscoveredConfig(
                app_name="zsh",
                source_rel=".zshrc",
                dest_expr="~/.zshrc",
                is_directory=False,
                is_excluded=True,  # User toggled exclude!
            ),
        ]
        tpl = build_template_from_items(self.repo_dir, items)
        self.assertIn(".gitconfig", tpl.mappings)
        self.assertNotIn(".zshrc", tpl.mappings)
        self.assertIn(".zshrc", tpl.ignore_patterns)

    def test_build_template_purges_stale_ignores_for_active_packages(self):
        # When an existing template previously had 'nvim' in ignore_patterns,
        # but nvim/.config/nvim is included, 'nvim' must be purged from ignore_patterns.
        existing_tpl = Template(
            name="test-dotfiles",
            ignore_patterns=[".git", "nvim", "old_package"],
        )
        items = [
            DiscoveredConfig(
                app_name="nvim",
                source_rel="nvim/.config/nvim",
                dest_expr="~/.config/nvim",
                is_directory=True,
                link_as_dir=True,
                is_excluded=False,
            ),
        ]
        tpl = build_template_from_items(self.repo_dir, items, existing_template=existing_tpl)
        self.assertIn("nvim/.config/nvim", tpl.mappings)
        self.assertNotIn("nvim", tpl.ignore_patterns)
        self.assertIn("old_package", tpl.ignore_patterns)

    def test_expand_collapse_and_customized_package(self):
        from fig.builder import (
            get_visible_items,
            set_expansion,
            set_exclusion_recursive,
            is_package_customized,
        )
        # Create a parent directory with 2 children
        child1 = DiscoveredConfig(
            app_name="Microsoft.PowerShell_profile",
            source_rel="pwsh/CurrentUserAllHosts/Microsoft.PowerShell_profile.ps1",
            dest_expr="~/Documents/PowerShell/Microsoft.PowerShell_profile.ps1",
            is_directory=False,
            depth=1,
        )
        child2 = DiscoveredConfig(
            app_name="powershell.config",
            source_rel="pwsh/CurrentUserAllHosts/powershell.config.json",
            dest_expr="~/.config/pwsh/powershell.config.json",
            is_directory=False,
            depth=1,
        )
        parent = DiscoveredConfig(
            app_name="pwsh",
            source_rel="pwsh",
            dest_expr="~/.config/pwsh",
            is_directory=True,
            child_count=2,
            is_expandable=True,
            is_expanded=False,
            children=[child1, child2],
        )

        items = [parent]
        # Initially collapsed: only parent visible
        self.assertEqual(len(get_visible_items(items)), 1)
        self.assertFalse(is_package_customized(parent))

        # Expand: parent + 2 children visible
        set_expansion(parent, expand=True)
        self.assertTrue(parent.is_expanded)
        self.assertEqual(len(get_visible_items(items)), 3)

        # Exclude child2
        child2.is_excluded = True
        self.assertTrue(is_package_customized(parent))

        # Build template: should contain child1 mapping, but child2 in ignore
        tpl = build_template_from_items(self.repo_dir, items)
        if CURRENT_OS.value == "windows":
            self.assertIn("pwsh/CurrentUserAllHosts/Microsoft.PowerShell_profile.ps1", tpl.os_mappings.get("windows", {}))
        else:
            self.assertIn("pwsh/CurrentUserAllHosts/Microsoft.PowerShell_profile.ps1", tpl.mappings)
        self.assertIn("pwsh/CurrentUserAllHosts/powershell.config.json", tpl.ignore_patterns)

        # Collapse parent back
        set_expansion(parent, expand=False)
        self.assertFalse(parent.is_expanded)
        self.assertEqual(len(get_visible_items(items)), 1)

    def test_complex_dotfiles_scan(self):
        from fig.builder.scanner import RepoScanner
        complex_dir = self.tmp_dir / "complex_dotfiles"
        complex_dir.mkdir(parents=True, exist_ok=True)
        for app in ("git", "nvim", "pwsh", "wezterm", "zsh", "gamefigs"):
            (complex_dir / app).mkdir(parents=True, exist_ok=True)
            (complex_dir / app / "config.txt").write_text("dummy", encoding="utf-8")
        # Subdirectories for pwsh
        (complex_dir / "pwsh" / "CurrentUserAllHosts").mkdir(parents=True, exist_ok=True)
        (complex_dir / "pwsh" / "CurrentUserAllHosts" / "profile.ps1").write_text("# profile", encoding="utf-8")

        scanner = RepoScanner(complex_dir)
        configs = scanner.scan()
        apps = {c.app_name.lower(): c for c in configs}

        # Verify top-level directories discovered
        for expected in ("gamefigs", "git", "nvim", "pwsh", "wezterm", "zsh"):
            self.assertIn(expected, apps)
            self.assertTrue(apps[expected].is_directory)
            self.assertTrue(apps[expected].dest_expr.startswith("~/.config/"))
            self.assertTrue(apps[expected].is_expandable)

        # Verify pwsh children contain profile
        pwsh_leaves = [c.source_rel for c in apps["pwsh"].children]
        self.assertTrue(any("CurrentUserAllHosts" in s for s in pwsh_leaves))

    def test_run_builder_non_interactive_and_active_registration(self):
        out_file = run_builder(target=str(self.repo_dir), interactive=False)
        self.assertIsNotNone(out_file)
        self.assertTrue(out_file.exists())

        loaded = Template.load(out_file)
        self.assertIn(".gitconfig", loaded.mappings)

        # Verify active template was registered
        state = FigState()
        active = state.get_active_template_path()
        self.assertIsNotNone(active)
        self.assertEqual(active.resolve(), out_file.resolve())

    def test_scoped_view_takeover_and_segregated_excluded_table(self):
        from fig.builder import (
            render_scoped_view,
            get_scope_path_str,
            render_full_repo_tree,
        )

        child1 = DiscoveredConfig(
            app_name="profile",
            source_rel="pwsh/CurrentUserAllHosts/profile.ps1",
            dest_expr="~/Documents/PowerShell/Microsoft.PowerShell_profile.ps1",
            is_directory=False,
            depth=1,
        )
        child2 = DiscoveredConfig(
            app_name="config",
            source_rel="pwsh/CurrentUserAllHosts/config.json",
            dest_expr="~/.config/pwsh/config.json",
            is_directory=False,
            depth=1,
            is_excluded=True,  # Excluded!
        )
        parent = DiscoveredConfig(
            app_name="pwsh",
            source_rel="pwsh",
            dest_expr="~/.config/pwsh",
            is_directory=True,
            child_count=2,
            is_expandable=True,
            children=[child1, child2],
        )
        root_file = DiscoveredConfig(
            app_name="gitconfig",
            source_rel=".gitconfig",
            dest_expr="~/.gitconfig",
            is_directory=False,
        )

        root_items = [parent, root_file]

        # 1. At Root (/): Path is "/"
        nav_stack = []
        self.assertEqual(get_scope_path_str(nav_stack), "/")
        view_text, lookup = render_scoped_view(root_items, nav_stack)
        self.assertIn("Location: /", view_text)
        self.assertIn("Active / Included Packages & Files:", view_text)
        self.assertIn("pwsh", view_text)
        self.assertIn(".gitconfig", view_text)
        # child2 is excluded, so it appears in the Excluded Items table
        self.assertIn("Excluded Items", view_text)
        self.assertIn("pwsh/CurrentUserAllHosts/config.json", view_text)

        # 2. Scoped Takeover: Navigating into 'pwsh'
        nav_stack = [parent]
        self.assertEqual(get_scope_path_str(nav_stack), "/pwsh/")
        view_text, lookup = render_scoped_view(root_items, nav_stack)
        self.assertIn("Location: /pwsh/", view_text)
        self.assertIn("Active Directory Tree:", view_text)
        self.assertIn("profile", view_text)
        # Excluded child2 is segregated into the bottom table, not in the active tree
        self.assertIn("Excluded Items in /pwsh/", view_text)
        self.assertIn("pwsh/CurrentUserAllHosts/config.json", view_text)

        # 3. Test Full Tree renderer
        tree_text = render_full_repo_tree(root_items)
        self.assertIn("/ (Repository Root)", tree_text)
        self.assertIn("pwsh/", tree_text)

    def test_unpack_directory_links_only_selected_files_not_dirtree(self):
        """Test user scenario: Dotfiles repo with pwsh/CurrentUserAllHosts/ contains 4 files.
        User unpacks pwsh and selects only 3 files.
        Neither pwsh nor CurrentUserAllHosts must be linked as directories.
        Only the 3 files must be linked; the 4th file must be in ignore_patterns.
        """
        file1 = DiscoveredConfig(
            app_name="profile",
            source_rel="pwsh/CurrentUserAllHosts/profile.ps1",
            dest_expr="~/Documents/PowerShell/profile.ps1",
            is_directory=False,
            depth=2,
            parent_source_rel="pwsh/CurrentUserAllHosts",
        )
        file2 = DiscoveredConfig(
            app_name="aliases",
            source_rel="pwsh/CurrentUserAllHosts/aliases.ps1",
            dest_expr="~/Documents/PowerShell/aliases.ps1",
            is_directory=False,
            depth=2,
            parent_source_rel="pwsh/CurrentUserAllHosts",
        )
        file3 = DiscoveredConfig(
            app_name="functions",
            source_rel="pwsh/CurrentUserAllHosts/functions.ps1",
            dest_expr="~/Documents/PowerShell/functions.ps1",
            is_directory=False,
            depth=2,
            parent_source_rel="pwsh/CurrentUserAllHosts",
        )
        file4 = DiscoveredConfig(
            app_name="unused",
            source_rel="pwsh/CurrentUserAllHosts/unused.ps1",
            dest_expr="~/Documents/PowerShell/unused.ps1",
            is_directory=False,
            depth=2,
            is_excluded=True,  # Excluded!
            parent_source_rel="pwsh/CurrentUserAllHosts",
        )
        subdir = DiscoveredConfig(
            app_name="CurrentUserAllHosts",
            source_rel="pwsh/CurrentUserAllHosts",
            dest_expr="~/.config/pwsh/CurrentUserAllHosts",
            is_directory=True,
            link_as_dir=False,  # Container folder
            depth=1,
            children=[file1, file2, file3, file4],
            parent_source_rel="pwsh",
        )
        parent = DiscoveredConfig(
            app_name="pwsh",
            source_rel="pwsh",
            dest_expr="~/.config/pwsh",
            is_directory=True,
            link_as_dir=False,  # Unpacked!
            depth=0,
            children=[subdir],
        )

        items = [parent]
        tpl = build_template_from_items(self.repo_dir, items)

        # 1. Neither parent dir nor subdir must be in mappings
        self.assertNotIn("pwsh", tpl.mappings)
        self.assertNotIn("pwsh/CurrentUserAllHosts", tpl.mappings)
        if "windows" in tpl.os_mappings:
            self.assertNotIn("pwsh", tpl.os_mappings["windows"])
            self.assertNotIn("pwsh/CurrentUserAllHosts", tpl.os_mappings["windows"])

        # 2. All 3 active files must be in mappings
        all_mapped = {**tpl.mappings, **tpl.os_mappings.get("windows", {})}
        self.assertIn("pwsh/CurrentUserAllHosts/profile.ps1", all_mapped)
        self.assertIn("pwsh/CurrentUserAllHosts/aliases.ps1", all_mapped)
        self.assertIn("pwsh/CurrentUserAllHosts/functions.ps1", all_mapped)
        self.assertNotIn("pwsh/CurrentUserAllHosts/unused.ps1", all_mapped)

        # 3. Excluded 4th file must be in ignore_patterns
        self.assertIn("pwsh/CurrentUserAllHosts/unused.ps1", tpl.ignore_patterns)

    def test_collect_active_tree_items_unpacked_container(self):
        """Verify that unpacked folder containers are not indexed as selectable link items,
        allowing leaf files to be directly indexed [1, 2, 3].
        """
        from fig.builder import collect_active_tree_items
        file1 = DiscoveredConfig(app_name="f1", source_rel="pwsh/sub/f1.ps1", dest_expr="~/f1.ps1", is_directory=False)
        file2 = DiscoveredConfig(app_name="f2", source_rel="pwsh/sub/f2.ps1", dest_expr="~/f2.ps1", is_directory=False)
        sub = DiscoveredConfig(
            app_name="sub",
            source_rel="pwsh/sub",
            dest_expr="~/sub",
            is_directory=True,
            link_as_dir=False,  # Unpacked folder container
            children=[file1, file2],
        )
        parent = DiscoveredConfig(
            app_name="pwsh",
            source_rel="pwsh",
            dest_expr="~/pwsh",
            is_directory=True,
            link_as_dir=False,
            children=[sub],
        )

        active = []
        excluded = []
        collect_active_tree_items(parent, active, excluded, is_root_call=True)

        # Active list must contain ONLY file1 and file2, NOT sub!
        self.assertEqual(len(active), 2)
        self.assertEqual(active[0].source_rel, "pwsh/sub/f1.ps1")
        self.assertEqual(active[1].source_rel, "pwsh/sub/f2.ps1")

    def test_including_child_in_previously_excluded_parent(self):
        """Verify that when a parent directory was excluded, including a child leaf
        un-excludes the package and links only the child leaf, not the whole directory.
        """
        child = DiscoveredConfig(
            app_name="f1",
            source_rel="pkg/f1.txt",
            dest_expr="~/f1.txt",
            is_directory=False,
            is_excluded=False,  # Active child!
        )
        parent = DiscoveredConfig(
            app_name="pkg",
            source_rel="pkg",
            dest_expr="~/.config/pkg",
            is_directory=True,
            is_excluded=True,  # Parent was marked excluded previously
            children=[child],
        )

        tpl = build_template_from_items(self.repo_dir, [parent])
        # Since child is active, it must be mapped
        self.assertIn("pkg/f1.txt", tpl.mappings)
        self.assertNotIn("pkg", tpl.mappings)


    def test_repl_commands_unpack_and_only(self):
        """Simulate interactive REPL session using 'unpack', 'cd', and 'only'."""
        from unittest.mock import patch
        from fig.builder import run_builder_repl

        file1 = DiscoveredConfig(app_name="f1", source_rel="pwsh/sub/f1.ps1", dest_expr="~/f1.ps1", is_directory=False)
        file2 = DiscoveredConfig(app_name="f2", source_rel="pwsh/sub/f2.ps1", dest_expr="~/f2.ps1", is_directory=False)
        file3 = DiscoveredConfig(app_name="f3", source_rel="pwsh/sub/f3.ps1", dest_expr="~/f3.ps1", is_directory=False)
        file4 = DiscoveredConfig(app_name="f4", source_rel="pwsh/sub/f4.ps1", dest_expr="~/f4.ps1", is_directory=False)
        sub = DiscoveredConfig(
            app_name="sub",
            source_rel="pwsh/sub",
            dest_expr="~/sub",
            is_directory=True,
            link_as_dir=False,
            children=[file1, file2, file3, file4],
        )
        parent = DiscoveredConfig(
            app_name="pwsh",
            source_rel="pwsh",
            dest_expr="~/.config/pwsh",
            is_directory=True,
            link_as_dir=True,  # Initially packed
            children=[sub],
        )

        simulated_inputs = [
            "unpack pwsh",     # 1. Unpack pwsh directory
            "cd pwsh",         # 2. cd into pwsh
            "only 1 2 3",      # 3. Keep only files 1, 2, 3 (exclude file 4)
            "cd ..",           # 4. Return to root
            "done",            # 5. Save & finish
        ]

        with patch("builtins.input", side_effect=simulated_inputs), patch("sys.stdin.isatty", return_value=True):
            result = run_builder_repl([parent], interactive=True)

        self.assertFalse(parent.link_as_dir)
        self.assertFalse(file1.is_excluded)
        self.assertFalse(file2.is_excluded)
        self.assertFalse(file3.is_excluded)
        self.assertTrue(file4.is_excluded)

        tpl = build_template_from_items(self.repo_dir, result)
        self.assertNotIn("pwsh", tpl.mappings)
        self.assertNotIn("pwsh/sub", tpl.mappings)
        self.assertIn("pwsh/sub/f1.ps1", tpl.mappings)
        self.assertIn("pwsh/sub/f2.ps1", tpl.mappings)
        self.assertIn("pwsh/sub/f3.ps1", tpl.mappings)
        self.assertNotIn("pwsh/sub/f4.ps1", tpl.mappings)
        self.assertIn("pwsh/sub/f4.ps1", tpl.ignore_patterns)

    def test_pack_preserves_directory_root_with_exclusions(self):
        """Verify that when a directory is explicitly packed (force_pack=True),
        it maps the directory as a whole root and adds excluded children to ignore_patterns.
        """
        child1 = DiscoveredConfig(app_name="init.lua", source_rel="nvim/init.lua", dest_expr="~/.config/nvim/init.lua", is_directory=False)
        child2 = DiscoveredConfig(app_name="lazy-lock.json", source_rel="nvim/lazy-lock.json", dest_expr="~/.config/nvim/lazy-lock.json", is_directory=False, is_excluded=True)
        parent = DiscoveredConfig(
            app_name="nvim",
            source_rel="nvim",
            dest_expr="~/.config/nvim",
            is_directory=True,
            link_as_dir=True,
            children=[child1, child2],
        )
        parent.force_pack = True  # User explicitly selected pack!

        tpl = build_template_from_items(self.repo_dir, [parent])
        self.assertIn("nvim", tpl.mappings)
        self.assertNotIn("nvim/init.lua", tpl.mappings)
        self.assertIn("nvim/lazy-lock.json", tpl.ignore_patterns)

    def test_repl_mode_and_os_commands(self):
        """Verify setting individual link mode and OS scope via REPL commands."""
        from unittest.mock import patch
        from fig.builder import run_builder_repl

        item = DiscoveredConfig(
            app_name="nvim",
            source_rel="nvim",
            dest_expr="~/.config/nvim",
            is_directory=True,
        )

        simulated_inputs = [
            "mode 1 junction",   # Set individual mode to junction
            "os 1 windows",      # Assign to windows OS scope
            "done",
        ]

        with patch("builtins.input", side_effect=simulated_inputs), patch("sys.stdin.isatty", return_value=True):
            result = run_builder_repl([item], interactive=True)

        self.assertEqual(item.link_mode, "junction")
        self.assertEqual(item.os_target, "windows")

        tpl = build_template_from_items(self.repo_dir, result)
        win_mappings = tpl.os_mappings.get("windows", {})
        self.assertIn("nvim", win_mappings)
        self.assertEqual(win_mappings["nvim"]["mode"], "junction")

    def test_render_help_modal(self):
        """Verify render_help_modal returns a styled box with categorized command references."""
        from fig.builder import render_help_modal
        from fig.ui.ansi import strip_ansi

        help_text = render_help_modal()
        plain = strip_ansi(help_text)
        self.assertIn("Fig Template Builder — Command Reference", plain)
        self.assertIn("Navigation:", plain)
        self.assertIn("cd <#|name>", plain)
        self.assertIn("Selection & Exclusions:", plain)
        self.assertIn("only <#> ...", plain)
        self.assertIn("Packaging & Link Modes:", plain)
        self.assertIn("pack [#|name]", plain)
        self.assertIn("unpack [#|name]", plain)
        self.assertIn("Actions & Configuration:", plain)
        self.assertIn("done (save)", plain)
        self.assertIn("quit (exit)", plain)
        self.assertTrue(plain.startswith("┌"))
        self.assertTrue(plain.strip().endswith("┘"))

    def test_render_scoped_view_status_msg_and_shortcuts_bar(self):
        """Verify render_scoped_view displays status_msg and modern 1-line shortcuts bar."""
        from fig.builder import render_scoped_view
        from fig.ui.ansi import strip_ansi

        item = DiscoveredConfig(app_name="git", source_rel=".gitconfig", dest_expr="~/.gitconfig", is_directory=False)
        view_text, _ = render_scoped_view([item], nav_stack=[], status_msg="[OK] TOGGLED #1 (git): EXCLUDED [ ]")
        plain = strip_ansi(view_text)

        # Status message embedded below header
        self.assertIn("[OK] TOGGLED #1 (git): EXCLUDED [ ]", plain)
        self.assertIn("Active / Included Packages & Files:", plain)
        # Modern single-line shortcuts legend
        self.assertIn("Commands:  <#> Toggle  ·  cd <#> Open  ·  edit <#> Remap", plain)
        self.assertIn("? Help  ·  done Save  ·  quit Exit", plain)

    def test_repl_help_modal_and_unknown_commands(self):
        """Verify that typing 'help' in REPL opens the help modal and returns upon Enter."""
        from unittest.mock import patch
        from fig.builder import run_builder_repl

        item = DiscoveredConfig(app_name="git", source_rel=".gitconfig", dest_expr="~/.gitconfig", is_directory=False)
        simulated_inputs = [
            "help",         # 1. Open help modal
            "",             # 2. Press Enter to return to template
            "invalid_xyz",  # 3. Unknown command
            "done",         # 4. Save and exit
        ]

        with patch("builtins.input", side_effect=simulated_inputs), patch("sys.stdin.isatty", return_value=True):
            result = run_builder_repl([item], interactive=True)

        self.assertEqual(len(result), 1)

    def test_ui_format_box_and_clear_screen(self):
        """Verify format_box border rendering and clear_screen ANSI escape sequence."""
        from unittest.mock import patch
        from fig.ui.ansi import format_box, clear_screen, strip_ansi

        box = format_box("Test Modal", ["Content line 1", "Content line 2"], width=40)
        plain = strip_ansi(box)
        self.assertIn("┌─ Test Modal", plain)
        self.assertIn("Content line 1", plain)
        self.assertIn("Content line 2", plain)
        self.assertTrue(plain.strip().endswith("┘"))

        # Test clear_screen in TTY mode
        with patch("sys.stdout.isatty", return_value=True), patch("sys.stdout.write") as mock_write, patch("sys.stdout.flush"):
            clear_screen()
            mock_write.assert_called_with("\033[2J\033[3J\033[H")

        # Test clear_screen in non-TTY mode (no-op)
        with patch("sys.stdout.isatty", return_value=False), patch("sys.stdout.write") as mock_write:
            clear_screen()
            mock_write.assert_not_called()

    def test_merge_existing_template_into_discovered(self):
        """Verify merge_existing_template_into_discovered preserves custom destinations,
        link modes, OS scopes, and exclusions from an existing template.
        """
        from fig.builder import merge_existing_template_into_discovered

        existing_tpl = Template(
            name="my-custom-tpl",
            mappings={
                "git/.config/git": "~/.config/git",
                "nvim": {"target": "~/.config/nvim", "mode": "junction"},
                "pwsh/sub/f1.ps1": "~/Documents/PowerShell/f1.ps1",
            },
            os_mappings={
                "windows": {
                    "pwsh/sub/f2.ps1": "~/Documents/PowerShell/f2.ps1",
                }
            },
            ignore_patterns=[".git", "pwsh/sub/f3.ps1"],
        )

        f1 = DiscoveredConfig(app_name="f1", source_rel="pwsh/sub/f1.ps1", dest_expr="~/f1.ps1", is_directory=False)
        f2 = DiscoveredConfig(app_name="f2", source_rel="pwsh/sub/f2.ps1", dest_expr="~/f2.ps1", is_directory=False)
        f3 = DiscoveredConfig(app_name="f3", source_rel="pwsh/sub/f3.ps1", dest_expr="~/f3.ps1", is_directory=False)
        pwsh_dir = DiscoveredConfig(
            app_name="pwsh",
            source_rel="pwsh",
            dest_expr="~/.config/pwsh",
            is_directory=True,
            children=[f1, f2, f3],
        )
        nvim_dir = DiscoveredConfig(
            app_name="nvim",
            source_rel="nvim",
            dest_expr="~/.config/nvim",
            is_directory=True,
        )

        discovered = [pwsh_dir, nvim_dir]
        merged = merge_existing_template_into_discovered(discovered, existing_tpl)

        # nvim should be packed, junction mode
        self.assertFalse(nvim_dir.is_excluded)
        self.assertTrue(nvim_dir.link_as_dir)
        self.assertEqual(nvim_dir.link_mode, "junction")

        # pwsh should be unpacked because individual children are mapped
        self.assertFalse(pwsh_dir.link_as_dir)
        self.assertFalse(f1.is_excluded)
        self.assertEqual(f1.dest_expr, "~/Documents/PowerShell/f1.ps1")
        self.assertFalse(f2.is_excluded)
        self.assertEqual(f2.os_target, "windows")
        # f3 was in ignore_patterns -> must be excluded!
        self.assertTrue(f3.is_excluded)

    def test_run_rebuilder_references_source_of_truth_without_path(self):
        """Verify run_rebuilder locates the active template source of truth
        without needing an explicit path argument.
        """
        from unittest.mock import patch
        from fig.builder import run_rebuilder

        # Create an initial template in repo_dir
        init_tpl = Template(
            name="initial-dots",
            mappings={".gitconfig": "~/.gitconfig"},
        )
        tpl_path = self.repo_dir / "fig.toml"
        init_tpl.save(tpl_path)

        # Register as active template
        state = FigState()
        state.set_active_template_path(tpl_path, self.repo_dir)

        # Run rebuilder without passing target, simulated interactive input
        simulated_inputs = [
            "done",         # Exit REPL
            "test_prof",    # Profile name
            "n",            # Do not deploy now
        ]

        with patch("builtins.input", side_effect=simulated_inputs), patch("sys.stdin.isatty", return_value=True):
            res_path = run_rebuilder(target=None, interactive=True)

        self.assertIsNotNone(res_path)
        self.assertEqual(res_path.resolve(), tpl_path.resolve())

        # Verify state.toml and profile creation
        cfg = state.load_config()
        self.assertEqual(cfg.get("active", {}).get("profile_name"), "test_prof")
        self.assertIn("test_prof", cfg.get("profiles", {}))


if __name__ == "__main__":
    unittest.main()
