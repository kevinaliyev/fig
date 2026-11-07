"""Command Line Interface for Fig.
Fast, auditable user & system dotfile and configuration manager.
"""

from __future__ import annotations

import os
import sys
import argparse
from pathlib import Path
from typing import List, Optional

from fig import __version__
from fig.core.platform import CURRENT_OS
from fig.core.config import FigState, get_fig_home
from fig.core.engine import FigEngine, EngineResult
from fig.core.backup import list_all_backups
from fig.core.profiles import ProfileManager, BorrowSessionManager
from fig.core.wizard import run_interactive_wizard


def print_banner() -> None:
    print(f"fig v{__version__} ({CURRENT_OS.value}) — Configuration & Dotfile Manager\n")


def print_engine_result(result: EngineResult) -> None:
    action_title = "Preview Plan (Dry Run)" if result.dry_run else f"Action: {result.action.upper()}"
    print(f"\n--- {action_title} [{result.template_name}] ---")
    print(f"Platform:   {CURRENT_OS.value.capitalize()}")
    print(f"Repository: {result.repo_root}")

    if result.backup_id:
        print(f"Backup Vault Session: {result.backup_id}")

    if result.backed_up:
        print(f"\nBacked up {len(result.backed_up)} colliding item(s):")
        for p in result.backed_up:
            print(f"  [BACKUP] {p}")

    if result.created:
        verb = "Would link" if result.dry_run else "Linked"
        print(f"\n{verb} {len(result.created)} item(s):")
        for src, dest in result.created:
            print(f"  [+] {dest} -> {src}")

    if result.already_linked:
        print(f"\nAlready synchronized ({len(result.already_linked)} item(s)):")
        for src, dest in result.already_linked:
            print(f"  [=] {dest}")

    if result.failed:
        print(f"\nFailures ({len(result.failed)}):")
        for src, dest, err in result.failed:
            print(f"  [!] {dest}: {err}")
    
    print()


def cmd_bootstrap(engine: FigEngine, path: Path, dry_run: bool) -> int:
    try:
        res = engine.bootstrap(path, dry_run=dry_run)
        print_engine_result(res)
        return 0 if res.is_success else 1
    except Exception as e:
        print(f"Error during bootstrap: {e}", file=sys.stderr)
        return 1


def cmd_sync(engine: FigEngine, dry_run: bool) -> int:
    try:
        res = engine.apply(dry_run=dry_run)
        print_engine_result(res)
        return 0 if res.is_success else 1
    except Exception as e:
        print(f"Error during sync: {e}", file=sys.stderr)
        return 1


def cmd_check(engine: FigEngine) -> int:
    info = engine.status()
    if "error" in info:
        print(info["error"])
        return 1

    print(f"Platform:        {CURRENT_OS.value.capitalize()}")
    print(f"Active Template: {info['active_template']}")
    print(f"Repository Root: {info['repo_root']}\n")

    mappings = info.get("mappings", [])
    if not mappings:
        print("No mappings configured in active template.")
        return 0

    print("Target Statuses:")
    for m in mappings:
        st = m["status"]
        if st == "linked":
            tag = "[OK]      "
        elif st == "drifted":
            tag = "[DRIFT]   "
        elif st == "collision":
            tag = "[CONFLICT]"
        else:
            tag = "[MISSING] "
        
        detail = f" -> {m['current_target']}" if m.get("current_target") else ""
        print(f"  {tag} {m['destination']}{detail}")

    return 0


def cmd_undo(engine: FigEngine, backup_id: Optional[str]) -> int:
    try:
        restored, removed_new = engine.restore_backup(backup_id)
        print("Undo / Rollback complete.")
        if restored:
            print(f"\nRestored {len(restored)} original file(s):")
            for r in restored:
                print(f"  [RESTORED] {r}")
        if removed_new:
            print(f"\nRemoved {len(removed_new)} newly deployed file(s):")
            for rm in removed_new:
                print(f"  [REMOVED]  {rm}")
        return 0
    except Exception as e:
        print(f"Error during undo: {e}", file=sys.stderr)
        return 1


