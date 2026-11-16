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
from fig.config.platform import CURRENT_OS
from fig.config.state import FigState, get_fig_home
from fig.sync.linker import is_symlink_or_junction
from fig.sync.engine import FigEngine, EngineResult
from fig.sync.backup import list_all_backups
from fig.config.template import Template, discover_template
from fig.utils.logger import log_event, log_operation
from fig.ui.ansi import (
    render_banner,
    format_table,
    badge_ok,
    badge_created,
    badge_backed_up,
    badge_conflict,
    badge_missing,
    c_cyan,
    c_green,
    c_yellow,
    c_red,
    c_bold,
    c_dim,
)
from fig.profiles.manager import ProfileManager, BorrowSessionManager
from fig.builder import run_builder, run_rebuilder
from fig.ui.viewer import view_template, edit_template, list_templates
from fig.builder.wizard import run_interactive_wizard
from fig.sync.system import SystemConfigManager
from fig.utils.cleanup import CleanupManager
from fig.utils.git_clone import is_git_url, clone_remote_repo


def print_banner() -> None:
    print(c_cyan(f"fig v{__version__} ({CURRENT_OS.value}) — Auditable Configuration & Dotfile Manager\n", bold=True))


def print_engine_result(result: EngineResult) -> None:
    action_title = "Preview Plan (Dry Run)" if result.dry_run else f"Action: {result.action.upper()}"
    print(f"\n{c_cyan('---')} {c_bold(action_title)} [{c_bold(result.template_name or 'unnamed')}] {c_cyan('---')}")
    print(f"Platform:   {CURRENT_OS.value.capitalize()}")
    print(f"Repository: {result.repo_root}")

    if result.backup_id:
        print(f"Backup Vault Session: {c_bold(result.backup_id)}")

    if result.backed_up:
        print(f"\nBacked up {len(result.backed_up)} colliding item(s) to vault (restorable with 'fig undo'):")
        for p in result.backed_up:
            print(f"  {badge_backed_up('BACKUP')} {c_yellow(str(p))}")

    if result.created:
        verb = "Would link" if result.dry_run else "Linked"
        print(f"\n{verb} {len(result.created)} item(s):")
        for src, dest in result.created:
            print(f"  {badge_created('+')} {dest} {c_dim('->')} {src}")

    if result.already_linked:
        print(f"\nAlready synchronized ({len(result.already_linked)} item(s)):")
        for src, dest in result.already_linked:
            print(f"  {badge_ok('=')} {c_dim(str(dest))}")

    if result.failed:
        print(f"\n{c_red(f'Failures ({len(result.failed)}):', bold=True)}")
        for src, dest, err in result.failed:
            print(f"  {badge_conflict('!')} {c_red(str(dest))}: {err}")

    # Explicit summary and completion status
    if result.is_success:
        if result.dry_run:
            print(f"\n{c_cyan('[OK] Dry run plan completed. No filesystem changes made.', bold=True)}")
        elif not result.created and not result.backed_up and result.already_linked:
            print(f"\n{c_green('[OK] All items are up to date. Everything is already synchronized.', bold=True)}")
        else:
            summary_parts = []
            if result.created:
                summary_parts.append(f"{len(result.created)} linked")
            if result.already_linked:
                summary_parts.append(f"{len(result.already_linked)} already in sync")
            if result.backed_up:
                summary_parts.append(f"{len(result.backed_up)} backed up")
            print(f"\n{c_green(f'[SUCCESS] Synchronization complete ({', '.join(summary_parts)}).', bold=True)}")
    else:
        print(f"\n{c_red(f'[FAILED] Synchronization finished with {len(result.failed)} error(s). Review failures above.', bold=True)}")

    print()


def cmd_bootstrap(engine: FigEngine, path: Path, dry_run: bool, is_system: bool = False, force_yes: bool = False) -> int:
    try:
        res = engine.bootstrap(path, dry_run=dry_run)
        print_engine_result(res)
        log_operation(
            "bootstrap",
            "SUCCESS" if res.is_success else "FAILED",
            f"Repo: {path}, Created: {len(res.created)}, Synced: {len(res.already_linked)}, Backups: {len(res.backed_up)}, Failures: {len(res.failed)}",
            is_system=is_system,
        )
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
                log_operation("bootstrap_system", "SUCCESS" if sys_res.is_success else "FAILED", is_system=True)
                return 0 if sys_res.is_success else 1

        return 0
    except Exception as e:
        print(f"Error during bootstrap: {e}", file=sys.stderr)
        log_event(f"Bootstrap failure: {e}", is_system=is_system, level="ERROR")
        return 1


