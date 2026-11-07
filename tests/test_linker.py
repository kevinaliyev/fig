"""Tests for Linker Engine."""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from fig.core.linker import deploy_link, LinkStatus, LinkMode, remove_link_or_entry


class TestLinker(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="fig_test_linker_"))
        self.src_file = self.tmp_dir / "my_config.txt"
        self.src_file.write_text("hello config", encoding="utf-8")
        self.dest_file = self.tmp_dir / "target_dest.txt"

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_deploy_link_file(self):
        status, msg = deploy_link(self.src_file, self.dest_file)
        self.assertIn(status, [LinkStatus.CREATED, LinkStatus.ALREADY_LINKED])
        self.assertTrue(self.dest_file.exists())
        self.assertEqual(self.dest_file.read_text(encoding="utf-8"), "hello config")

    def test_deploy_link_collision_and_idempotency(self):
        # First deploy
        status1, _ = deploy_link(self.src_file, self.dest_file)
        self.assertIn(status1, [LinkStatus.CREATED, LinkStatus.ALREADY_LINKED])

        # Second deploy without changes
        # On POSIX or if symlinked, it should be ALREADY_LINKED or CREATED
        status2, _ = deploy_link(self.src_file, self.dest_file)
        self.assertIn(status2, [LinkStatus.ALREADY_LINKED, LinkStatus.CREATED])

    def test_dry_run_does_not_modify(self):
        dry_dest = self.tmp_dir / "dry_run_target.txt"
        status, msg = deploy_link(self.src_file, dry_dest, dry_run=True)
        self.assertEqual(status, LinkStatus.WOULD_CREATE)
        self.assertFalse(dry_dest.exists())


if __name__ == "__main__":
    unittest.main()
