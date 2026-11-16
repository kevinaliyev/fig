"""Cross-Platform Linking Engine.
Provides atomic symlinking, junctions, hardlinks, collision detection,
and cross-platform permission fallback (e.g. Windows Dev Mode vs Junctions).
"""

from __future__ import annotations

import os
import sys
import stat
import shutil
import subprocess
from enum import Enum
from pathlib import Path
from typing import Optional, Tuple


class LinkMode(str, Enum):
    AUTO = "auto"
    SYMLINK = "symlink"
    HARDLINK = "hardlink"
    JUNCTION = "junction"
    COPY = "copy"


class LinkStatus(str, Enum):
    ALREADY_LINKED = "already_linked"
    WOULD_CREATE = "would_create"
    CREATED = "created"
    COLLISION = "collision"
    FAILED = "failed"


def is_windows() -> bool:
    return sys.platform.startswith("win")


def is_symlink_or_junction(path: Path) -> bool:
    """Return True if path is a symlink or directory junction."""
    try:
        if path.is_symlink():
            return True
        if sys.platform.startswith("win"):
            st = os.lstat(str(path))
            return bool(st.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    except (OSError, ValueError):
        return False
    return False


def get_link_target(path: Path) -> Optional[Path]:
    """Resolve what the link or junction points to, without resolving recursively."""
    try:
        if is_symlink_or_junction(path):
            target_str = os.readlink(str(path))
            for prefix in ("\\\\?\\", "\\\\??\\", "\\??\\"):
                if target_str.startswith(prefix):
                    target_str = target_str[len(prefix):]
            target_path = Path(target_str)
            if not target_path.is_absolute():
                target_path = (path.parent / target_path).resolve()
            return target_path
    except (OSError, ValueError):
        pass
    return None


def create_directory_junction(src: Path, dest: Path) -> None:
    """Create an unprivileged directory junction on Windows."""
    # Attempt Win32 API junction or fallback to mklink /J
    cmd = ["cmd", "/c", "mklink", "/J", str(dest), str(src)]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        raise OSError(f"Failed to create directory junction: {res.stderr or res.stdout}")


def remove_link_or_entry(path: Path) -> None:
    """Safely remove a link, file, or empty directory."""
    if not path.exists() and not is_symlink_or_junction(path):
        return
    
    # On Windows, directory junctions report is_symlink() == False in some pythons,
    # or is_dir() == True. Using rmdir on junction removes the link without deleting contents.
    if is_symlink_or_junction(path):
        try:
            path.unlink()
            return
        except OSError:
            if path.is_dir():
                os.rmdir(path)
                return
            raise

    if path.is_dir():
        # Check if it's a junction or real dir
        try:
            os.rmdir(path)
        except OSError:
            shutil.rmtree(path)
    else:
        path.unlink()


def deploy_link(
    src: Path,
    dest: Path,
    mode: LinkMode = LinkMode.AUTO,
    dry_run: bool = False,
) -> Tuple[LinkStatus, str]:
    """Deploy link from src to dest.
    Returns (LinkStatus, descriptive message).
    """
    src = src.resolve()
    dest_path = Path(os.path.expanduser(str(dest))).absolute()

    if not src.exists():
        return LinkStatus.FAILED, f"Source path does not exist: {src}"

    # Self-link check: ensure destination path is not literally identical to source path
    try:
        dest_location = dest_path.parent.resolve() / dest_path.name
    except Exception:
        dest_location = dest_path

    if os.path.normcase(os.path.normpath(str(src))) == os.path.normcase(os.path.normpath(str(dest_location))):
        return LinkStatus.FAILED, f"Source and destination cannot be identical: {src}"

    # Check if already correctly linked or in sync
    if is_symlink_or_junction(dest_path):
        existing_target = get_link_target(dest_path)
        if existing_target:
            try:
                if existing_target.resolve() == src or os.path.samefile(existing_target, src):
                    return LinkStatus.ALREADY_LINKED, f"Already linked: {dest_path} -> {src}"
            except (OSError, ValueError):
                pass
        try:
            if dest_path.resolve() == src:
                return LinkStatus.ALREADY_LINKED, f"Already linked: {dest_path} -> {src}"
        except (OSError, ValueError):
            pass

    try:
        if dest_path.exists():
            if os.path.samefile(src, dest_path):
                return LinkStatus.ALREADY_LINKED, f"Already linked: {dest_path} -> {src}"
            if dest_path.is_file() and src.is_file() and dest_path.stat().st_size == src.stat().st_size:
                if dest_path.read_bytes() == src.read_bytes():
                    return LinkStatus.ALREADY_LINKED, f"Already in sync: {dest_path} -> {src}"
    except (OSError, ValueError):
        pass

    # In dry run, announce what would happen
    if dry_run:
        if dest_path.exists() or is_symlink_or_junction(dest_path):
            return LinkStatus.COLLISION, f"Would override existing file/link: {dest_path}"
        return LinkStatus.WOULD_CREATE, f"Would create link: {dest_path} -> {src}"

    # Ensure parent dir exists
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    # Remove existing destination if present
    if dest_path.exists() or is_symlink_or_junction(dest_path):
        remove_link_or_entry(dest_path)

    # Perform linking according to mode
    is_dir = src.is_dir()

    if mode == LinkMode.COPY:
        if is_dir:
            shutil.copytree(src, dest_path)
        else:
            shutil.copy2(src, dest_path)
        return LinkStatus.CREATED, f"Copied: {src} -> {dest_path}"

    if mode == LinkMode.HARDLINK:
        if is_dir:
            return LinkStatus.FAILED, f"Hardlinks cannot be created for directories: {src}"
        os.link(src, dest_path)
        return LinkStatus.CREATED, f"Hardlinked: {dest_path} -> {src}"

    if mode == LinkMode.JUNCTION:
        if not is_dir:
            return LinkStatus.FAILED, f"Junctions can only be created for directories: {src}"
        create_directory_junction(src, dest_path)
        return LinkStatus.CREATED, f"Junction created: {dest_path} -> {src}"

    # AUTO or SYMLINK mode
    try:
        os.symlink(src, dest_path, target_is_directory=is_dir)
        return LinkStatus.CREATED, f"Symlinked: {dest_path} -> {src}"
    except OSError as err:
        # Check for Windows WinError 1314 (Privilege not held / Developer Mode disabled)
        if is_windows() and getattr(err, "winerror", None) == 1314:
            if is_dir:
                try:
                    create_directory_junction(src, dest_path)
                    return LinkStatus.CREATED, f"Junction created (Windows fallback): {dest_path} -> {src}"
                except Exception as junc_err:
                    return LinkStatus.FAILED, f"Windows junction fallback failed: {junc_err}"
            else:
                try:
                    os.link(src, dest_path)
                    return LinkStatus.CREATED, f"Hardlink created (Windows fallback): {dest_path} -> {src}"
                except Exception:
                    try:
                        shutil.copy2(src, dest_path)
                        return LinkStatus.CREATED, f"Copied (Windows fallback): {dest_path} -> {src}"
                    except Exception as copy_err:
                        return LinkStatus.FAILED, f"Windows copy fallback failed: {copy_err}"
        
        return LinkStatus.FAILED, f"Failed to link {src} -> {dest_path}: {err}"