def cmd_sync(
    engine: FigEngine,
    dry_run: bool,
    is_system: bool = False,
    force_yes: bool = False,
    check_cwd: bool = True,
) -> int:
    try:
        active_path: Optional[Path] = None
        repo_root: Optional[Path] = None

        if check_cwd:
            cwd = Path.cwd().resolve()
            cwd_tpl = cwd / "fig.toml"
            if not cwd_tpl.exists():
                cwd_tpl = cwd / ".fig.toml"

            if cwd_tpl.is_file():
                print(c_cyan(f"[INFO] Found '{cwd_tpl.name}' in current working directory ({cwd}).", bold=True))
                print(f"Applying template from: {cwd_tpl} (registered as active template).\n")
                engine.state.set_active_template_path(cwd_tpl, repo_root=cwd)
                active_path = cwd_tpl
                repo_root = cwd

        if not active_path:
            active_path = engine.state.get_active_template_path()
            if not active_path or not active_path.exists():
                raise RuntimeError(
                    "No active template registered and no 'fig.toml' found in current directory.\n"
                    "Run 'fig build' or 'fig -bootstrap' to create or register a template."
                )

            if check_cwd:
                print(c_cyan(f"[INFO] No 'fig.toml' found in current directory. Refreshing current active template:", bold=True))
                print(f"Active Template: {active_path}\n")
            else:
                print(c_cyan(f"[INFO] Refreshing current active template: {active_path}\n", bold=True))

            repo_root = engine.state.get_active_repo_root() or active_path.parent.resolve()

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
        log_operation(
            "sync",
            "SUCCESS" if res.is_success else "FAILED",
            f"Active: {active_path}, Created: {len(res.created)}, Synced: {len(res.already_linked)}, Backups: {len(res.backed_up)}, Failures: {len(res.failed)}",
            is_system=is_system,
        )
        return 0 if res.is_success else 1
    except Exception as e:
        print(f"Error during sync: {e}", file=sys.stderr)
        log_event(f"Sync failure: {e}", is_system=is_system, level="ERROR")
        return 1


def cmd_check(engine: FigEngine, is_system: bool = False) -> int:
    info = engine.status()
    if "error" in info:
        print(c_red(info["error"], bold=True))
        log_event(f"Check error: {info['error']}", is_system=is_system, level="WARN")
        return 1

    print(render_banner("Fig Status Check", f"Host OS: {CURRENT_OS.value.capitalize()}", width=80))
    print(f"  {c_bold('Platform:')}        {CURRENT_OS.value.capitalize()}")
    print(f"  {c_bold('Active Template:')} {info['active_template']}")
    print(f"  {c_bold('Repository Root:')} {info['repo_root']}\n")

    mappings = info.get("mappings", [])
    if not mappings:
        print("No user mappings configured in active template.")
    else:
        print(c_bold("User Target Statuses:"))
        for m in mappings:
            st = m["status"]
            tag = f"{badge_ok('OK')}      " if st == "linked" else (f"{c_yellow('[DRIFT]   ', bold=True)}" if st == "drifted" else (f"{badge_conflict('CONFLICT')}" if st == "collision" else f"{badge_missing('MISSING')} "))
            detail = f" {c_dim('->')} {m['current_target']}" if m.get("current_target") else ""
            print(f"  {tag} {m['destination']}{detail}")

    # Check system configs if present or if requested
    tpl = Template.load(Path(info["active_template"]))
    if tpl.has_system_mappings:
        print(f"\n{c_bold('System Target Statuses:')}")
        try:
            sys_plan = tpl.resolve_plan(Path(info["repo_root"]), is_system=True)
            for src, dest in sys_plan:
                exists = dest.exists() or is_symlink_or_junction(dest)
                tag = f"{badge_ok('EXISTS')}  " if exists else f"{badge_missing('NOT SET')} "
                print(f"  {tag} {dest}")
        except Exception as err:
            print(f"  {badge_conflict('!')} System plan resolution error: {err}")

    log_operation("check", "SUCCESS", f"Active: {info['active_template']}, Checked: {len(mappings)} mappings", is_system=is_system)
    return 0


