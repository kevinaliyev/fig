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
from fig.core.template import Template, discover_template
from fig.core.logger import log_event
from fig.modules.profiles import ProfileManager, BorrowSessionManager
from fig.modules.builder import run_builder
from fig.modules.viewer import view_template, edit_template, list_templates
from fig.modules.wizard import run_interactive_wizard
from fig.modules.system import SystemConfigManager


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


def cmd_bootstrap(engine: FigEngine, path: Path, dry_run: bool, is_system: bool = False, force_yes: bool = False) -> int:
    try:
        res = engine.bootstrap(path, dry_run=dry_run)
        print_engine_result(res)
        if not res.is_success:
            return 1

        if is_system:
            tpl_path = engine.state.get_active_template_path()
            if tpl_path:
                tpl = Template.load(tpl_path)
                sys_res = SystemConfigManager(engine.state).apply_system(
                    tpl, path, force_yes=force_yes, dry_run=dry_run
                )
                print_engine_result(sys_res)
                return 0 if sys_res.is_success else 1

        return 0
    except Exception as e:
        print(f"Error during bootstrap: {e}", file=sys.stderr)
        log_event(f"Bootstrap failure: {e}", is_system=is_system, level="ERROR")
        return 1


def cmd_sync(engine: FigEngine, dry_run: bool, is_system: bool = False, force_yes: bool = False) -> int:
    try:
        active_path = engine.state.get_active_template_path()
        if not active_path or not active_path.exists():
            raise RuntimeError("No active template registered. Run 'fig bootstrap' first.")

        cfg = engine.state.load_config()
        repo_root_str = cfg.get("active", {}).get("repo_root")
        repo_root = Path(repo_root_str).resolve() if repo_root_str else active_path.parent.resolve()
        tpl = Template.load(active_path)

        if is_system:
            # System mode deployment
            res = SystemConfigManager(engine.state).apply_system(
                tpl, repo_root, force_yes=force_yes, dry_run=dry_run
            )
        else:
            # User mode deployment
            res = engine.apply(dry_run=dry_run)

        print_engine_result(res)
        return 0 if res.is_success else 1
    except Exception as e:
        print(f"Error during sync: {e}", file=sys.stderr)
        log_event(f"Sync failure: {e}", is_system=is_system, level="ERROR")
        return 1


def cmd_check(engine: FigEngine, is_system: bool = False) -> int:
    info = engine.status()
    if "error" in info:
        print(info["error"])
        return 1

    print(f"Platform:        {CURRENT_OS.value.capitalize()}")
    print(f"Active Template: {info['active_template']}")
    print(f"Repository Root: {info['repo_root']}\n")

    mappings = info.get("mappings", [])
    if not mappings:
        print("No user mappings configured in active template.")
    else:
        print("User Target Statuses:")
        for m in mappings:
            st = m["status"]
            tag = "[OK]      " if st == "linked" else ("[DRIFT]   " if st == "drifted" else ("[CONFLICT]" if st == "collision" else "[MISSING] "))
            detail = f" -> {m['current_target']}" if m.get("current_target") else ""
            print(f"  {tag} {m['destination']}{detail}")

    # Check system configs if present or if requested
    tpl = Template.load(Path(info["active_template"]))
    if tpl.has_system_mappings:
        print("\nSystem Target Statuses:")
        try:
            sys_plan = tpl.resolve_plan(Path(info["repo_root"]), is_system=True)
            for src, dest in sys_plan:
                exists = dest.exists() or dest.is_symlink()
                tag = "[EXISTS]  " if exists else "[NOT SET] "
                print(f"  {tag} {dest}")
        except Exception as err:
            print(f"  [!] System plan resolution error: {err}")

    return 0


def cmd_undo(engine: FigEngine, backup_id: Optional[str], is_system: bool = False, force_yes: bool = False) -> int:
    try:
        if is_system:
            restored, removed_new = SystemConfigManager(engine.state).restore_system(backup_id, force_yes=force_yes)
        else:
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
        log_event(f"Undo failure: {e}", is_system=is_system, level="ERROR")
        return 1


