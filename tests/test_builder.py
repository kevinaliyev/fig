"""Tests for Builder Module."""

import shutil
import tempfile
import unittest
from pathlib import Path

from fig.modules.scanner import DiscoveredConfig
from fig.modules.builder import build_template_from_items, run_builder
from fig.core.template import Template


class TestBuilder(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="fig_test_bld_"))
        self.repo_dir = self.tmp_dir / "dotfiles"
        self.repo_dir.mkdir()
        (self.repo_dir / ".gitconfig").write_text("[user]\nname = Jane", encoding="utf-8")
        (self.repo_dir / ".zshrc").write_text("export FOO=1", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

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

    def test_run_builder_non_interactive(self):
        out_file = run_builder(target=str(self.repo_dir), interactive=False)
        self.assertIsNotNone(out_file)
        self.assertTrue(out_file.exists())

        loaded = Template.load(out_file)
        self.assertIn(".gitconfig", loaded.mappings)


if __name__ == "__main__":
    unittest.main()
