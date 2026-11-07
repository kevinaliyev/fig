"""Tests for Platform & OS Abstraction Layer."""

import os
import unittest
from pathlib import Path

from fig.core.platform import (
    CURRENT_OS,
    OperatingSystem,
    detect_os,
    matches_current_os,
    resolve_native_path,
    get_user_home,
    get_config_home,
)


class TestPlatform(unittest.TestCase):
    def test_current_os_detected(self):
        self.assertIn(CURRENT_OS, [
            OperatingSystem.WINDOWS,
            OperatingSystem.LINUX,
            OperatingSystem.MACOS,
            OperatingSystem.BSD,
        ])
        self.assertTrue(matches_current_os(CURRENT_OS.value))

    def test_resolve_native_path_home(self):
        home_path = resolve_native_path("~")
        self.assertEqual(home_path.resolve(), get_user_home().resolve())

        sub_path = resolve_native_path("~/.test_dotfile")
        expected = (get_user_home() / ".test_dotfile").resolve()
        self.assertEqual(sub_path.resolve(), expected)

    def test_resolve_native_path_env_vars(self):
        os.environ["FIG_TEST_VAR"] = "sample_dir"
        try:
            resolved = resolve_native_path("~/subdir/$FIG_TEST_VAR/config.json")
            self.assertIn("sample_dir", str(resolved))
        finally:
            del os.environ["FIG_TEST_VAR"]

    def test_config_home_exists(self):
        cfg_home = get_config_home()
        self.assertIsInstance(cfg_home, Path)
        self.assertTrue(str(cfg_home))


if __name__ == "__main__":
    unittest.main()
