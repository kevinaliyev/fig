"""Template Viewer and Visual Editor Module for Fig.
Provides colorized inspection of active or catalog templates (including system sections)
and launches visual editors ($VISUAL, $EDITOR, nvim, vim, notepad) to edit them in place.
"""

from __future__ import annotations

import os
import sys
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, Union

from fig.config.state import FigState
from fig.config.platform import CURRENT_OS, matches_current_os, get_preferred_editor
from fig.config.template import Template
from fig.ui.ansi import (
    render_banner,
    render_warning_banner,
    format_table,
    badge_ok,
    c_bold,
    c_dim,
    c_cyan,
    c_green,
    c_yellow,
    c_red,
    c_magenta,
    c_blue,
)


def resolve_template_target(state: FigState, name_or_path: Optional[str] = None) -> Optional[Path]:
    """Resolve a template name, profile name, or explicit file path to a valid Path."""
    if name_or_path:
        cand = Path(name_or_path)
        if cand.is_file():
            return cand.resolve()
        
        prof = state.profiles_dir / f"{name_or_path}.toml"
        if prof.is_file():
            return prof.resolve()
        
        prof_raw = state.profiles_dir / name_or_path
        if prof_raw.is_file():
            return prof_raw.resolve()
        
        return None

    active = state.get_active_template_path()
    if active and active.exists():
        return active
    if state.active_template_link.exists():
        return state.active_template_link.resolve()
    return None


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


def _format_mappings_table(mappings_dict: Dict[str, Any], default_mode: str, indent: str = "  ") -> List[str]:
    """Format dictionary of mappings into a neat table with per-link mode badges."""
    headers = ["Source in Repo", "Target Destination", "Link Mode"]
    rows = []
    for src, val in sorted(mappings_dict.items()):
        if isinstance(val, dict):
            dest = str(val.get("target") or val.get("dest") or val.get("path") or "")
            mode = str(val.get("mode") or default_mode)
        else:
            dest = str(val)
            mode = default_mode

        rows.append([
            c_bold(src),
            f"{c_dim('->')} {dest}",
            _format_mode_badge(mode),
        ])

    table_lines = format_table(headers, rows).splitlines()
    return [f"{indent}{line}" for line in table_lines]


def format_template_view(tpl: Template, path: Path) -> str:
    """Produce a clean, colorized, human-readable representation of a template."""
    banner = render_banner(
        f"Fig Template: {tpl.name} (v{tpl.version})",
        subtitle=f"Host OS: {CURRENT_OS.value.capitalize()} (Detected)  |  Source: {path}",
        width=85,
    )

    lines = [banner]

    if tpl.description:
        lines.append(f"{c_dim('Description:')} {tpl.description}\n")

    # Settings Section
    lines.append(c_bold("Global Settings:"))
    lines.append(f"  Default Link Mode:    {_format_mode_badge(tpl.link_mode)}")
    backup_st = c_green("Enabled") if tpl.backup_on_collision else c_yellow("Disabled")
    lines.append(f"  Backup on Collision:  {backup_st}")
    if tpl.ignore_patterns:
        lines.append(f"  Ignored Patterns ({len(tpl.ignore_patterns)}):  {c_dim(', '.join(tpl.ignore_patterns))}")
    lines.append("")

    # Presets reference (if defined)
    if tpl.presets:
        lines.append(c_bold("Preset References:"))
        lines.append(f"  {c_dim(', '.join(tpl.presets))}")
        lines.append("")

    # Separate active vs inactive OS mappings
    active_os_maps = {k: v for k, v in tpl.os_mappings.items() if matches_current_os(k)}
    inactive_os_maps = {k: v for k, v in tpl.os_mappings.items() if not matches_current_os(k)}

    # 1. Active User Mappings Section (Always rendered first, above all inactive mappings)
    has_active_user = bool(tpl.mappings or active_os_maps)
    if has_active_user or inactive_os_maps:
        lines.append(c_bold(f"Active Mappings on this Host ({CURRENT_OS.value.capitalize()}):"))
        if not has_active_user:
            lines.append(c_dim(f"  (No active mappings defined for {CURRENT_OS.value.capitalize()})\n"))
        else:
            if tpl.mappings:
                header = f"  [universal] {badge_ok(f'ACTIVE ON THIS HOST ({CURRENT_OS.value.capitalize()})')} {c_dim('(Universal / All Platforms)')}"
                lines.append(c_bold(header))
                lines.extend(_format_mappings_table(tpl.mappings, tpl.link_mode, indent="    "))
                lines.append("")

            for os_name, mapping_dict in sorted(active_os_maps.items()):
                header = f"  [{os_name}] {badge_ok(f'ACTIVE ON THIS HOST ({CURRENT_OS.value.capitalize()})')}"
                lines.append(c_bold(header))
                lines.extend(_format_mappings_table(mapping_dict, tpl.link_mode, indent="    "))
                lines.append("")

    # 2. Inactive Platform Mappings Section (Placed strictly below active mappings)
    if inactive_os_maps:
        lines.append(c_bold(f"Inactive Platform Mappings (Cross-platform specifications for other OSes):"))
        for os_name, mapping_dict in sorted(inactive_os_maps.items()):
            header = f"  [{os_name}] {c_dim(f'[INACTIVE ON THIS HOST ({CURRENT_OS.value.capitalize()})]')}"
            lines.append(header)
            for src, val in sorted(mapping_dict.items()):
                if isinstance(val, dict):
                    d = val.get("target") or val.get("dest") or ""
                    m = val.get("mode") or tpl.link_mode
                else:
                    d = str(val)
                    m = tpl.link_mode
                lines.append(c_dim(f"    {src:<24} -> {d} [{m}]"))
            lines.append("")

    # System configuration sections
    if tpl.system_mappings or tpl.os_system_mappings:
        lines.append(render_warning_banner("SYSTEM CONFIGURATIONS (Requires -system flag to deploy)"))
        active_sys_maps = {k: v for k, v in tpl.os_system_mappings.items() if matches_current_os(k)}
        inactive_sys_maps = {k: v for k, v in tpl.os_system_mappings.items() if not matches_current_os(k)}

        if tpl.system_mappings or active_sys_maps:
            lines.append(c_bold(f"  Active System Mappings on this Host ({CURRENT_OS.value.capitalize()}):"))
            if tpl.system_mappings:
                header = f"    [universal System] {badge_ok(f'ACTIVE ON THIS HOST ({CURRENT_OS.value.capitalize()})')} {c_dim('(Universal / All Platforms)')}"
                lines.append(c_bold(header))
                lines.extend(_format_mappings_table(tpl.system_mappings, tpl.link_mode, indent="      "))
                lines.append("")
            for os_name, sys_maps in sorted(active_sys_maps.items()):
                header = f"    [{os_name} System] {badge_ok(f'ACTIVE ON THIS HOST ({CURRENT_OS.value.capitalize()})')}"
                lines.append(c_bold(header))
                lines.extend(_format_mappings_table(sys_maps, tpl.link_mode, indent="      "))
                lines.append("")

        if inactive_sys_maps:
            lines.append(c_bold("  Inactive Platform System Mappings (Cross-platform specifications for other OSes):"))
            for os_name, sys_maps in sorted(inactive_sys_maps.items()):
                header = f"    [{os_name} System] {c_dim(f'[INACTIVE ON THIS HOST ({CURRENT_OS.value.capitalize()})]')}"
                lines.append(header)
                for src, val in sorted(sys_maps.items()):
                    d = val.get("target") if isinstance(val, dict) else str(val)
                    m = val.get("mode") or tpl.link_mode if isinstance(val, dict) else tpl.link_mode
                    lines.append(c_dim(f"      {src:<24} -> {d} [{m}]"))
                lines.append("")

    lines.append("=" * 85)
    return "\n".join(lines)