def cmd_history(engine: FigEngine) -> int:
    backups = list_all_backups(engine.state.backups_dir)
    if not backups:
        print("No backup history found in Fig vault.")
        return 0

    print(f"Fig Backup History ({engine.state.backups_dir}):\n")
    for b in backups:
        print(f"  Session ID: {b['id']}")
        print(f"    Date:     {b['timestamp']}")
        print(f"    Reason:   {b['reason']}")
        print(f"    Items:    {b['overridden_count']} overridden file(s)")
        print()
    return 0


def cmd_temp(engine: FigEngine, repo_dir: Path) -> int:
    """Temporarily deploy dotfiles for a work session on a coworker/shared machine."""
    bm = BorrowSessionManager(engine.state)
    if bm.has_active_borrow():
        print("An active temporary session already exists. Run 'fig revert' first.", file=sys.stderr)
        return 1

    prev_active = engine.state.get_active_template_path()
    res = engine.bootstrap(repo_dir, dry_run=False)
    print_engine_result(res)

    if res.is_success and res.backup_id:
        bm.record_borrow(
            backup_id=res.backup_id,
            prev_active_template=str(prev_active) if prev_active else None,
        )
        print("Temporary override active! Run 'fig revert' when finished to restore original state.")
        return 0
    return 1


def cmd_revert(engine: FigEngine) -> int:
    """Revert temporary session and restore original machine state."""
    bm = BorrowSessionManager(engine.state)
    info = bm.get_borrow_info()
    if not info:
        print("No active temporary session found to revert.")
        return 0

    backup_id = info.get("backup_id")
    print(f"Reverting temporary session (backup ID: {backup_id})...")
    res_code = cmd_undo(engine, backup_id)
    if res_code == 0:
        prev_active = info.get("prev_active_template")
        if prev_active and Path(prev_active).exists():
            engine.state.set_active_template_path(Path(prev_active))
        bm.clear_borrow()
        print("Workstation reverted cleanly to prior state.")
    return res_code