def cmd_undo(engine: FigEngine, backup_id: Optional[str], is_system: bool = False, force_yes: bool = False) -> int:
    try:
        if is_system:
            restored, removed_new = SystemConfigManager(engine.state).restore_system(backup_id, force_yes=force_yes)
        else:
            restored, removed_new = engine.restore_backup(backup_id)

        print(c_green("Undo / Rollback complete.", bold=True))
        if restored:
            print(f"\nRestored {len(restored)} original file(s):")
            for r in restored:
                print(f"  {badge_ok('RESTORED')} {r}")
        if removed_new:
            print(f"\nRemoved {len(removed_new)} newly deployed file(s):")
            for rm in removed_new:
                print(f"  {badge_conflict('REMOVED')}  {rm}")
        log_operation("undo", "SUCCESS", f"Session: {backup_id or 'latest'}, Restored: {len(restored)}, Removed: {len(removed_new)}", is_system=is_system)
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
        log_operation("history", "SUCCESS", f"{scope}: 0 backups", is_system=is_system)
        return 0

    print(render_banner("Fig Backup History", f"{scope} ({target_vault})", width=84) + "\n")
    for b in backups:
        print(f"  {c_bold('Session ID:')} {c_cyan(b['id'])}")
        print(f"    Date:     {b['timestamp']}")
        print(f"    Reason:   {b['reason']}")
        print(f"    Items:    {b['overridden_count']} overridden file(s)")
        print()
    print(f"  {c_dim('To restore any previous session: fig undo <Session ID>')}\n")
    log_operation("history", "SUCCESS", f"{scope}: {len(backups)} backups listed", is_system=is_system)
    return 0


def cmd_temp(engine: FigEngine, repo_dir: Path) -> int:
    bm = BorrowSessionManager(engine.state)
    if bm.has_active_borrow():
        print("An active temporary session already exists. Run 'fig revert' first.", file=sys.stderr)
        log_event("Temporary session attempt rejected: active session already exists", level="WARN")
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
        log_operation("temp", "SUCCESS", f"Target: {repo_dir}, Backup: {res.backup_id}")
        return 0
    log_operation("temp", "FAILED", f"Target: {repo_dir}", level="ERROR")
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
        log_operation("revert", "SUCCESS", f"Restored backup: {backup_id}")
    else:
        log_operation("revert", "FAILED", f"Backup: {backup_id}", level="ERROR")
    return res_code


