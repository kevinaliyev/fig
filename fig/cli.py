"""Command Line Interface for Fig.
Supports both subcommand syntax ('fig bootstrap') and classic flag syntax ('fig --bootstrap').
"""

from __future__ import annotations

import os
import sys
import argparse
from pathlib import Path
from typing import List, Optional

from fig import __version__
from fig.core.config import FigState, get_fig_home
from fig.core.engine import FigEngine, EngineResult
from fig.core.backup import list_all_backups
from fig.core.profiles import ProfileManager, BorrowSessionManager
from fig.core.template import Template, generate_default_template


def print_banner() -> None:
    print(f"fig v{__version__} - Dotfile and Configuration Manager\n")


def print_engine_result(result: EngineResult) -> None:
    action_title = "Dry Run Plan" if result.dry_run else f"Action: {result.action.upper()}"
    print(f"\n--- {action_title} [{result.template_name}] ---")
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


def cmd_apply(engine: FigEngine, dry_run: bool) -> int:
    try:
        res = engine.apply(dry_run=dry_run)
        print_engine_result(res)
        return 0 if res.is_success else 1
    except Exception as e:
        print(f"Error during apply: {e}", file=sys.stderr)
        return 1


def cmd_status(engine: FigEngine) -> int:
    info = engine.status()
    if "error" in info:
        print(info["error"])
        return 1

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


def cmd_restore(engine: FigEngine, backup_id: Optional[str]) -> int:
    try:
        restored, removed_new = engine.restore_backup(backup_id)
        print("Restoration complete.")
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
        print(f"Error during restore: {e}", file=sys.stderr)
        return 1


def cmd_backups(engine: FigEngine) -> int:
    backups = list_all_backups(engine.state.backups_dir)
    if not backups:
        print("No backups found in Fig vault.")
        return 0

    print(f"Fig Backup Vault ({engine.state.backups_dir}):\n")
    for b in backups:
        print(f"  Session ID: {b['id']}")
        print(f"    Date:     {b['timestamp']}")
        print(f"    Reason:   {b['reason']}")
        print(f"    Items:    {b['overridden_count']} overridden file(s)")
        print()
    return 0


def cmd_init(target_dir: Path) -> int:
    out_file = target_dir / "fig.toml"
    if out_file.exists():
        print(f"Template already exists at {out_file}", file=sys.stderr)
        return 1
    tpl = generate_default_template(target_dir)
    tpl.save(out_file)
    print(f"Created template at {out_file}")
    return 0


def cmd_borrow(engine: FigEngine, repo_dir: Path) -> int:
    bm = BorrowSessionManager(engine.state)
    if bm.has_active_borrow():
        print("An active borrow session already exists. Run 'fig unborrow' first.", file=sys.stderr)
        return 1

    prev_active = engine.state.get_active_template_path()
    res = engine.bootstrap(repo_dir, dry_run=False)
    print_engine_result(res)

    if res.is_success and res.backup_id:
        bm.record_borrow(
            backup_id=res.backup_id,
            prev_active_template=str(prev_active) if prev_active else None,
        )
        print("Temporary 'borrow' mode active! Run 'fig unborrow' or 'fig revert' when finished.")
        return 0
    return 1


