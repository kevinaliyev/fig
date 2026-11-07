"""Fig Builder Module.
Interactive REPL that scans a repository directory (or clones a remote repo),
determines directory trees, interprets pathspec.txt, provides clean tabular
reviews with toggleable exclusions, and generates a structured fig.toml template.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from fig.core.platform import CURRENT_OS, OperatingSystem
from fig.core.scanner import RepoScanner, DiscoveredConfig
from fig.core.template import Template
from fig.core.git_clone import is_git_url, clone_remote_repo


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


def format_discovered_table(items: List[DiscoveredConfig]) -> str:
    """Format discovered configs into a clean, human-readable table."""
    lines = [
        "=" * 85,
        " Discovered Applications & Configuration Mappings",
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
) -> List[DiscoveredConfig]:
    """Interactive REPL allowing user to review, toggle exclusions, and edit mappings."""
    if not interactive or not sys.stdin.isatty():
        return items

    print(format_discovered_table(items))
    print("\nBuilder Commands:")
    print("  toggle <#>    : Toggle include/exclude (e.g. 'toggle 2')")
    print("  exclude <#>   : Exclude an application from linking")
    print("  include <#>   : Include an application")
    print("  edit <#>      : Change target destination for an item")
    print("  list          : Reprint the mappings table")
    print("  done          : Finalize and build template")
    print("  quit          : Cancel builder\n")

    while True:
        try:
            cmd_line = input("fig builder> ").strip()
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
            print(format_discovered_table(items))
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
                # Try matching by name
                name_query = parts[1].lower()
                for i, it in enumerate(items):
                    if it.app_name.lower() == name_query:
                        it.is_excluded = True
                        print(f"Excluded #{i+1} ({it.app_name})")
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
                    item.dest_expr = new_dest
                    print(f"Updated item #{idx+1} destination -> {new_dest}")
                else:
                    print(f"Invalid index: {parts[1]}")
            except ValueError:
                print(f"Please provide a number (e.g. 'edit 1')")
        else:
            print("Unknown command. Options: toggle <#>, exclude <#>, include <#>, edit <#>, list, done, quit")

    return items


def build_template_from_items(
    repo_root: Path,
    items: List[DiscoveredConfig],
) -> Template:
    """Assemble a Template object from reviewed items."""
    universal_mappings: Dict[str, str] = {}
    os_mappings: Dict[str, Dict[str, str]] = {}
    presets_set: set[str] = set()
    ignored_patterns = [".git", ".gitignore", "README.md", "fig.toml", "*.swp"]

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

    return Template(
        name=repo_root.name or "dotfiles",
        version="1.0.0",
        description=f"Generated by Fig Builder for {repo_root.name}",
        link_mode="auto",
        backup_on_collision=True,
        ignore_patterns=ignored_patterns,
        mappings=universal_mappings,
        presets=sorted(presets_set),
        os_mappings=os_mappings,
        source_file=repo_root / "fig.toml",
    )


def run_builder(
    target: Optional[str] = None,
    interactive: bool = True,
) -> Optional[Path]:
    """Execute the Fig Build workflow."""
    print("=" * 80)
    print(f"Fig Template Builder — Platform: {CURRENT_OS.value.capitalize()}")
    print("=" * 80)

    # 1. Resolve source repository
    if target:
        if is_git_url(target):
            repo_dir = clone_remote_repo(target)
        else:
            repo_dir = Path(target).resolve()
    else:
        # Prompt if CWD is the source of truth
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

    print(f"\nScanning repository tree at: {repo_dir}...")
    scanner = RepoScanner(repo_dir)
    discovered = scanner.scan()

    if not discovered:
        print("No standard configuration files or pathspecs detected.")
        if interactive:
            add_man = ask_bool("Would you like to manually add a mapping?", default=False)
            if not add_man:
                return None
            # Manual entry
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

    # 2. Interactive REPL review
    reviewed = run_builder_repl(discovered, interactive=interactive)
    if not reviewed:
        return None

    # 3. Assemble and save template
    template = build_template_from_items(repo_dir, reviewed)
    out_file = repo_dir / "fig.toml"
    template.save(out_file)

    print("\n" + "=" * 80)
    print(f"[SUCCESS] Template successfully built and saved to:\n  {out_file}")
    print("=" * 80)

    return out_file
