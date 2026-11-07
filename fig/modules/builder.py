"""Fig Builder Module.
Interactive REPL that scans a repository directory (or clones a remote repo),
determines directory trees, interprets pathspec.txt, provides clean tabular
reviews with toggleable exclusions, and generates a structured fig.toml template.
Supports dedicated -system mode for overview and confirmation of system specifications.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from fig.core.platform import CURRENT_OS, OperatingSystem
from fig.core.elevation import display_breaking_changes_warning
from fig.core.template import Template
from fig.modules.scanner import RepoScanner, DiscoveredConfig
from fig.modules.git_clone import is_git_url, clone_remote_repo


def ask_input(prompt: str, default: str = "") -> str:
    """Prompt user for input with default fallback."""
    suffix = f" [{default}]" if default else ""
    try:
        val = input(f"{prompt}{suffix}: ").strip()
        return val if val else default
    except (EOFError, KeyboardInterrupt):
        return default


def ask_bool(prompt: str, default: bool = True) -> bool:
    """Prompt user for boolean yes/no question."""
    hint = "Y/n" if default else "y/N"
    try:
        val = input(f"{prompt} [{hint}]: ").strip().lower()
        if not val:
            return default
        return val in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return default


def format_discovered_table(items: List[DiscoveredConfig], is_system: bool = False) -> str:
    """Format discovered configs into a clean, human-readable table."""
    scope_title = "SYSTEM CONFIGURATIONS" if is_system else "User Dotfiles & Application Mappings"
    lines = [
        "=" * 85,
        f" Discovered: {scope_title}",
        "=" * 85,
        f" {'#':<4} {'Inc':<5} {'Type':<7} {'Application':<15} {'Source':<20} {'Destination (Target OS)':<30}",
        "-" * 85,
    ]

    for idx, item in enumerate(items, 1):
        status_char = "[x]" if not item.is_excluded else "[ ]"
        os_tag = f" ({item.os_target})" if item.os_target else " (universal)"
        dest_display = f"{item.dest_expr}{os_tag}"
        lines.append(
            f" [{idx:<2}] {status_char:<5} {item.display_type:<7} {item.app_name:<15} "
            f"{item.source_rel:<20} {dest_display:<30}"
        )

    lines.append("=" * 85)
    return "\n".join(lines)


def run_builder_repl(
    items: List[DiscoveredConfig],
    interactive: bool = True,
    is_system: bool = False,
) -> List[DiscoveredConfig]:
    """Interactive REPL allowing user to review, toggle exclusions, and edit mappings."""
    if not interactive or not sys.stdin.isatty():
        return items

    print(format_discovered_table(items, is_system=is_system))
    print("\nBuilder Commands:")
    print("  toggle <#>    : Toggle include/exclude (e.g. 'toggle 2')")
    print("  exclude <#>   : Exclude from linking")
    print("  include <#>   : Include for linking")
    print("  edit <#>      : Change target destination for an item")
    print("  add           : Add another mapping with explicit pathspec")
    print("  list          : Reprint the mappings table")
    print("  done          : Finalize and build template")
    print("  quit          : Cancel builder\n")

    while True:
        try:
            prompt_name = "fig builder (system)" if is_system else "fig builder"
            cmd_line = input(f"{prompt_name}> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBuilder cancelled.")
            break

        if not cmd_line:
            continue

        parts = cmd_line.split()
        verb = parts[0].lower()

        if verb in ("done", "confirm", "save", "build"):
            break
        elif verb in ("quit", "exit", "cancel"):
            print("Builder cancelled without saving.")
            return []
        elif verb in ("list", "ls", "show"):
            print(format_discovered_table(items, is_system=is_system))
        elif verb in ("toggle", "t") and len(parts) > 1:
            try:
                idx = int(parts[1]) - 1
                if 0 <= idx < len(items):
                    items[idx].is_excluded = not items[idx].is_excluded
                    st = "Excluded" if items[idx].is_excluded else "Included"
                    print(f"Item #{idx+1} ({items[idx].app_name}): {st}")
                else:
                    print(f"Invalid index: {parts[1]}")
            except ValueError:
                print(f"Please provide a number (e.g. 'toggle 1')")
        elif verb in ("exclude", "ex") and len(parts) > 1:
            try:
                idx = int(parts[1]) - 1
                if 0 <= idx < len(items):
                    items[idx].is_excluded = True
                    print(f"Excluded item #{idx+1} ({items[idx].app_name})")
                else:
                    print(f"Invalid index: {parts[1]}")
            except ValueError:
                pass
        elif verb in ("include", "inc") and len(parts) > 1:
            try:
                idx = int(parts[1]) - 1
                if 0 <= idx < len(items):
                    items[idx].is_excluded = False
                    print(f"Included item #{idx+1} ({items[idx].app_name})")
            except ValueError:
                pass
        elif verb in ("edit", "e") and len(parts) > 1:
            try:
                idx = int(parts[1]) - 1
                if 0 <= idx < len(items):
                    item = items[idx]
                    new_dest = ask_input(f"Enter new destination for '{item.app_name}'", default=item.dest_expr)
                    if not new_dest.strip():
                        print("Error: Pathspec destination cannot be empty.")
                    else:
                        item.dest_expr = new_dest
                        print(f"Updated item #{idx+1} destination -> {new_dest}")
                else:
                    print(f"Invalid index: {parts[1]}")
            except ValueError:
                print("Please provide a number (e.g. 'edit 1')")
        elif verb in ("add", "new"):
            src = ask_input("Relative source path in repo")
            dest = ask_input("Mandatory destination pathspec (e.g. /etc/hosts)")
            if src and dest:
                items.append(DiscoveredConfig(
                    app_name=Path(src).stem,
                    source_rel=src,
                    dest_expr=dest,
                    is_directory=False,
                    is_system=is_system,
                    detection_source="manual pathspec",
                ))
                print(f"Added mapping: {src} -> {dest}")
        else:
            print("Unknown command. Options: toggle <#>, exclude <#>, include <#>, edit <#>, add, list, done, quit")

    return items


def build_template_from_items(
    repo_root: Path,
    items: List[DiscoveredConfig],
    is_system: bool = False,
    existing_template: Optional[Template] = None,
) -> Template:
    """Assemble or update a Template object from reviewed items."""
    tpl = existing_template or Template(
        name=repo_root.name or "dotfiles",
        version="1.0.0",
        description=f"Generated by Fig Builder for {repo_root.name}",
        link_mode="auto",
        backup_on_collision=True,
        source_file=repo_root / "fig.toml",
    )

    if is_system:
        # Update system sections
        for item in items:
            if item.is_excluded:
                continue
            if not item.dest_expr or not item.dest_expr.strip():
                raise ValueError(f"Every system spec must include an explicit destination pathspec: {item.source_rel}")
            
            if item.os_target:
                os_key = item.os_target.lower()
                tpl.os_system_mappings.setdefault(os_key, {})[item.source_rel] = item.dest_expr
            else:
                tpl.system_mappings[item.source_rel] = item.dest_expr
        return tpl

    # User dotfiles mode
    universal_mappings: Dict[str, str] = {}
    os_mappings: Dict[str, Dict[str, str]] = {}
    presets_set: set[str] = set(tpl.presets)
    ignored_patterns = list(tpl.ignore_patterns)

    for item in items:
        if item.is_excluded:
            ignored_patterns.append(item.source_rel)
            continue

        presets_set.add(item.app_name.lower())

        if item.os_target:
            os_key = item.os_target.lower()
            os_mappings.setdefault(os_key, {})[item.source_rel] = item.dest_expr
        else:
            universal_mappings[item.source_rel] = item.dest_expr

    tpl.mappings = universal_mappings
    tpl.os_mappings = os_mappings
    tpl.presets = sorted(presets_set)
    tpl.ignore_patterns = ignored_patterns
    return tpl


def run_builder(
    target: Optional[str] = None,
    interactive: bool = True,
    is_system: bool = False,
    force_yes: bool = False,
) -> Optional[Path]:
    """Execute the Fig Build workflow.
    If is_system is True: validates explicit system pathspecs and provides overview confirmation.
    """
    mode_tag = "SYSTEM CONFIGURATION MODE" if is_system else "User Dotfiles Mode"
    print("=" * 80)
    print(f"Fig Template Builder — [{mode_tag}] — Platform: {CURRENT_OS.value.capitalize()}")
    print("=" * 80)

    # 1. Resolve source repository
    if target:
        if is_git_url(target):
            repo_dir = clone_remote_repo(target)
        else:
            repo_dir = Path(target).resolve()
    else:
        cwd = Path.cwd().resolve()
        use_cwd = ask_bool(f"Use current directory ({cwd.name}) as config source of truth?", default=True) if interactive else True
        if use_cwd:
            repo_dir = cwd
        else:
            loc = ask_input("Enter path to dotfiles directory or Git URL")
            if not loc:
                print("No directory provided. Aborting builder.")
                return None
            if is_git_url(loc):
                repo_dir = clone_remote_repo(loc)
            else:
                repo_dir = Path(loc).resolve()

    if not repo_dir.is_dir():
        print(f"Error: Directory does not exist: {repo_dir}", file=sys.stderr)
        return None

    # Load existing template if present
    existing_tpl = None
    tpl_file = repo_dir / "fig.toml"
    if tpl_file.is_file():
        try:
            existing_tpl = Template.load(tpl_file)
        except Exception:
            pass

    # 2. Safety Warning if building system configs
    if is_system:
        confirmed = display_breaking_changes_warning(
            affected_paths=[],
            force_yes=force_yes,
            interactive=interactive,
        )
        if not confirmed:
            print("System builder aborted.")
            return None

    print(f"\nScanning repository tree at: {repo_dir} (system_mode={is_system})...")
    scanner = RepoScanner(repo_dir)
    discovered = scanner.scan(scan_system=is_system)

    # If in system mode and existing template already has system specs, include them in overview
    if is_system and existing_tpl and existing_tpl.has_system_mappings:
        for src, dest in existing_tpl.system_mappings.items():
            if not any(d.source_rel == src for d in discovered):
                discovered.append(DiscoveredConfig(
                    app_name=Path(src).stem,
                    source_rel=src,
                    dest_expr=dest,
                    is_directory=False,
                    is_system=True,
                    detection_source="existing fig.toml",
                ))
        for os_k, maps in existing_tpl.os_system_mappings.items():
            for src, dest in maps.items():
                if not any(d.source_rel == src and d.os_target == os_k for d in discovered):
                    discovered.append(DiscoveredConfig(
                        app_name=Path(src).stem,
                        source_rel=src,
                        dest_expr=dest,
                        is_directory=False,
                        is_system=True,
                        os_target=os_k,
                        detection_source="existing fig.toml",
                    ))

    if not discovered:
        if is_system:
            print("No system specifications with pathspec.txt found.")
            if interactive:
                add_man = ask_bool("Would you like to manually declare a system mapping now?", default=True)
                if not add_man:
                    return None
                src = ask_input("Relative source path in repo (e.g. system/hosts)")
                dest = ask_input("Mandatory destination pathspec (e.g. /etc/hosts)")
                if src and dest:
                    discovered.append(DiscoveredConfig(
                        app_name=Path(src).stem,
                        source_rel=src,
                        dest_expr=dest,
                        is_directory=False,
                        is_system=True,
                        detection_source="manual pathspec",
                    ))
            else:
                return None
        else:
            print("No standard configuration files or pathspecs detected.")
            if interactive:
                add_man = ask_bool("Would you like to manually add a mapping?", default=False)
                if not add_man:
                    return None
                src = ask_input("Relative source path in repo")
                dest = ask_input("Target destination expression (e.g. ~/.config/myapp)")
                discovered.append(DiscoveredConfig(
                    app_name=Path(src).stem,
                    source_rel=src,
                    dest_expr=dest,
                    is_directory=False,
                ))
            else:
                return None

    # 3. Interactive REPL review
    reviewed = run_builder_repl(discovered, interactive=interactive, is_system=is_system)
    if not reviewed:
        return None

    # 4. Assemble and save template
    template = build_template_from_items(
        repo_root=repo_dir,
        items=reviewed,
        is_system=is_system,
        existing_template=existing_tpl,
    )
    template.save(tpl_file)

    print("\n" + "=" * 80)
    print(f"[SUCCESS] Template successfully updated and saved to:\n  {tpl_file}")
    if is_system:
        print("\nNote: To deploy system configurations, run:")
        print("  fig -system (or 'fig apply -system')")
    print("=" * 80)

    return tpl_file