def view_template(state: FigState, name_or_path: Optional[str] = None) -> int:
    """Display a formatted inspection view of active or specified template."""
    target_path = resolve_template_target(state, name_or_path)
    if not target_path or not target_path.exists():
        print("No template found to view. Run 'fig build' or 'fig bootstrap' first.", file=sys.stderr)
        return 1

    try:
        tpl = Template.load(target_path)
        print(format_template_view(tpl, target_path))
        return 0
    except Exception as e:
        print(f"Error loading template: {e}", file=sys.stderr)
        return 1


def edit_template(
    state: FigState,
    name_or_path: Optional[str] = None,
    editor: Optional[str] = None,
) -> int:
    """Launch preferred visual editor on the template file."""
    target_path = resolve_template_target(state, name_or_path)
    if not target_path or not target_path.exists():
        print("No template found to edit. Run 'fig build' or 'fig bootstrap' first.", file=sys.stderr)
        return 1

    chosen_editor = editor or get_preferred_editor()
    print(f"Opening {target_path} with {chosen_editor}...")

    try:
        ret = subprocess.call([chosen_editor, str(target_path)])
        if ret != 0:
            print(f"Editor exited with return code {ret}")
        
        try:
            Template.load(target_path)
            print(f"Template syntax validated successfully: {target_path}")
        except Exception as parse_err:
            print(f"Warning: Syntax error detected in edited template:\n  {parse_err}", file=sys.stderr)

        return ret
    except Exception as e:
        print(f"Failed to open editor '{chosen_editor}': {e}", file=sys.stderr)
        return 1


def list_templates(state: FigState) -> int:
    """List active template and all templates in profiles directory."""
    state.ensure_directories()
    active_path = state.get_active_template_path()

    print("=" * 60)
    print(" Fig Templates & Profiles Catalog")
    print("=" * 60)

    if active_path and active_path.exists():
        print(f" Active Template: {active_path}")
    else:
        print(" Active Template: None (run 'fig bootstrap' or 'fig build')")

    profiles = list(state.profiles_dir.glob("*.toml"))
    if profiles:
        print(f"\n Saved Profiles in {state.profiles_dir}:")
        for p in sorted(profiles):
            is_active = (active_path and active_path.resolve() == p.resolve())
            tag = " [active]" if is_active else ""
            print(f"   - {p.stem}{tag} ({p})")
    else:
        print(f"\n No saved profiles in {state.profiles_dir}")

    print("=" * 60)
    return 0