def cmd_unborrow(engine: FigEngine) -> int:
    bm = BorrowSessionManager(engine.state)
    info = bm.get_borrow_info()
    if not info:
        print("No active borrow session found.")
        return 0

    backup_id = info.get("backup_id")
    print(f"Reverting temporary session (backup ID: {backup_id})...")
    res_code = cmd_restore(engine, backup_id)
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

    # Handle custom flags like -bootstrap or --bootstrap at top-level
    parser = argparse.ArgumentParser(
        prog="fig",
        description="Fig: Fast, Auditable Dotfile and Configuration Manager",
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
        "--dry-run", "-n",
        action="store_true",
        help="Simulate actions without modifying filesystem",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # bootstrap subcommand
    sp_boot = subparsers.add_parser("bootstrap", help="Deploy dotfiles from repository")
    sp_boot.add_argument("path", nargs="?", default=".", help="Path to dotfiles directory")
    sp_boot.add_argument("--dry-run", "-n", action="store_true", help="Preview changes")

    # apply subcommand
    sp_apply = subparsers.add_parser("apply", help="Synchronize against active template")
    sp_apply.add_argument("--dry-run", "-n", action="store_true", help="Preview changes")

    # status subcommand
    subparsers.add_parser("status", help="Inspect active template and link health")

    # diff subcommand
    subparsers.add_parser("diff", help="Preview changes against active template")

    # restore subcommand
    sp_restore = subparsers.add_parser("restore", help="Restore files from backup vault")
    sp_restore.add_argument("backup_id", nargs="?", help="Specific backup ID to restore")

    # backups subcommand
    subparsers.add_parser("backups", help="List all backup sessions")

    # init subcommand
    sp_init = subparsers.add_parser("init", help="Generate initial fig.toml template in directory")
    sp_init.add_argument("path", nargs="?", default=".", help="Target directory")

    # borrow & unborrow / revert
    sp_borrow = subparsers.add_parser("borrow", help="Temporarily deploy dotfiles on coworker machine")
    sp_borrow.add_argument("path", help="Path to dotfile repository")

    subparsers.add_parser("unborrow", help="Cleanly revert temporary dotfile takeover")
    subparsers.add_parser("revert", help="Alias for unborrow")

    # profile subcommand
    sp_profile = subparsers.add_parser("profile", help="Manage named configuration profiles")
    sp_profile_sub = sp_profile.add_subparsers(dest="profile_action")
    sp_profile_sub.add_parser("list", help="List profiles")
    sp_prof_switch = sp_profile_sub.add_parser("switch", help="Switch active profile")
    sp_prof_switch.add_argument("name", help="Profile name")

    args = parser.parse_args(argv)

    engine = FigEngine()

    # Case 1: Flag --bootstrap or -bootstrap was passed
    if args.bootstrap is not None:
        target_path = Path(args.bootstrap).resolve()
        return cmd_bootstrap(engine, target_path, dry_run=args.dry_run)

    # Case 2: Subcommand specified
    if args.command == "bootstrap":
        return cmd_bootstrap(engine, Path(args.path).resolve(), dry_run=args.dry_run or args.dry_run)
    elif args.command == "apply":
        return cmd_apply(engine, dry_run=args.dry_run)
    elif args.command == "status":
        return cmd_status(engine)
    elif args.command == "diff":
        return cmd_apply(engine, dry_run=True)
    elif args.command == "restore":
        return cmd_restore(engine, args.backup_id)
    elif args.command == "backups":
        return cmd_backups(engine)
    elif args.command == "init":
        return cmd_init(Path(args.path).resolve())
    elif args.command == "borrow":
        return cmd_borrow(engine, Path(args.path).resolve())
    elif args.command in ("unborrow", "revert"):
        return cmd_unborrow(engine)
    elif args.command == "profile":
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
                print(f"Switched active profile to '{args.name}'. Applying...")
                return cmd_apply(engine, dry_run=False)
            except Exception as e:
                print(f"Error switching profile: {e}", file=sys.stderr)
                return 1
        else:
            sp_profile.print_help()
            return 0

    # Case 3: No command or flags -> Default behavior: apply active template
    active_path = engine.state.get_active_template_path()
    if active_path and active_path.exists():
        return cmd_apply(engine, dry_run=args.dry_run)
    else:
        # No active template yet: show welcoming guide
        print_banner()
        print("No active template configured.")
        print("To bootstrap dotfiles from a repository directory:")
        print("  fig bootstrap /path/to/dotfiles")
        print("  or: cd /path/to/dotfiles && fig --bootstrap\n")
        print("Run 'fig --help' for all options.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
