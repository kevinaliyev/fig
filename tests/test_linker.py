"""Tests for Linker Engine."""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from fig.sync.linker import deploy_link, LinkStatus, LinkMode, remove_link_or_entry


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

    def test_deploy_link_identical_source_and_destination(self):
        # Attempting to link a file to its own path must fail safely
        status, msg = deploy_link(self.src_file, self.src_file)
        self.assertEqual(status, LinkStatus.FAILED)
        self.assertIn("cannot be identical", msg)

    def test_deploy_link_already_linked_junction_or_symlink(self):
        # When destination is a symlink or junction pointing to source,
        # deploy_link must return ALREADY_LINKED, NOT fail with "cannot be identical".
        from unittest.mock import patch
        fake_dest = self.tmp_dir / "fake_link"

        with patch("fig.sync.linker.is_symlink_or_junction", return_value=True), \
             patch("fig.sync.linker.get_link_target", return_value=self.src_file):
            status, msg = deploy_link(self.src_file, fake_dest)
            self.assertEqual(status, LinkStatus.ALREADY_LINKED)
            self.assertIn("Already linked", msg)

    def test_deploy_link_already_linked_directory_resolve(self):
        # Even if get_link_target is None, if is_symlink_or_junction is True
        # and dest.resolve() == src, deploy_link returns ALREADY_LINKED
        from unittest.mock import patch
        src_dir = self.tmp_dir / "src_dir"
        src_dir.mkdir()
        fake_dest = self.tmp_dir / "dest_junc"

        with patch("fig.sync.linker.is_symlink_or_junction", return_value=True), \
             patch("fig.sync.linker.get_link_target", return_value=None), \
             patch.object(Path, "resolve", return_value=src_dir.resolve()):
            status, msg = deploy_link(src_dir, fake_dest)
            self.assertEqual(status, LinkStatus.ALREADY_LINKED)

    def test_remove_link_or_entry_broken_junction(self):
        from unittest.mock import patch, MagicMock
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = False
        mock_path.is_dir.return_value = True
        mock_path.unlink.side_effect = OSError("unlink not supported for junction")

        with patch("fig.sync.linker.is_symlink_or_junction", return_value=True), \
             patch("os.rmdir") as mock_rmdir:
            remove_link_or_entry(mock_path)
            mock_rmdir.assert_called_once_with(mock_path)


if __name__ == "__main__":
    unittest.main()