def cmd_history(engine: FigEngine, is_system: bool = False) -> int:
    target_vault = SystemConfigManager(engine.state).get_system_redundancy_dir() if is_system else engine.state.backups_dir
    backups = list_all_backups(target_vault)
    scope = "System Redundancy Vault" if is_system else "User Vault"

    if not backups:
        print(f"No backup history found in {scope} ({target_vault}).")
        return 0

    print(f"Fig Backup History — {scope} ({target_vault}):\n")
    for b in backups:
        print(f"  Session ID: {b['id']}")
        print(f"    Date:     {b['timestamp']}")
        print(f"    Reason:   {b['reason']}")
        print(f"    Items:    {b['overridden_count']} overridden file(s)")
        print()
    return 0


def cmd_temp(engine: FigEngine, repo_dir: Path) -> int:
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
        "--system", "-system",
        action="store_true",
        help="Operate in SYSTEM mode (targets elevated /etc, systemd, or Windows system files)",
    )
    parser.add_argument(
        "-y", "--yes",
        action="store_true",
        help="Automatic confirmation to proceed through warnings without prompting",
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
    sp_boot.add_argument("--system", "-system", action="store_true", help="Include system configurations")
    sp_boot.add_argument("-y", "--yes", action="store_true", help="Skip confirmation prompt")
    sp_boot.add_argument("--preview", "-n", action="store_true", help="Preview changes")

    # build
    sp_build = subparsers.add_parser("build", help="Build a configuration template via interactive REPL scanner")
    sp_build.add_argument("target", nargs="?", help="Directory or remote Git URL (e.g. gh:user/dotfiles)")
    sp_build.add_argument("--system", "-system", action="store_true", help="Build/review system configuration specifications")
    sp_build.add_argument("-y", "--yes", action="store_true", help="Skip confirmation prompt")

    # sync / apply
    sp_sync = subparsers.add_parser("sync", aliases=["apply"], help="Synchronize system with active template")
    sp_sync.add_argument("--system", "-system", action="store_true", help="Apply system configurations")
    sp_sync.add_argument("-y", "--yes", action="store_true", help="Skip confirmation prompt")
    sp_sync.add_argument("--preview", "-n", action="store_true", help="Preview changes")

    # check (alias: status)
    sp_check = subparsers.add_parser("check", aliases=["status"], help="Check health and link status of managed dotfiles")
    sp_check.add_argument("--system", "-system", action="store_true", help="Check system configurations")

    # preview (alias: diff)
    sp_prev = subparsers.add_parser("preview", aliases=["diff"], help="Preview planned changes against active template")
    sp_prev.add_argument("--system", "-system", action="store_true", help="Preview system configurations")

    # undo (alias: rollback, restore)
    sp_undo = subparsers.add_parser("undo", aliases=["rollback", "restore"], help="Undo changes and restore previous files")
    sp_undo.add_argument("backup_id", nargs="?", help="Specific backup ID to restore (default: most recent)")
    sp_undo.add_argument("--system", "-system", action="store_true", help="Restore system configurations from redundancy vault")
    sp_undo.add_argument("-y", "--yes", action="store_true", help="Skip confirmation prompt")

    # history (alias: backups)
    sp_hist = subparsers.add_parser("history", aliases=["backups"], help="List backup vault history")
    sp_hist.add_argument("--system", "-system", action="store_true", help="List system redundancy vault backups")

    # temp (alias: guest, borrow)
    sp_temp = subparsers.add_parser("temp", aliases=["guest", "borrow"], help="Temporarily deploy dotfiles on coworker machine")
    sp_temp.add_argument("path", help="Path to dotfile repository")

    # revert (alias: unborrow)
    subparsers.add_parser("revert", aliases=["unborrow"], help="Revert temporary dotfile override and restore original state")

    # setup (questionnaire wizard)
    sp_setup = subparsers.add_parser("setup", help="Run interactive setup wizard to generate starter fig.toml")
    sp_setup.add_argument("path", nargs="?", default=".", help="Output directory (default: .)")

    # view & edit & template
    sp_view = subparsers.add_parser("view", help="View active or specified template in clean formatted layout")
    sp_view.add_argument("target", nargs="?", help="Template name, profile name, or path")

    sp_edit = subparsers.add_parser("edit", help="Open template in visual editor ($EDITOR, nvim, notepad)")
    sp_edit.add_argument("target", nargs="?", help="Template name, profile name, or path")

    sp_tpl = subparsers.add_parser("template", help="Inspect and manage templates")
    sp_tpl_sub = sp_tpl.add_subparsers(dest="template_action")
    sp_tpl_view = sp_tpl_sub.add_parser("view", help="View template contents")
    sp_tpl_view.add_argument("target", nargs="?", help="Template name, profile name, or path")
    sp_tpl_edit = sp_tpl_sub.add_parser("edit", help="Edit template with $EDITOR")
    sp_tpl_edit.add_argument("target", nargs="?", help="Template name, profile name, or path")
    sp_tpl_sub.add_parser("list", help="List all saved templates")

    # profile
    sp_profile = subparsers.add_parser("profile", help="Manage named configuration profiles")
    sp_profile_sub = sp_profile.add_subparsers(dest="profile_action")
    sp_profile_sub.add_parser("list", help="List available profiles")
    sp_prof_switch = sp_profile_sub.add_parser("switch", help="Switch active profile")
    sp_prof_switch.add_argument("name", help="Profile name to activate")

    args = parser.parse_args(argv)

    engine = FigEngine()
    is_system_mode = getattr(args, "system", False)
    force_yes = getattr(args, "yes", False)

    # Case 1: Flag --bootstrap or -bootstrap passed
    if args.bootstrap is not None:
        target_path = Path(args.bootstrap).resolve()
        return cmd_bootstrap(engine, target_path, dry_run=args.preview, is_system=is_system_mode, force_yes=force_yes)

    # Case 2: Subcommands
    cmd = args.command
    if cmd == "bootstrap":
        return cmd_bootstrap(
            engine,
            Path(args.path).resolve(),
            dry_run=args.preview or getattr(args, "preview", False),
            is_system=is_system_mode or getattr(args, "system", False),
            force_yes=force_yes or getattr(args, "yes", False),
        )
    elif cmd == "build":
        out = run_builder(
            args.target,
            interactive=sys.stdin.isatty(),
            is_system=is_system_mode or getattr(args, "system", False),
            force_yes=force_yes or getattr(args, "yes", False),
        )
        return 0 if out else 1
    elif cmd in ("sync", "apply"):
        return cmd_sync(
            engine,
            dry_run=args.preview or getattr(args, "preview", False),
            is_system=is_system_mode or getattr(args, "system", False),
            force_yes=force_yes or getattr(args, "yes", False),
        )
    elif cmd in ("check", "status"):
        return cmd_check(engine, is_system=is_system_mode or getattr(args, "system", False))
    elif cmd in ("preview", "diff"):
        return cmd_sync(
            engine,
            dry_run=True,
            is_system=is_system_mode or getattr(args, "system", False),
            force_yes=True,
        )
    elif cmd in ("undo", "rollback", "restore"):
        return cmd_undo(
            engine,
            args.backup_id,
            is_system=is_system_mode or getattr(args, "system", False),
            force_yes=force_yes or getattr(args, "yes", False),
        )
    elif cmd in ("history", "backups"):
        return cmd_history(engine, is_system=is_system_mode or getattr(args, "system", False))
    elif cmd in ("temp", "guest", "borrow"):
        return cmd_temp(engine, Path(args.path).resolve())
    elif cmd in ("revert", "unborrow"):
        return cmd_revert(engine)
    elif cmd == "setup":
        run_interactive_wizard(Path(args.path).resolve(), interactive=sys.stdin.isatty())
        return 0
    elif cmd == "view":
        return view_template(engine.state, args.target)
    elif cmd == "edit":
        return edit_template(engine.state, args.target)
    elif cmd == "template":
        if args.template_action == "view":
            return view_template(engine.state, args.target)
        elif args.template_action == "edit":
            return edit_template(engine.state, args.target)
        else:
            return list_templates(engine.state)
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
                return cmd_sync(engine, dry_run=False, is_system=is_system_mode, force_yes=force_yes)
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
        return cmd_sync(engine, dry_run=args.preview, is_system=is_system_mode, force_yes=force_yes)
    else:
        # No active template exists and not bootstrap -> enter builder REPL
        is_interactive = sys.stdin.isatty()
        if is_interactive:
            out = run_builder(interactive=True, is_system=is_system_mode, force_yes=force_yes)
            return 0 if out else 1
        else:
            print_banner()
            print("No active template configured.")
            print("To build a template from your dotfiles: fig build [dir_or_git_url]")
            print("To bootstrap from a dotfiles repo:     fig -bootstrap /path/to/dotfiles\n")
            return 0


if __name__ == "__main__":
    sys.exit(main())
