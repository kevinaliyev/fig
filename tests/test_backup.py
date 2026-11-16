"""Tests for Backup and Restore Engine."""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from fig.sync.backup import BackupSession, list_all_backups


class TestBackupRestore(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="fig_test_backup_"))
        self.backups_root = self.tmp_dir / "backups"
        self.backups_root.mkdir()

        # Existing user file that should be backed up
        self.user_file = self.tmp_dir / "my_existing_file.txt"
        self.user_file.write_text("original user content", encoding="utf-8")

        # Destination that does NOT exist beforehand
        self.new_dest = self.tmp_dir / "brand_new_file.txt"

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_backup_and_restore(self):
        # 1. Create backup session
        session = BackupSession.create(self.backups_root, reason="test_run")
        self.assertTrue(session.manifest_file.exists())

        # 2. Backup existing user file
        entry = session.backup_collision(self.user_file)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.dest_path, self.user_file)

        # 3. Simulate overwrite of user_file and creation of new_dest
        self.user_file.write_text("fig replaced content", encoding="utf-8")
        self.new_dest.write_text("newly added link", encoding="utf-8")
        session.record_new_destination(self.new_dest)

        self.assertEqual(self.user_file.read_text(encoding="utf-8"), "fig replaced content")
        self.assertTrue(self.new_dest.exists())

        # 4. Now restore!
        restored, removed_new = session.restore()

        # user_file should be back to original!
        self.assertEqual(self.user_file.read_text(encoding="utf-8"), "original user content")
        # new_dest should have been cleanly deleted!
        self.assertFalse(self.new_dest.exists())

        self.assertEqual(len(restored), 1)
        self.assertEqual(len(removed_new), 1)

    def test_list_all_backups(self):
        session1 = BackupSession.create(self.backups_root, reason="first")
        session2 = BackupSession.create(self.backups_root, reason="second")

        backups = list_all_backups(self.backups_root)
        self.assertEqual(len(backups), 2)
        reasons = [b["reason"] for b in backups]
        self.assertIn("first", reasons)
        self.assertIn("second", reasons)

    def test_backup_parent_containing_backup_root_no_recursion(self):
        # Emulate situation where destination being backed up is a parent of backups_root
        parent_dir = self.tmp_dir / "my_config_parent"
        parent_dir.mkdir()
        (parent_dir / "app_file.txt").write_text("hello world")

        # Put backup root INSIDE the parent being backed up!
        nested_backups_root = parent_dir / "fig" / "backups"
        nested_backups_root.mkdir(parents=True)

        session = BackupSession.create(nested_backups_root, reason="test_nested")
        # Backing up parent_dir must NOT recurse infinitely into nested_backups_root
        entry = session.backup_collision(parent_dir)
        self.assertIsNotNone(entry)
        self.assertTrue(entry.is_dir)

        # Restore
        (parent_dir / "app_file.txt").write_text("modified")
        session.restore()
        self.assertEqual((parent_dir / "app_file.txt").read_text(), "hello world")


if __name__ == "__main__":
    unittest.main()
