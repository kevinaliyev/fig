"""Tests for Template Viewer Module."""

import shutil
import tempfile
import unittest
from pathlib import Path

from fig.core.config import FigState
from fig.core.template import Template
from fig.modules.viewer import format_template_view, resolve_template_target, view_template


class TestViewer(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="fig_test_view_"))
        self.fig_home = self.tmp_dir / ".fig"
        self.state = FigState(self.fig_home)
        self.state.ensure_directories()

        self.tpl_path = self.tmp_dir / "my_tpl.toml"
        self.tpl = Template(
            name="test-tpl",
            mappings={".gitconfig": "~/.gitconfig"},
            os_mappings={"windows": {"powershell": "~/Documents/PowerShell"}},
        )
        self.tpl.save(self.tpl_path)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_format_template_view(self):
        output = format_template_view(self.tpl, self.tpl_path)
        self.assertIn("test-tpl", output)
        self.assertIn(".gitconfig", output)
        self.assertIn("[windows]", output)

    def test_resolve_template_target_direct_file(self):
        resolved = resolve_template_target(self.state, str(self.tpl_path))
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.resolve(), self.tpl_path.resolve())

    def test_view_template(self):
        ret = view_template(self.state, str(self.tpl_path))
        self.assertEqual(ret, 0)


if __name__ == "__main__":
    unittest.main()
