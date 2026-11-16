"""Git Remote Cloning Utility for Fig.
Supports cloning dotfile repositories from GitHub or Git URLs into local directories,
with interactive destination selection and non-blocking authentication for SSH & private repositories.
"""

from __future__ import annotations

import os
import sys
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Tuple

from fig.config.state import get_fig_home
from fig.config.platform import get_user_home, expand_pathspec_shorthand
from fig.ui.menu import interactive_select


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

    # Extract repository name from end of path/URL
    name = clean.rstrip("/").split("/")[-1]
    # Handle SSH git@host:user/repo.git format
    if ":" in name and not name.startswith("http"):
        name = name.split(":")[-1]
    if name.endswith(".git"):
        name = name[:-4]
    return clean, name or "dotfiles"


def resolve_interactive_clone_destination(repo_name: str) -> Path:
    """Prompt user with interactive popup to choose where to clone the repository."""
    cwd_dest = Path.cwd().resolve() / repo_name
    home_dir = get_user_home()

    desktop_repos = home_dir / "Desktop" / "repos" / repo_name
    standard_repos = home_dir / "repos" / repo_name
    repos_cand = desktop_repos if desktop_repos.parent.exists() else standard_repos

    dotfiles_home = home_dir / (f".{repo_name}" if not repo_name.startswith(".") else repo_name)
    fig_store = get_fig_home() / "repos" / repo_name

    dest_options = [
        (f"./{repo_name}", f"Current Directory ({Path.cwd().name})"),
        (f"~/repos/{repo_name}", "User Repositories Folder"),
        (f"~/{dotfiles_home.name}", "Home Dotfiles Folder"),
        (f"~/.fig/repos/{repo_name}", "Fig Managed Storage"),
        ("Custom Path...", "Enter custom destination manually"),
    ]

    sel = interactive_select(f"Select Clone Destination: [{repo_name}]", dest_options, default_idx=0)
    if sel == 0 or sel is None:
        return cwd_dest
    elif sel == 1:
        return repos_cand
    elif sel == 2:
        return dotfiles_home
    elif sel == 3:
        return fig_store
    else:
        try:
            custom_input = input(f"Enter destination directory for '{repo_name}': ").strip()
            if custom_input:
                expanded = expand_pathspec_shorthand(custom_input)
                return Path(os.path.expanduser(expanded)).resolve()
        except (EOFError, KeyboardInterrupt):
            pass
        return cwd_dest


def clone_remote_repo(
    target: str,
    dest_dir: Optional[Path] = None,
    interactive: bool = True,
) -> Path:
    """Clone remote Git repository to local disk and return destination Path.
    Seamlessly handles private repositories and SSH authentication without breaking the process.
    """
    if not shutil.which("git"):
        raise RuntimeError(
            "Git executable not found in system PATH. "
            "Please install Git to clone remote dotfile repositories."
        )

    url, repo_name = normalize_git_url(target)

    if dest_dir is None:
        if interactive and sys.stdin.isatty():
            clone_dest = resolve_interactive_clone_destination(repo_name)
        else:
            # Non-interactive default: current directory / <repo_name>
            clone_dest = Path.cwd().resolve() / repo_name
    else:
        clone_dest = dest_dir.resolve()

    if clone_dest.exists():
        if (clone_dest / ".git").is_dir():
            print(f"[OK] Repository already cloned at: {clone_dest}")
            return clone_dest
        # If directory exists and is non-empty, error cleanly
        if any(clone_dest.iterdir()):
            raise FileExistsError(
                f"Destination directory already exists and is not an empty git repo: {clone_dest}"
            )

    clone_dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"Cloning {url} into {clone_dest}...")
    cmd = ["git", "clone", url, str(clone_dest)]

    if sys.stdin.isatty():
        # Interactive mode: inherit terminal I/O so SSH passphrases, host verification,
        # and Credential Manager prompts work smoothly.
        res = subprocess.run(cmd)
        if res.returncode != 0:
            error_hint = ""
            if "git@" in url or "ssh://" in url:
                error_hint = " (Check your SSH keys, ssh-agent, or repository permissions)"
            elif "http" in url:
                error_hint = " (Check your credentials, Personal Access Token, or repository permissions)"
            raise RuntimeError(f"Git clone failed with exit code {res.returncode}.{error_hint}")
    else:
        # Non-interactive mode: prevent hanging on prompts
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        if res.returncode != 0:
            err_msg = res.stderr.strip() or res.stdout.strip()
            raise RuntimeError(f"Git clone failed: {err_msg}")

    print(f"[SUCCESS] Successfully cloned into {clone_dest}\n")
    return clone_dest
