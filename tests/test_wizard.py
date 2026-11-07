"""Tests for Setup Wizard."""

import shutil
import tempfile
import unittest
from pathlib import Path

from fig.core.wizard import run_interactive_wizard
from fig.core.template import Template


class TestWizard(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="fig_test_wiz_"))

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_wizard_generates_starter_template(self):
        answers = {
            "shell": "zsh",
            "git": True,
            "ssh": True,
            "editor": "neovim",
            "terminal": "alacritty",
        }
        out_file = run_interactive_wizard(
            output_dir=self.tmp_dir,
            interactive=False,
            answers=answers,
        )
        self.assertIsNotNone(out_file)
        self.assertTrue(out_file.exists())

        tpl = Template.load(out_file)
        self.assertIn("git", tpl.presets)
        self.assertIn("zsh", tpl.presets)
        self.assertIn("neovim", tpl.presets)
        self.assertIn(".gitconfig", tpl.mappings)


if __name__ == "__main__":
    unittest.main()
