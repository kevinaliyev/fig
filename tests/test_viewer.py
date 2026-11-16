"""Tests for Template Viewer Module."""

import shutil
import tempfile
import unittest
from pathlib import Path

from fig.config.state import FigState
from fig.config.template import Template
from fig.ui.viewer import format_template_view, resolve_template_target, view_template


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

    def test_format_template_view_os_active_inactive(self):
        """Verify that POSIX mappings are marked inactive on Windows, and per-link modes are rendered."""
        from fig.config.platform import CURRENT_OS, OperatingSystem

        cross_tpl = Template(
            name="cross-test",
            mappings={"nvim": {"target": "~/.config/nvim", "mode": "junction"}},
            os_mappings={
                "windows": {"pwsh": "~/Documents/PowerShell"},
                "posix": {"zsh": "~/.zshrc"},
            },
        )
        output = format_template_view(cross_tpl, self.tpl_path)
        self.assertIn("[junction]", output)
        if CURRENT_OS == OperatingSystem.WINDOWS:
            self.assertIn("ACTIVE ON THIS HOST (Windows)", output)
            self.assertIn("INACTIVE ON THIS HOST", output)
            # Active mappings must strictly appear above inactive platform mappings
            active_idx = output.find("Active Mappings on this Host")
            inactive_idx = output.find("Inactive Platform Mappings")
            self.assertNotEqual(active_idx, -1)
            self.assertNotEqual(inactive_idx, -1)
            self.assertLess(active_idx, inactive_idx)
            # Universal mappings must also have the active badge
            self.assertIn("[universal] \x1b[1m\x1b[32m[ACTIVE ON THIS HOST (Windows)]\x1b[0m" if "\x1b" in output else "[universal] [ACTIVE ON THIS HOST (Windows)]", output)

    def test_resolve_template_target_direct_file(self):
        resolved = resolve_template_target(self.state, str(self.tpl_path))
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.resolve(), self.tpl_path.resolve())

    def test_view_template(self):
        ret = view_template(self.state, str(self.tpl_path))
        self.assertEqual(ret, 0)


if __name__ == "__main__":
    unittest.main()
