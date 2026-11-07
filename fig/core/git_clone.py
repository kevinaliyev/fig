"""Git Remote Cloning Utility for Fig.
Supports cloning dotfile repositories from GitHub or Git URLs into local directories.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Optional, Tuple

from fig.core.config import get_fig_home


GIT_URL_PATTERNS = [
    re.compile(r"^https?://.+"),
    re.compile(r"^git@.+"),
    re.compile(r"^ssh://.+"),
    re.compile(r"^gh:([a-zA-Z0-9_\-\.]+)/([a-zA-Z0-9_\-\.]+)$"),
]


def is_git_url(target: str) -> bool:
    """Return True if target looks like a remote Git repository URL or shorthand."""
    clean = target.strip()
    return any(p.match(clean) for p in GIT_URL_PATTERNS)


def normalize_git_url(target: str) -> Tuple[str, str]:
    """Convert shorthand (gh:user/repo) into full Git URL and extract repo name."""
    clean = target.strip()
    gh_match = re.match(r"^gh:([a-zA-Z0-9_\-\.]+)/([a-zA-Z0-9_\-\.]+)$", clean)
    if gh_match:
        user, repo = gh_match.groups()
        url = f"https://github.com/{user}/{repo}.git"
        return url, repo

    # Extract repo name from URL
    name = clean.rstrip("/").split("/")[-1]
    if name.endswith(".git"):
        name = name[:-4]
    return clean, name or "dotfiles"


def clone_remote_repo(
    target: str,
    dest_dir: Optional[Path] = None,
) -> Path:
    """Clone remote Git repository to local disk and return destination Path."""
    url, repo_name = normalize_git_url(target)

    if dest_dir is None:
        repos_root = get_fig_home() / "repos"
        repos_root.mkdir(parents=True, exist_ok=True)
        clone_dest = repos_root / repo_name
    else:
        clone_dest = dest_dir.resolve()

    if clone_dest.exists():
        # Check if already cloned
        if (clone_dest / ".git").is_dir():
            print(f"Repository already cloned at: {clone_dest}")
            return clone_dest
        raise FileExistsError(f"Destination directory already exists and is not a git repo: {clone_dest}")

    print(f"Cloning {url} into {clone_dest}...")
    cmd = ["git", "clone", url, str(clone_dest)]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Git clone failed: {res.stderr or res.stdout}")

    print(f"Successfully cloned into {clone_dest}\n")
    return clone_dest