def main(argv: Optional[List[str]] = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser(
        prog="fig",
        description=f"Fig v{__version__} ({CURRENT_OS.value}) — Auditable Configuration & Dotfile Manager",
    )
    parser.add_argument("-v", "--version", action="version", version=f"fig {__version__}")
    parser.add_argument(
        "--bootstrap", "-bootstrap", "-b",
        nargs="?",
        const=".",
        metavar="DIR",
        help="Bootstrap dotfiles from DIR (default: current directory)",
    )
    parser.add_argument(
        "--preview", "--dry-run", "-n",
        dest="preview",
        action="store_true",
        help="Preview changes without modifying filesystem",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # bootstrap
    sp_boot = subparsers.add_parser("bootstrap", help="Deploy dotfiles from repository & register as active")
    sp_boot.add_argument("path", nargs="?", default=".", help="Path to dotfiles directory (default: .)")
    sp_boot.add_argument("--preview", "-n", action="store_true", help="Preview changes")

    # sync / apply
    sp_sync = subparsers.add_parser("sync", aliases=["apply"], help="Synchronize system with active template")
    sp_sync.add_argument("--preview", "-n", action="store_true", help="Preview changes")

    # check (alias: status)
    subparsers.add_parser("check", aliases=["status"], help="Check health and link status of managed dotfiles")

    # preview (alias: diff)
    subparsers.add_parser("preview", aliases=["diff"], help="Preview planned changes against active template")

    # undo (alias: rollback, restore)
    sp_undo = subparsers.add_parser("undo", aliases=["rollback", "restore"], help="Undo changes and restore previous files")
    sp_undo.add_argument("backup_id", nargs="?", help="Specific backup ID to restore (default: most recent)")

    # history (alias: backups)
    subparsers.add_parser("history", aliases=["backups"], help="List backup vault history")

    # temp (alias: guest, borrow)
    sp_temp = subparsers.add_parser("temp", aliases=["guest", "borrow"], help="Temporarily deploy dotfiles on coworker machine")
    sp_temp.add_argument("path", help="Path to dotfile repository")

    # revert (alias: unborrow)
    subparsers.add_parser("revert", aliases=["unborrow"], help="Revert temporary dotfile override and restore original state")

    # setup (interactive REPL wizard)
    sp_setup = subparsers.add_parser("setup", help="Run interactive setup wizard to generate starter fig.toml")
    sp_setup.add_argument("path", nargs="?", default=".", help="Output directory (default: .)")

    # profile
    sp_profile = subparsers.add_parser("profile", help="Manage named configuration profiles")
    sp_profile_sub = sp_profile.add_subparsers(dest="profile_action")
    sp_profile_sub.add_parser("list", help="List available profiles")
    sp_prof_switch = sp_profile_sub.add_parser("switch", help="Switch active profile")
    sp_prof_switch.add_argument("name", help="Profile name to activate")

    args = parser.parse_args(argv)

    engine = FigEngine()

    # Case 1: Flag --bootstrap or -bootstrap passed
    if args.bootstrap is not None:
        target_path = Path(args.bootstrap).resolve()
        return cmd_bootstrap(engine, target_path, dry_run=args.preview)

    # Case 2: Subcommands
    cmd = args.command
    if cmd == "bootstrap":
        return cmd_bootstrap(engine, Path(args.path).resolve(), dry_run=args.preview or getattr(args, "preview", False))
    elif cmd in ("sync", "apply"):
        return cmd_sync(engine, dry_run=args.preview or getattr(args, "preview", False))
    elif cmd in ("check", "status"):
        return cmd_check(engine)
    elif cmd in ("preview", "diff"):
        return cmd_sync(engine, dry_run=True)
    elif cmd in ("undo", "rollback", "restore"):
        return cmd_undo(engine, args.backup_id)
    elif cmd in ("history", "backups"):
        return cmd_history(engine)
    elif cmd in ("temp", "guest", "borrow"):
        return cmd_temp(engine, Path(args.path).resolve())
    elif cmd in ("revert", "unborrow"):
        return cmd_revert(engine)
    elif cmd == "setup":
        run_interactive_wizard(Path(args.path).resolve(), interactive=sys.stdin.isatty())
        return 0
    elif cmd == "profile":
        pm = ProfileManager(engine.state)
        if args.profile_action == "list":
            profs = pm.list_profiles()
            if not profs:
                print("No profiles found in ~/.fig/profiles/.")
            else:
                for p in profs:
                    act = " (active)" if p["is_active"] else ""
                    print(f"  {p['name']}{act}")
            return 0
        elif args.profile_action == "switch":
            try:
                pm.switch_profile(args.name)
                print(f"Switched active profile to '{args.name}'. Synchronizing...")
                return cmd_sync(engine, dry_run=False)
            except Exception as e:
                print(f"Error switching profile: {e}", file=sys.stderr)
                return 1
        else:
            sp_profile.print_help()
            return 0

    # Case 3: Bare 'fig' with no arguments
    active_path = engine.state.get_active_template_path()
    if active_path and active_path.exists():
        # Active template exists -> routine sync
        return cmd_sync(engine, dry_run=args.preview)
    else:
        # No active template exists and not bootstrap -> enter interactive setup wizard
        is_interactive = sys.stdin.isatty()
        if is_interactive:
            run_interactive_wizard(Path.cwd(), interactive=True)
            return 0
        else:
            # Non-interactive shell (e.g. pipe, script)
            print_banner()
            print("No active template configured.")
            print("To generate a starter template, run: fig setup")
            print("To bootstrap from your dotfiles repo, run: fig -bootstrap /path/to/dotfiles\n")
            return 0


if __name__ == "__main__":
    sys.exit(main())
