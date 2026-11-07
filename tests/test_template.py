"""Tests for Template Engine."""

import shutil
import tempfile
import unittest
from pathlib import Path

from fig.core.template import Template, discover_template, generate_default_template


class TestTemplate(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="fig_test_tpl_"))
        self.repo_dir = self.tmp_dir / "dotfiles"
        self.repo_dir.mkdir()

        # Create some mock dotfiles in repo
        (self.repo_dir / ".gitconfig").write_text("[user]\nname = Test", encoding="utf-8")
        (self.repo_dir / ".zshrc").write_text("export FOO=1", encoding="utf-8")
        (self.repo_dir / "custom.conf").write_text("setting=true", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_auto_generate_template(self):
        tpl = generate_default_template(self.repo_dir)
        self.assertIn("git", tpl.presets)
        self.assertIn("zsh", tpl.presets)
        self.assertIn(".gitconfig", tpl.mappings)
        self.assertIn(".zshrc", tpl.mappings)
        self.assertIn("custom.conf", tpl.mappings)

    def test_save_and_load_template(self):
        tpl = Template(
            name="my-test-profile",
            mappings={".gitconfig": "~/.gitconfig"},
            presets=["git"],
        )
        tpl_path = self.repo_dir / "fig.toml"
        tpl.save(tpl_path)

        self.assertTrue(tpl_path.exists())

        loaded = Template.load(tpl_path)
        self.assertEqual(loaded.name, "my-test-profile")
        self.assertIn(".gitconfig", loaded.mappings)
        self.assertEqual(loaded.mappings[".gitconfig"], "~/.gitconfig")

    def test_discover_template(self):
        self.assertIsNone(discover_template(self.repo_dir))

        tpl_path = self.repo_dir / "fig.toml"
        tpl_path.write_text("[meta]\nname = 'test'\n", encoding="utf-8")

        found = discover_template(self.repo_dir)
        self.assertIsNotNone(found)
        self.assertEqual(found, tpl_path.resolve())

    def test_resolve_plan(self):
        tpl = Template(
            mappings={
                ".gitconfig": "~/.gitconfig",
                "custom.conf": "~/config/custom.conf",
            }
        )
        plan = tpl.resolve_plan(self.repo_dir)
        self.assertEqual(len(plan), 2)
        sources = [str(src) for src, _ in plan]
        self.assertTrue(any(".gitconfig" in s for s in sources))
        self.assertTrue(any("custom.conf" in s for s in sources))


if __name__ == "__main__":
    unittest.main()
