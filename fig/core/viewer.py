"""Template Viewer and Visual Editor Module for Fig.
Provides colorized inspection of active or catalog templates and launches
visual editors ($VISUAL, $EDITOR, nvim, vim, notepad) to edit them in place.
"""

from __future__ import annotations

import os
import sys
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore

from fig.core.config import FigState
from fig.core.platform import CURRENT_OS, get_preferred_editor
from fig.core.template import Template


def resolve_template_target(state: FigState, name_or_path: Optional[str] = None) -> Optional[Path]:
    """Resolve a template name, profile name, or explicit file path to a valid Path."""
    if name_or_path:
        cand = Path(name_or_path)
        if cand.is_file():
            return cand.resolve()
        
        # Check profiles directory
        prof = state.profiles_dir / f"{name_or_path}.toml"
        if prof.is_file():
            return prof.resolve()
        
        prof_raw = state.profiles_dir / name_or_path
        if prof_raw.is_file():
            return prof_raw.resolve()
        
        return None

    # Default to active template
    active = state.get_active_template_path()
    if active and active.exists():
        return active
    if state.active_template_link.exists():
        return state.active_template_link.resolve()
    return None


def format_template_view(tpl: Template, path: Path) -> str:
    """Produce a clean, human-readable representation of a template."""
    lines = [
        "=" * 70,
        f" Fig Template: {tpl.name} (v{tpl.version})",
        f" Location:     {path}",
        f" Current OS:   {CURRENT_OS.value.capitalize()}",
        "=" * 70,
    ]

    if tpl.description:
        lines.append(f"Description: {tpl.description}\n")

    lines.append("Settings:")
    lines.append(f"  Link Mode:            {tpl.link_mode}")
    lines.append(f"  Backup on Collision:  {tpl.backup_on_collision}")
    if tpl.ignore_patterns:
        lines.append(f"  Ignored Patterns:     {', '.join(tpl.ignore_patterns)}")
    lines.append("")

    if tpl.presets:
        lines.append(f"Universal Presets: {', '.join(tpl.presets)}")
        lines.append("")

    if tpl.mappings:
        lines.append("Universal Mappings:")
        for src, dest in sorted(tpl.mappings.items()):
            lines.append(f"  {src:<24} -> {dest}")
        lines.append("")

    if tpl.os_mappings:
        lines.append("Platform-Specific Mappings:")
        for os_name, mapping_dict in sorted(tpl.os_mappings.items()):
            active_marker = " [ACTIVE ON THIS HOST]" if os_name in (CURRENT_OS.value, "posix") else ""
            lines.append(f"  [{os_name}]{active_marker}")
            for src, dest in sorted(mapping_dict.items()):
                lines.append(f"    {src:<22} -> {dest}")
        lines.append("")

    if tpl.os_presets:
        lines.append("Platform-Specific Presets:")
        for os_name, presets_list in sorted(tpl.os_presets.items()):
            lines.append(f"  [{os_name}]: {', '.join(presets_list)}")
        lines.append("")

    lines.append("=" * 70)
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
        # Launch editor
        ret = subprocess.call([chosen_editor, str(target_path)])
        if ret != 0:
            print(f"Editor exited with return code {ret}")
        
        # Validate syntax after editing
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
