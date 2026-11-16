"""Unit tests for Git Remote Cloning Utility."""

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from fig.utils.git_clone import is_git_url, normalize_git_url, clone_remote_repo


class TestGitClone(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="fig_test_git_"))

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_is_git_url(self):
        # Valid Git URLs
        self.assertTrue(is_git_url("https://github.com/user/dotfiles.git"))
        self.assertTrue(is_git_url("http://gitlab.com/user/repo"))
        self.assertTrue(is_git_url("git@github.com:user/dotfiles.git"))
        self.assertTrue(is_git_url("ssh://git@host.com/user/repo.git"))
        self.assertTrue(is_git_url("gh:user/dotfiles"))

        # Local filesystem paths
        self.assertFalse(is_git_url("C:\\Users\\user\\dotfiles"))
        self.assertFalse(is_git_url("/home/user/dotfiles"))
        self.assertFalse(is_git_url("./dotfiles"))
        self.assertFalse(is_git_url("my-dotfiles"))

    def test_normalize_git_url(self):
        # GitHub shorthand
        url, name = normalize_git_url("gh:octocat/dotfiles")
        self.assertEqual(url, "https://github.com/octocat/dotfiles.git")
        self.assertEqual(name, "dotfiles")

        # Standard HTTPS
        url, name = normalize_git_url("https://github.com/octocat/custom-repo.git")
        self.assertEqual(url, "https://github.com/octocat/custom-repo.git")
        self.assertEqual(name, "custom-repo")

        # SSH URL
        url, name = normalize_git_url("git@github.com:octocat/ssh-dots.git")
        self.assertEqual(url, "git@github.com:octocat/ssh-dots.git")
        self.assertEqual(name, "ssh-dots")

    def test_clone_idempotent_existing_repo(self):
        """If directory already exists with a .git subfolder, return it immediately."""
        fake_repo = self.tmp_dir / "already_cloned"
        fake_repo.mkdir()
        (fake_repo / ".git").mkdir()

        with patch("shutil.which", return_value="git"):
            result = clone_remote_repo("gh:user/already_cloned", dest_dir=fake_repo)
            self.assertEqual(result.resolve(), fake_repo.resolve())

    @patch("shutil.which", return_value="git")
    @patch("subprocess.run")
    @patch("sys.stdin.isatty", return_value=False)
    def test_clone_non_interactive_sets_no_prompt_env(self, mock_isatty, mock_run, mock_which):
        """Non-interactive clone must set GIT_TERMINAL_PROMPT=0 to prevent hanging."""
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_run.return_value = mock_proc

        dest = self.tmp_dir / "new_clone"
        clone_remote_repo("https://github.com/user/dots.git", dest_dir=dest, interactive=False)

        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args[1]
        self.assertIn("env", call_kwargs)
        self.assertEqual(call_kwargs["env"].get("GIT_TERMINAL_PROMPT"), "0")

    @patch("shutil.which", return_value="git")
    @patch("subprocess.run")
    @patch("sys.stdin.isatty", return_value=False)
    def test_clone_failure_raises_runtime_error(self, mock_isatty, mock_run, mock_which):
        mock_proc = MagicMock()
        mock_proc.returncode = 128
        mock_proc.stderr = "fatal: repository 'https://github.com/user/private.git' not found"
        mock_proc.stdout = ""
        mock_run.return_value = mock_proc

        dest = self.tmp_dir / "failed_clone"
        with self.assertRaises(RuntimeError) as ctx:
            clone_remote_repo("https://github.com/user/private.git", dest_dir=dest, interactive=False)

        self.assertIn("fatal: repository", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
