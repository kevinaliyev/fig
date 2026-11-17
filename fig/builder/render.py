"""Fig Builder Rendering & Tree Helpers.
Provides scoped directory table views, hierarchical tree formatting,
excluded item tables, help modals, and pathspec suggestion helpers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from fig.config.platform import CURRENT_OS, OperatingSystem
from fig.config.presets import COMMON_PRESETS, WINDOWS_PRESETS
from fig.builder.scanner import DiscoveredConfig
from fig.ui.ansi import (
    render_banner,
    format_table,
    format_box,
    get_terminal_width,
    badge_active,
    badge_kind,
    c_cyan,
    c_green,
    c_yellow,
    c_red,
    c_bold,
    c_dim,
    c_blue,
    c_magenta,
)


def _format_mode_badge(mode: str) -> str:
    """Format link mode with distinct color badge."""
    m_lower = mode.lower()
    if m_lower == "symlink":
        return c_cyan("[symlink]")
    elif m_lower == "junction":
        return c_green("[junction]")
    elif m_lower == "hardlink":
        return c_yellow("[hardlink]")
    elif m_lower == "copy":
        return c_magenta("[copy]")
    return c_blue("[auto]")


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


def parse_indices(tokens: List[str], max_len: int) -> List[int]:
    """Parse space-separated string tokens into distinct 0-based valid item indices."""
    indices: List[int] = []
    for t in tokens:
        cleaned = t.strip().lstrip("#")
        try:
            val = int(cleaned) - 1
            if 0 <= val < max_len:
                if val not in indices:
                    indices.append(val)
            else:
                print(f"Warning: Index #{cleaned} is out of range (1..{max_len}).")
        except ValueError:
            print(f"Warning: '{t}' is not a valid item number.")
    return indices


class PathSuggestion(str):
    """String subclass that holds a descriptive label for interactive menus."""
    desc: str

    def __new__(cls, path: str, desc: str = ""):
        inst = super().__new__(cls, path)
        inst.desc = desc
        return inst


def get_pathspec_suggestions(item: DiscoveredConfig) -> List[PathSuggestion]:
    """Provide sensible, standard shorthand destination suggestions for an item across platforms."""
    app_lower = item.app_name.lower()
    source_lower = item.source_rel.lower().replace("\\", "/")
    raw_suggestions: List[Tuple[str, str]] = []

    # Check for powershell profile or scripts
    if "profile.ps1" in source_lower or app_lower in ("pwsh", "powershell") or "powershell" in source_lower:
        base_ps = "~/Documents/PowerShell" if CURRENT_OS == OperatingSystem.WINDOWS else "~/.config/powershell"
        file_name = Path(item.source_rel).name
        raw_suggestions.append((f"{base_ps}/{file_name}", "PowerShell Default Directory"))
        raw_suggestions.append((f"{base_ps}/Microsoft.PowerShell_profile.ps1", "PowerShell Current User Profile"))
        raw_suggestions.append((f"{base_ps}/profile.ps1", "PowerShell Generic Profile"))
        if CURRENT_OS == OperatingSystem.WINDOWS:
            raw_suggestions.append(("~/.config/powershell/Microsoft.PowerShell_profile.ps1", "POSIX/Cross-Platform PowerShell"))
    elif "gitconfig" in source_lower or app_lower == "git":
        raw_suggestions.append(("~/.gitconfig", "User Home Git Config"))
        raw_suggestions.append(("~/.config/git/config", "XDG Standard Git Config"))
    elif "zshrc" in source_lower or app_lower == "zsh":
        raw_suggestions.append(("~/.zshrc", "User Home Zsh Config"))
        raw_suggestions.append(("~/.config/zsh/.zshrc", "XDG Zsh Config"))
    elif "tmux" in source_lower or app_lower == "tmux":
        raw_suggestions.append(("~/.tmux.conf", "User Home Tmux Config"))
        raw_suggestions.append(("~/.config/tmux/tmux.conf", "XDG Tmux Config"))
    elif app_lower in ("nvim", "neovim"):
        raw_suggestions.append(("~/.config/nvim", "XDG Neovim Config Directory"))
        raw_suggestions.append(("%LOCALAPPDATA%/nvim", "Windows Native Neovim Config"))
    elif app_lower == "wezterm":
        raw_suggestions.append(("~/.config/wezterm", "XDG WezTerm Directory"))
        raw_suggestions.append(("~/.wezterm.lua", "Home WezTerm Lua Config"))
    elif app_lower == "alacritty":
        raw_suggestions.append(("~/.config/alacritty", "XDG Alacritty Config"))
        raw_suggestions.append(("%APPDATA%/alacritty", "Windows Native Roaming Config"))
    else:
        # Check KNOWN_CONFIG_DIRS catalog
        if app_lower in KNOWN_CONFIG_DIRS:
            posix_path = KNOWN_CONFIG_DIRS[app_lower].get("posix")
            win_path = KNOWN_CONFIG_DIRS[app_lower].get("windows")
            if posix_path:
                raw_suggestions.append((posix_path, "Cross-Platform / POSIX Path"))
            if win_path and win_path != posix_path:
                raw_suggestions.append((win_path, "Windows Native Path"))

        if item.is_directory:
            raw_suggestions.append((f"~/.config/{item.app_name}", "XDG Config Directory"))
            if CURRENT_OS == OperatingSystem.WINDOWS:
                raw_suggestions.append((f"%APPDATA%/{item.app_name}", "Windows Roaming AppData"))
        else:
            raw_suggestions.append((f"~/{Path(item.source_rel).name}", "Home Directory"))
            raw_suggestions.append((f"~/.config/{item.app_name}/{Path(item.source_rel).name}", "XDG Config File"))

    # Include current destination if not already present
    paths = [p for p, _ in raw_suggestions]
    if item.dest_expr and item.dest_expr not in paths:
        raw_suggestions.insert(0, (item.dest_expr, "Current Target"))

    # Deduplicate while preserving order
    seen: set[str] = set()
    result: List[PathSuggestion] = []
    for p, d in raw_suggestions:
        if p not in seen:
            seen.add(p)
            result.append(PathSuggestion(p, d))

    return result[:5]


def get_visible_items(items: List[DiscoveredConfig]) -> List[DiscoveredConfig]:
    """Flatten visible items in hierarchy for backward compatibility with tests."""
    visible: List[DiscoveredConfig] = []
    for item in items:
        visible.append(item)
        if item.is_directory and item.is_expanded:
            visible.extend(get_visible_items(item.children))
    return visible


def set_expansion(item: DiscoveredConfig, expand: bool, max_depth: int = 2, current_depth: int = 1) -> None:
    """Expand or collapse a directory and its subdirectories up to max_depth."""
    if not item.is_directory:
        return
    item.is_expanded = expand
    if expand and current_depth < max_depth:
        for child in item.children:
            if child.is_directory and child.is_expandable:
                set_expansion(child, expand, max_depth=max_depth, current_depth=current_depth + 1)
    elif not expand:
        for child in item.children:
            if child.is_directory:
                set_expansion(child, False, max_depth=max_depth, current_depth=current_depth + 1)


def set_exclusion_recursive(item: DiscoveredConfig, is_excluded: bool) -> None:
    """Recursively set exclusion status on an item and all its children."""
    item.is_excluded = is_excluded
    for child in item.children:
        set_exclusion_recursive(child, is_excluded)


def get_all_leaf_items(item: DiscoveredConfig) -> List[DiscoveredConfig]:
    """Return all leaf items under a configuration tree."""
    leaves: List[DiscoveredConfig] = []
    if not item.is_directory or not item.children:
        leaves.append(item)
    else:
        for child in item.children:
            leaves.extend(get_all_leaf_items(child))
    return leaves


def is_package_customized(item: DiscoveredConfig) -> bool:
    """Check if an application package was customized granularly by the user."""
    if getattr(item, "force_pack", False):
        return False
    if not item.is_directory:
        return item.customized
    if item.customized or not item.link_as_dir:
        return True
    leaves = get_all_leaf_items(item)
    for c in leaves:
        if c.is_excluded or c.customized:
            return True
    return False


def mark_ancestors_unpacked(nav_stack: List[DiscoveredConfig], unexclude: bool = False) -> None:
    """Mark all ancestor directories in navigation stack as unpacked folder containers unless explicitly packed."""
    for ancestor in nav_stack:
        if not getattr(ancestor, "force_pack", False):
            ancestor.link_as_dir = False
        ancestor.customized = True
        if unexclude:
            ancestor.is_excluded = False


# ==============================================================================
# Scoped Navigation & Tree View Engine
# ==============================================================================

def get_scope_path_str(nav_stack: List[DiscoveredConfig]) -> str:
    """Return formatted location path string, e.g. '/' or '/pwsh/CurrentUserAllHosts/'."""
    if not nav_stack:
        return "/"
    return "/" + "/".join(item.app_name for item in nav_stack) + "/"


def collect_active_tree_items(
    node: DiscoveredConfig,
    active_list: List[DiscoveredConfig],
    excluded_list: List[DiscoveredConfig],
    is_root_call: bool = False,
) -> None:
    """Recursively collect active items in tree order and top-level excluded items."""
    if not is_root_call:
        if node.is_directory:
            if node.link_as_dir:
                # Packed directory: atomic link
                if node.is_excluded:
                    excluded_list.append(node)
                    return
                active_list.append(node)
            else:
                # Unpacked container: do not index directory itself, inspect its children
                pass
        else:
            # File item
            if node.is_excluded:
                excluded_list.append(node)
                return
            active_list.append(node)

    for child in node.children:
        collect_active_tree_items(child, active_list, excluded_list, is_root_call=False)


def format_tree_lines(
    node: DiscoveredConfig,
    active_indices: Dict[int, int],
    prefix: str = "",
    is_last: bool = True,
    is_top: bool = False,
) -> List[str]:
    """Format hierarchical tree branch lines with clean connectors and item badges."""
    lines: List[str] = []
    if not is_top:
        connector = "└── " if is_last else "├── "
        idx = active_indices.get(id(node), 0)

        if node.is_directory:
            if node.link_as_dir:
                idx_str = f"[{idx:>2}]"
                badge = c_cyan("[dir+]", bold=True)
                name_display = c_bold(node.app_name + "/")
                desc = c_dim(f"({node.child_count} files)")
                line = f"{prefix}{connector}{idx_str} {badge} {name_display} {desc}"
            else:
                name_display = c_bold(node.app_name + "/")
                desc = c_dim(f"({node.child_count} files)")
                line = f"{prefix}{connector}📁 {name_display} {desc}"
        else:
            idx_str = f"[{idx:>2}]"
            badge = c_magenta("[file]")
            name_display = node.app_name
            dest = f"{c_dim('->')} {node.dest_expr}"
            line = f"{prefix}{connector}{idx_str} {badge} {name_display} {dest}"
        lines.append(line)

    if node.is_directory and node.children:
        visible_children = []
        for c in node.children:
            if not c.is_excluded:
                visible_children.append(c)
            elif c.is_directory and not c.link_as_dir:
                if any(not leaf.is_excluded for leaf in get_all_leaf_items(c)):
                    visible_children.append(c)

        child_prefix = prefix if is_top else prefix + ("    " if is_last else "│   ")
        for i, child in enumerate(visible_children):
            child_is_last = (i == len(visible_children) - 1)
            lines.extend(format_tree_lines(child, active_indices, prefix=child_prefix, is_last=child_is_last, is_top=False))

    return lines


def format_excluded_table(excluded_items: List[DiscoveredConfig], start_idx: int, scope_path: str = "") -> str:
    """Format excluded items in a separate, dedicated table placed at the bottom."""
    if not excluded_items:
        return ""

    headers = ["#", "Type", "Excluded Item / Source", "Original Target Destination"]
    rows = []
    for i, item in enumerate(excluded_items):
        idx_num = start_idx + i
        type_badge = c_red("[dir ]") if item.is_directory else c_dim("[file]")
        dest_display = c_dim(item.dest_expr) if item.dest_expr else c_dim("(Excluded)")
        rows.append([
            f"[{idx_num:>2}]",
            type_badge,
            c_dim(item.source_rel),
            dest_display,
        ])

    table = format_table(headers, rows)
    scope_tag = f" in {scope_path}" if scope_path and scope_path != "/" else ""
    title = c_yellow(f"Excluded Items{scope_tag} (Will Not Be Linked in Template):", bold=True)
    hint = c_dim("  (Type number to re-include, e.g. '3', or 'include 3')")
    return f"\n{title}\n{table}\n{hint}\n"


def render_help_modal() -> str:
    """Render a comprehensive, cleanly categorized command reference modal."""
    content = [
        "",
        f"{c_bold('Navigation:')}",
        f"  {c_cyan('cd <#|name>')}       Navigate into directory package (aliases: 'ex', 'open')",
        f"  {c_cyan('cd ..')}             Return to parent directory (aliases: 'back', 'up')",
        f"  {c_cyan('cd /')}              Return to repository root (aliases: 'root', 'home')",
        "",
        f"{c_bold('Selection & Exclusions:')}",
        f"  {c_cyan('<#> ...')}           Toggle item(s) by index (e.g. '1', '1 3 5', 'toggle 1 3 5')",
        f"  {c_cyan('only <#> ...')}      Keep ONLY specified items active and exclude all others in scope",
        f"  {c_cyan('exclude <#> ...')}   Exclude item(s) from template (aliases: 'skip', 'exc')",
        f"  {c_cyan('include <#> ...')}   Re-include item(s) in template (alias: 'inc')",
        f"  {c_cyan('all / none')}        Include all or exclude all items in current folder scope",
        "",
        f"{c_bold('Packaging & Link Modes:')}",
        f"  {c_cyan('pack [#|name]')}     Link as single atomic directory root (aliases: 'dir', 'group')",
        f"  {c_cyan('unpack [#|name]')}   Unpack directory into individual files (aliases: 'files', 'split')",
        f"  {c_cyan('mode <#> [type]')}   Set link strategy: auto, symlink, junction, hardlink, copy",
        f"  {c_cyan('os <#> [target]')}   Set target OS scope: universal, windows, linux, macos, posix",
        "",
        f"{c_bold('Actions & Configuration:')}",
        f"  {c_cyan('edit <#> [dest]')}   Remap destination path (opens curated preset picker)",
        f"  {c_cyan(':  or  menu')}       Open interactive command palette popup",
        f"  {c_cyan('tree')}              Display clean hierarchy tree for directory or repository",
        f"  {c_cyan('add')}               Add custom relative source & destination mapping manually",
        f"  {c_cyan('list (ls)')}         Reprint current scoped template view",
        f"  {c_green('done (save)')}       Finalize, save template, and activate",
        f"  {c_red('quit (exit)')}        Cancel builder and exit without saving",
        "",
    ]
    return format_box("Fig Template Builder — Command Reference", content)


def render_scoped_view(
    root_items: List[DiscoveredConfig],
    nav_stack: List[DiscoveredConfig],
    is_system: bool = False,
    force_view: Optional[str] = None,
    status_msg: Optional[str] = None,
) -> Tuple[str, List[DiscoveredConfig]]:
    """Render the view for the current directory scope (takeover).
    At root (/), displays top-level application table.
    Inside a directory, displays a clean hierarchical tree view.
    Always includes a dedicated table at the bottom for excluded items.
    Returns (rendered_output, unified_item_lookup_list).
    """
    path_str = get_scope_path_str(nav_stack)
    scope_title = "SYSTEM CONFIGURATIONS" if is_system else f"Host: {CURRENT_OS.value.capitalize()}"
    banner = render_banner(
        f"Fig Template Builder — [{scope_title}]",
        subtitle=f"Location: {path_str}  (Type 'help' for commands, ':' for menu)",
    )

    active_items: List[DiscoveredConfig] = []
    excluded_items: List[DiscoveredConfig] = []
    output_lines: List[str] = [banner]

    if status_msg:
        output_lines.append(f"\n  {status_msg}")

    if not nav_stack:
        # AT ROOT (/)
        for it in root_items:
            if it.is_excluded:
                excluded_items.append(it)
            else:
                active_items.append(it)

        # Also find any excluded leaves in customized active packages so user sees everything excluded
        for it in active_items:
            if it.is_directory:
                for leaf in get_all_leaf_items(it):
                    if leaf.is_excluded and leaf not in excluded_items:
                        excluded_items.append(leaf)

        # Primary Table for Active Items at Root
        headers = ["#", "Type", "Package / Item", "Source in Repo", "Target Destination", "Mode", "Scope"]
        rows = []
        for idx, item in enumerate(active_items, 1):
            if item.is_directory:
                if getattr(item, "force_pack", False):
                    type_badge = c_cyan("[dir+]", bold=True)
                elif not item.link_as_dir:
                    type_badge = c_cyan("[files]")
                elif item.is_expandable:
                    type_badge = c_cyan("[dir+]", bold=True)
                else:
                    type_badge = c_blue("[dir] ")
            else:
                type_badge = c_magenta("[file]")

            app_name = c_bold(item.app_name)
            if item.is_directory:
                if getattr(item, "force_pack", False):
                    dest_display = f"{c_dim('->')} {item.dest_expr} {c_green('(packed package)')}"
                elif not item.link_as_dir:
                    active_count = len([l for l in get_all_leaf_items(item) if not l.is_excluded])
                    dest_display = f"{c_dim('->')} {c_yellow(f'(Unpacked: {active_count} active files, cd to configure)')}"
                elif is_package_customized(item):
                    dest_display = f"{c_dim('->')} {item.dest_expr} {c_yellow('(customized)')}"
                elif item.is_expandable:
                    dest_display = f"{c_dim('->')} {item.dest_expr} {c_dim(f'({item.child_count} files, cd to explore)')}"
                else:
                    dest_display = f"{c_dim('->')} {item.dest_expr}"
            else:
                dest_display = f"{c_dim('->')} {item.dest_expr}"

            mode_badge = _format_mode_badge(item.link_mode) if item.link_mode else c_dim("[auto]")
            if item.os_target:
                scope_badge = c_cyan(f"[{item.os_target}]")
            elif CURRENT_OS == OperatingSystem.WINDOWS and (
                "Documents/PowerShell" in item.dest_expr
                or "%APPDATA%" in item.dest_expr
                or "%LOCALAPPDATA%" in item.dest_expr
            ):
                scope_badge = c_yellow("[windows]")
            else:
                scope_badge = c_dim("Universal")

            rows.append([
                f"[{idx:>2}]",
                type_badge,
                app_name,
                item.source_rel,
                dest_display,
                mode_badge,
                scope_badge,
            ])

        table_output = format_table(headers, rows)
        output_lines.append(c_bold("Active / Included Packages & Files:"))
        output_lines.append(table_output)

    else:
        # INSIDE A SCOPED DIRECTORY
        current_dir = nav_stack[-1]
        collect_active_tree_items(current_dir, active_items, excluded_items, is_root_call=True)

        active_indices = {id(item): idx for idx, item in enumerate(active_items, 1)}

        parent_label = "/" if len(nav_stack) == 1 else nav_stack[-2].app_name + "/"
        if current_dir.link_as_dir or getattr(current_dir, "force_pack", False):
            mode_desc = f"{c_cyan('[Mode: Whole Directory Link -> ' + current_dir.dest_expr + ']')}"
            mode_hint = c_dim("   (Type 'unpack' to link individual files instead of directory)")
        else:
            mode_desc = f"{c_yellow('[Mode: Individual Files (Unpacked) | Directory itself will NOT be linked]')}"
            mode_hint = c_dim("   (Type 'pack' to link as a whole directory, 'only <#>' to keep specific files)")

        output_lines.append(f"📁 {c_bold(current_dir.app_name + '/')}  {mode_desc}")
        output_lines.append(f"{c_dim('   (Type cd .. or back to return to ' + parent_label + ')')}")
        output_lines.append(mode_hint)
        output_lines.append("")

        if active_items:
            output_lines.append(c_bold("Active Directory Tree:"))
            tree_lines = format_tree_lines(current_dir, active_indices, prefix="", is_last=True, is_top=True)
            output_lines.extend(tree_lines)
        else:
            output_lines.append(c_dim("  (All items in this directory are currently excluded)"))

    # Append segregated Excluded Items Table at the bottom
    item_lookup = active_items + excluded_items
    if excluded_items:
        excluded_table = format_excluded_table(excluded_items, start_idx=len(active_items) + 1, scope_path=path_str)
        output_lines.append(excluded_table)
    else:
        output_lines.append(c_dim("\n  (No excluded items in current scope. Type '<#>' or 'exclude <#>' to exclude an item)"))

    rule_w = min(110, max(40, get_terminal_width() - 2))
    legend = [
        "",
        c_dim("─" * rule_w),
        f" {c_bold('Commands:')}  "
        f"{c_cyan('<#>')} Toggle  ·  "
        f"{c_cyan('cd <#>')} Open  ·  "
        f"{c_cyan('edit <#>')} Remap  ·  "
        f"{c_cyan('mode <#>')} Mode  ·  "
        f"{c_cyan('pack/unpack')}  ·  "
        f"{c_cyan(':')} Menu  ·  "
        f"{c_cyan('?')} Help  ·  "
        f"{c_green('done')} Save  ·  "
        f"{c_red('quit')} Exit",
        c_dim("─" * rule_w),
    ]
    output_lines.extend(legend)

    return "\n".join(output_lines) + "\n", item_lookup


def render_full_repo_tree(root_items: List[DiscoveredConfig]) -> str:
    """Render a comprehensive hierarchical tree of the entire repository."""
    lines: List[str] = [c_bold("Full Repository Structure Tree:")]
    lines.append("/ (Repository Root)")
    for i, it in enumerate(root_items):
        is_last = (i == len(root_items) - 1)
        connector = "└── " if is_last else "├── "
        prefix = "    " if is_last else "│   "
        st = c_dim("[EXCLUDED] ") if it.is_excluded else ""
        if it.is_directory:
            lines.append(f"{connector}{st}{c_cyan(it.app_name + '/', bold=True)} {c_dim(f'-> {it.dest_expr} ({it.child_count} files)')}")
            if it.children and not it.is_excluded:
                # show 2-depth preview
                for j, ch in enumerate(it.children[:10]):
                    ch_last = (j == len(it.children[:10]) - 1 and len(it.children) <= 10)
                    ch_conn = "└── " if ch_last else "├── "
                    ch_st = c_dim("[EXCLUDED] ") if ch.is_excluded else ""
                    if ch.is_directory:
                        lines.append(f"{prefix}{ch_conn}{ch_st}{c_cyan(ch.app_name + '/')} {c_dim(f'({ch.child_count} files)')}")
                    else:
                        lines.append(f"{prefix}{ch_conn}{ch_st}{ch.app_name} {c_dim(f'-> {ch.dest_expr}')}")
                if len(it.children) > 10:
                    lines.append(f"{prefix}└── {c_dim(f'... and {len(it.children) - 10} more items (cd {it.app_name} to view)')}")
        else:
            lines.append(f"{connector}{st}{it.app_name} {c_dim(f'-> {it.dest_expr}')}")
    return "\n".join(lines)


def format_discovered_table(visible_items: List[DiscoveredConfig], is_system: bool = False) -> str:
    """Format discovered configs into a clean table (retained for backward compatibility)."""
    rendered, _ = render_scoped_view(visible_items, nav_stack=[], is_system=is_system)
    return rendered


