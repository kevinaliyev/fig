"""Elevation, Permissions, and Safety Guard Engine for Fig.
Handles elevation detection (UAC / sudo), prominent breaking-changes warnings,
and user-confirmed elevated re-launching.
"""

from __future__ import annotations

import os
import sys
import ctypes
import subprocess
from pathlib import Path
from typing import List, Optional

from fig.core.platform import CURRENT_OS, OperatingSystem
from fig.core.logger import log_event


def is_elevated() -> bool:
    """Return True if current process is running with administrative/root privileges."""
    if CURRENT_OS == OperatingSystem.WINDOWS:
        try:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            return False
    else:
        try:
            return os.geteuid() == 0  # type: ignore[attr-defined]
        except AttributeError:
            return False


def display_breaking_changes_warning(
    affected_paths: List[str],
    force_yes: bool = False,
    interactive: bool = True,
) -> bool:
    """Display prominent breaking-changes warning banner and require confirmation.
    Can be skipped with force_yes (-y / --yes).
    """
    print("\n" + "=" * 80)
    print(" [!] CRITICAL SAFETY WARNING: SYSTEM CONFIGURATION MODE")
    print("=" * 80)
    print(" You are about to deploy or modify SYSTEM-LEVEL configuration files.")
    print(" These modifications affect the underlying operating system and may cause")
    print(" breaking changes, service daemon failures, or network disruptions if misconfigured.\n")

    if affected_paths:
        print(" Target system paths to be modified:")
        for p in affected_paths:
            print(f"   [!] {p}")
        print()

    print(" A redundant disaster-recovery backup will be archived to:")
    if CURRENT_OS == OperatingSystem.WINDOWS:
        print("   %ProgramData%\\fig\\backups\\")
    else:
        print("   /var/backups/fig/")
    print("=" * 80)

    if force_yes:
        print("[CONFIRM] Proceeding automatically (-y / --yes flag provided).\n")
        log_event("System breaking-changes warning confirmed automatically (-y)", is_system=True)
        return True

    if not interactive or not sys.stdin.isatty():
        print("Aborted: Modifying system files in a non-interactive shell requires the -y / --yes flag.", file=sys.stderr)
        log_event("System breaking-changes aborted: non-interactive shell without -y", is_system=True, level="WARN")
        return False

    try:
        ans = input("Are you sure you want to proceed with system modifications? [y/N]: ").strip().lower()
        if ans in ("y", "yes"):
            log_event("System breaking-changes warning confirmed by user interactively", is_system=True)
            return True
        else:
            print("System operation cancelled by user.")
            log_event("System operation cancelled by user at warning prompt", is_system=True)
            return False
    except (EOFError, KeyboardInterrupt):
        print("\nSystem operation cancelled.")
        return False


def request_elevation(argv: Optional[List[str]] = None, interactive: bool = True) -> int:
    """Offer to re-launch command in an elevated shell (UAC on Windows / sudo on POSIX).
    ONLY called AFTER breaking changes warning has been displayed and confirmed.
    """
    args = argv if argv is not None else sys.argv[1:]
    # Ensure -system flag remains in argument list
    if "-system" not in args and "--system" not in args:
        args = ["--system"] + args
    # Add -y flag so the elevated subshell does not redundantly re-prompt for breaking warning
    if "-y" not in args and "--yes" not in args:
        args = ["-y"] + args

    if CURRENT_OS == OperatingSystem.WINDOWS:
        if interactive and sys.stdin.isatty():
            try:
                ans = input("\nYou are not in an elevated shell. Request UAC elevation now? [Y/n]: ").strip().lower()
                if ans and ans not in ("y", "yes"):
                    print("\nOperation cancelled. Please open an elevated Administrator command prompt or PowerShell and re-run:")
                    print(f"  python -m fig {' '.join(args)}\n")
                    return 1
            except (EOFError, KeyboardInterrupt):
                print("\nOperation cancelled.")
                return 1

        print("Requesting Windows UAC elevation...")
        log_event("Triggering Windows UAC elevation", is_system=True)
        # Use PowerShell Start-Process with -Verb RunAs
        args_str = " ".join(f'\\"{a}\\"' if " " in a else a for a in ["-m", "fig"] + args)
        ps_cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            f"Start-Process '{sys.executable}' -ArgumentList '{args_str}' -Verb RunAs -Wait",
        ]
        res = subprocess.run(ps_cmd)
        return res.returncode

    else:
        # POSIX (Linux / macOS)
        if interactive and sys.stdin.isatty():
            try:
                ans = input("\nYou are not running as root. Would you like to elevate using sudo? [Y/n]: ").strip().lower()
                if ans and ans not in ("y", "yes"):
                    print("\nOperation cancelled. Please re-run your command with sudo:")
                    print(f"  sudo python3 -m fig {' '.join(args)}\n")
                    return 1
            except (EOFError, KeyboardInterrupt):
                print("\nOperation cancelled.")
                return 1

        print("Requesting sudo elevation...")
        log_event("Triggering POSIX sudo elevation", is_system=True)
        cmd = ["sudo", sys.executable, "-m", "fig"] + args
        res = subprocess.run(cmd)
        return res.returncode
