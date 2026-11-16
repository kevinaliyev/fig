"""Unit Tests for Interactive Menu Subsystem."""

import io
import unittest
from unittest.mock import patch

from fig.ui.menu import interactive_select, format_popup_box


class TestInteractiveMenu(unittest.TestCase):
    def test_format_popup_box(self):
        items = [
            ("Option 1", "First description"),
            ("Option 2", "Second description"),
        ]
        lines = format_popup_box("Test Title", items, selected_idx=0, width=50)
        self.assertGreater(len(lines), 3)
        self.assertIn("Test Title", lines[0])
        self.assertIn("Option 1", lines[1])

    @patch("sys.stdin.isatty", return_value=False)
    @patch("builtins.input", return_value="2")
    def test_interactive_select_non_interactive_choice(self, mock_input, mock_isatty):
        options = [("Alpha", "First"), ("Beta", "Second"), ("Gamma", "Third")]
        idx = interactive_select("Choose Letter", options, default_idx=0)
        self.assertEqual(idx, 1)  # 2nd item is index 1

    @patch("sys.stdin.isatty", return_value=False)
    @patch("builtins.input", return_value="")
    def test_interactive_select_non_interactive_default(self, mock_input, mock_isatty):
        options = ["One", "Two", "Three"]
        idx = interactive_select("Numbers", options, default_idx=2)
        self.assertEqual(idx, 2)

    def test_interactive_select_empty_options(self):
        self.assertIsNone(interactive_select("Empty", []))


if __name__ == "__main__":
    unittest.main()
