"""Template Engine for Fig.
Parses, validates, auto-generates, and resolves mapping templates (fig.toml)
with full OS-specific path declarations and platform awareness.
"""

from __future__ import annotations

import os
import sys
import fnmatch
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Union

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore

from fig.core.platform import (
    CURRENT_OS,
    OperatingSystem,
    matches_current_os,
    resolve_native_path,
)
from fig.builtins.catalog import (
    PRESET_CATALOG,
    get_platform_catalog,
    resolve_preset_mappings,
)


TEMPLATE_CANDIDATE_NAMES = [
    "fig.toml",
    ".fig.toml",
    "fig.template.toml",
    ".fig.template.toml",
]


class Template:
    def __init__(
        self,
        name: str = "default",
        version: str = "1.0.0",
        description: str = "Fig dotfile template",
        link_mode: str = "auto",
        backup_on_collision: bool = True,
        ignore_patterns: Optional[List[str]] = None,
        mappings: Optional[Dict[str, Union[str, Dict[str, str]]]] = None,
        presets: Optional[List[str]] = None,
        os_mappings: Optional[Dict[str, Dict[str, str]]] = None,
        os_presets: Optional[Dict[str, List[str]]] = None,
        source_file: Optional[Path] = None,
    ):
        self.name = name
        self.version = version
        self.description = description
        self.link_mode = link_mode
        self.backup_on_collision = backup_on_collision
        self.ignore_patterns = ignore_patterns or [".git", ".gitignore", "README.md", "fig.toml", ".fig.toml"]
        self.mappings = mappings or {}
        self.presets = presets or []
        self.os_mappings = os_mappings or {}  # e.g. {"windows": {...}, "linux": {...}}
        self.os_presets = os_presets or {}    # e.g. {"windows": [...], "linux": [...]}
        self.source_file = source_file

    @classmethod
    def load(cls, path: Path) -> Template:
        """Load template from a TOML file with OS-specific support."""
        with open(path, "rb") as f:
            data = tomllib.load(f)

        meta = data.get("meta", {})
        settings = data.get("settings", {})
        presets = data.get("presets", {}).get("include", [])
        raw_mappings = data.get("mappings", {})

        os_mappings: Dict[str, Dict[str, str]] = {}
        os_presets: Dict[str, List[str]] = {}

        # 1. Look for [os.<name>.mappings] and [os.<name>.presets]
        os_blocks = data.get("os", {})
        for os_key, os_data in os_blocks.items():
            if isinstance(os_data, dict):
                if "mappings" in os_data and isinstance(os_data["mappings"], dict):
                    os_mappings[os_key.lower()] = os_data["mappings"]
                elif "include" in os_data:
                    # e.g. os.windows.include = ["powershell"]
                    os_presets[os_key.lower()] = os_data["include"]
                else:
                    # Direct key-value mappings inside [os.<name>]
                    direct_mappings = {k: v for k, v in os_data.items() if isinstance(v, str)}
                    if direct_mappings:
                        os_mappings[os_key.lower()] = direct_mappings
                
                if "presets" in os_data and isinstance(os_data["presets"], dict):
                    os_presets[os_key.lower()] = os_data["presets"].get("include", [])

        # 2. Extract any inline OS mappings declared inside [mappings]
        universal_mappings: Dict[str, Union[str, Dict[str, str]]] = {}
        for src_key, target_val in raw_mappings.items():
            if isinstance(target_val, dict):
                # e.g. "wezterm.lua" = { windows = "...", linux = "..." }
                for os_k, dest in target_val.items():
                    os_mappings.setdefault(os_k.lower(), {})[src_key] = dest
            else:
                universal_mappings[src_key] = target_val

        return cls(
            name=meta.get("name", path.stem),
            version=meta.get("version", "1.0.0"),
            description=meta.get("description", ""),
            link_mode=settings.get("link_mode", "auto"),
            backup_on_collision=settings.get("backup_on_collision", True),
            ignore_patterns=settings.get("ignore", [".git", ".gitignore", "README.md", "fig.toml"]),
            mappings=universal_mappings,
            presets=presets,
            os_mappings=os_mappings,
            os_presets=os_presets,
            source_file=path.resolve(),
        )

    def save(self, path: Path) -> None:
        """Serialize and save this template to TOML file."""
        lines = [
            "# Fig Configuration Template",
            "[meta]",
            f'name = "{self.name}"',
            f'version = "{self.version}"',
            f'description = "{self.description}"',
            "",
            "[settings]",
            f'link_mode = "{self.link_mode}"',
            f'backup_on_collision = {"true" if self.backup_on_collision else "false"}',
        ]

        quoted_ignores = [f'"{p}"' for p in self.ignore_patterns]
        lines.append(f"ignore = [{', '.join(quoted_ignores)}]")
        lines.append("")

        if self.presets:
            lines.append("[presets]")
            quoted_presets = [f'"{p}"' for p in self.presets]
            lines.append(f"include = [{', '.join(quoted_presets)}]")
            lines.append("")

        if self.mappings:
            lines.append("[mappings]")
            for src, dest in self.mappings.items():
                if isinstance(dest, str):
                    clean_dest = dest.replace("\\", "/")
                    lines.append(f'"{src}" = "{clean_dest}"')
            lines.append("")

        # Save OS-specific sections
        for os_name, os_map in sorted(self.os_mappings.items()):
            if os_map:
                lines.append(f"[os.{os_name}.mappings]")
                for src, dest in sorted(os_map.items()):
                    clean_dest = str(dest).replace("\\", "/")
                    lines.append(f'"{src}" = "{clean_dest}"')
                lines.append("")

        for os_name, presets in sorted(self.os_presets.items()):
            if presets:
                lines.append(f"[os.{os_name}.presets]")
                quoted = [f'"{p}"' for p in presets]
                lines.append(f"include = [{', '.join(quoted)}]")
                lines.append("")

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
        self.source_file = path.resolve()

    def is_ignored(self, rel_path: str) -> bool:
        """Check if relative path matches any ignore patterns."""
        norm_path = rel_path.replace("\\", "/")
        for pattern in self.ignore_patterns:
            if fnmatch.fnmatch(norm_path, pattern) or fnmatch.fnmatch(Path(norm_path).name, pattern):
                return True
        return False

    def resolve_plan(
        self,
        repo_root: Path,
        target_os: Optional[OperatingSystem] = None,
    ) -> List[Tuple[Path, Path]]:
        """Compute the complete list of (source_path, destination_path) pairs for current OS.
        Prioritizes OS-specific mappings and presets over universal defaults.
        """
        active_os = target_os or CURRENT_OS
        repo_root = repo_root.resolve()
        resolved: Dict[str, Tuple[Path, Path]] = {}

        # 1. Combine universal presets with presets targeting the active OS
        active_presets = list(self.presets)
        for os_key, presets_list in self.os_presets.items():
            if matches_current_os(os_key, target_os=active_os):
                for p in presets_list:
                    if p not in active_presets:
                        active_presets.append(p)

        preset_map = resolve_preset_mappings(active_presets, os_type=active_os)
        for cand_src, target_expr in preset_map.items():
            src_path = repo_root / cand_src
            if src_path.exists() and not self.is_ignored(cand_src):
                dest_path = resolve_native_path(target_expr)
                resolved[str(dest_path.resolve())] = (src_path, dest_path)

        # 2. Universal mappings
        for rel_src, target_val in self.mappings.items():
            if self.is_ignored(rel_src):
                continue
            if isinstance(target_val, str):
                src_path = repo_root / rel_src
                dest_path = resolve_native_path(target_val)
                resolved[str(dest_path.resolve())] = (src_path, dest_path)

        # 3. OS-specific mappings for active OS (takes precedence)
        for os_key, os_map in self.os_mappings.items():
            if matches_current_os(os_key, target_os=active_os):
                for rel_src, target_expr in os_map.items():
                    if self.is_ignored(rel_src):
                        continue
                    src_path = repo_root / rel_src
                    dest_path = resolve_native_path(target_expr)
                    # If this destination was mapped, or if src was mapped differently, update
                    resolved[str(dest_path.resolve())] = (src_path, dest_path)

        return list(resolved.values())


def discover_template(search_dir: Path) -> Optional[Path]:
    """Look for a template file in search_dir."""
    for name in TEMPLATE_CANDIDATE_NAMES:
        candidate = search_dir / name
        if candidate.is_file():
            return candidate.resolve()
    return None


def generate_default_template(repo_root: Path) -> Template:
    """Inspect repo_root for dotfiles and generate an OS-aware Template."""
    repo_root = repo_root.resolve()
    catalog = get_platform_catalog(CURRENT_OS)
    detected_mappings: Dict[str, str] = {}
    activated_presets: List[str] = []

    for preset_name, candidates in catalog.items():
        found = False
        for rel_src, dest in candidates.items():
            p = repo_root / rel_src
            if p.exists():
                detected_mappings[rel_src] = dest
                found = True
        if found:
            activated_presets.append(preset_name)

    return Template(
        name=repo_root.name or "my-dotfiles",
        description="Auto-generated by Fig",
        link_mode="auto",
        backup_on_collision=True,
        mappings=detected_mappings,
        presets=activated_presets,
    )