def main(argv: Optional[List[str]] = None) -> int:
    try:
        sys.setrecursionlimit(max(sys.getrecursionlimit(), 5000))
    except Exception:
        pass

    if argv is None:
        argv = sys.argv[1:]

    log_event(f"CLI Command: fig {' '.join(argv) if argv else '(bare)'}")

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
        "--dest",
        help="Destination directory if cloning a remote Git repository",
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
    sp_boot.add_argument("path", nargs="?", default=".", help="Path to dotfiles directory or remote Git URL (default: .)")
    sp_boot.add_argument("--dest", help="Destination directory if cloning a remote Git repository")
    sp_boot.add_argument("--system", "-system", action="store_true", help="Include system configurations")
    sp_boot.add_argument("-y", "--yes", action="store_true", help="Skip confirmation prompt")
    sp_boot.add_argument("--preview", "-n", action="store_true", help="Preview changes")

    # build
    sp_build = subparsers.add_parser("build", help="Build a configuration template via interactive REPL scanner")
    sp_build.add_argument("target", nargs="?", help="Directory or remote Git URL (e.g. gh:user/dotfiles)")
    sp_build.add_argument("--dest", help="Destination directory if cloning a remote Git repository")
    sp_build.add_argument("--system", "-system", action="store_true", help="Build/review system configuration specifications")
    sp_build.add_argument("-y", "--yes", action="store_true", help="Skip confirmation prompt")

    # rebuild
    sp_rebuild = subparsers.add_parser("rebuild", help="Rebuild / edit template inside interactive REPL without losing custom settings")
    sp_rebuild.add_argument("target", nargs="?", help="Directory or template path (default: active template source of truth)")
    sp_rebuild.add_argument("--system", "-system", action="store_true", help="Rebuild system configurations")
    sp_rebuild.add_argument("-y", "--yes", action="store_true", help="Skip confirmation prompt")

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
    sp_temp = subparsers.add_parser("temp", aliases=["guest", "borrow"], help="Temporarily deploy dotfiles for a session on a host machine")
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

    # clean / cleanup
    sp_clean = subparsers.add_parser("clean", aliases=["cleanup"], help="Clean repository build artifacts, caches, and clutter")
    sp_clean.add_argument("--releases", action="store_true", help="Prune obsolete version releases")
    sp_clean.add_argument("--all", action="store_true", help="Full clean (builds, caches, clutter, and old releases)")
    sp_clean.add_argument("--preview", "-n", action="store_true", help="Preview changes without deleting")

    # uninstall
    sp_uninst = subparsers.add_parser("uninstall", help="Uninstall Fig, purge active links, state directories, and binary")
    sp_uninst.add_argument("-y", "--yes", action="store_true", help="Skip confirmation prompt")
    sp_uninst.add_argument("--preserve-backups", action="store_true", help="Preserve collision backup vault")
    sp_uninst.add_argument("--system", "-system", action="store_true", help="Also purge machine disaster vault")
    sp_uninst.add_argument("--preview", "-n", action="store_true", help="Preview changes without deleting")

    args = parser.parse_args(argv)

    engine = FigEngine()
    is_system_mode = getattr(args, "system", False)
    force_yes = getattr(args, "yes", False)

    # Case 1: Flag --bootstrap or -bootstrap passed
    if args.bootstrap is not None:
        raw_b = args.bootstrap
        dest_override = Path(args.dest).resolve() if getattr(args, "dest", None) else None
        if is_git_url(raw_b):
            try:
                target_path = clone_remote_repo(raw_b, dest_dir=dest_override, interactive=sys.stdin.isatty())
            except Exception as e:
                print(f"Error cloning repository: {e}", file=sys.stderr)
                return 1
        else:
            target_path = Path(raw_b).resolve()
        return cmd_bootstrap(engine, target_path, dry_run=args.preview, is_system=is_system_mode, force_yes=force_yes)

    # Case 2: Subcommands
    cmd = args.command
    if cmd == "bootstrap":
        raw_path = args.path
        dest_override = Path(args.dest).resolve() if getattr(args, "dest", None) else None
        if is_git_url(raw_path):
            try:
                repo_path = clone_remote_repo(raw_path, dest_dir=dest_override, interactive=sys.stdin.isatty())
            except Exception as e:
                print(f"Error cloning repository: {e}", file=sys.stderr)
                return 1
        else:
            repo_path = Path(raw_path).resolve()

        return cmd_bootstrap(
            engine,
            repo_path,
            dry_run=args.preview or getattr(args, "preview", False),
            is_system=is_system_mode or getattr(args, "system", False),
            force_yes=force_yes or getattr(args, "yes", False),
        )
    elif cmd == "build":
        dest_override = Path(args.dest).resolve() if getattr(args, "dest", None) else None
        out = run_builder(
            args.target,
            dest_dir=dest_override,
            interactive=sys.stdin.isatty(),
            is_system=is_system_mode or getattr(args, "system", False),
            force_yes=force_yes or getattr(args, "yes", False),
        )
        return 0 if out else 1
    elif cmd == "rebuild":
        out = run_rebuilder(
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
            check_cwd=True,
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
    elif cmd in ("clean", "cleanup"):
        mgr = CleanupManager(engine.state)
        dry = getattr(args, "preview", False) or args.preview
        clean_rel = getattr(args, "releases", False) or getattr(args, "all", False)
        res = mgr.clean_repo_artifacts(clean_releases=clean_rel, dry_run=dry)
        total = sum(len(items) for items in res.values())
        action_word = "Would purge" if dry else "Purged"
        print(f"[*] {action_word} {total} item(s).")
        return 0
    elif cmd == "uninstall":
        mgr = CleanupManager(engine.state)
        dry = getattr(args, "preview", False) or args.preview
        if not dry and not force_yes and sys.stdin.isatty():
            ans = input("Are you sure you want to uninstall Fig and purge active links? (y/N): ").strip().lower()
            if ans not in ("y", "yes"):
                print("Uninstallation cancelled.")
                return 0
        summary = mgr.full_uninstall(
            preserve_backups=getattr(args, "preserve_backups", False),
            clean_system=is_system_mode or getattr(args, "system", False),
            dry_run=dry,
        )
        mode_str = "Simulation" if dry else "Complete"
        print(render_banner(f"Fig Uninstallation {mode_str}", width=80))
        print(f"  Restored original files: {len(summary.get('restored_files', []))}")
        print(f"  Removed deployed links:  {len(summary.get('removed_links', []))}")
        print(f"  Purged state entries:    {len(summary.get('purged_user_state', []))}")
        print(f"  Binary uninstalled:      {summary.get('binary_removed', False)}")
        return 0

    # Case 3: Bare 'fig' with no arguments
    active_path = engine.state.get_active_template_path()
    if active_path and active_path.exists():
        # Active template exists -> routine sync
        return cmd_sync(engine, dry_run=args.preview, is_system=is_system_mode, force_yes=force_yes, check_cwd=False)
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
