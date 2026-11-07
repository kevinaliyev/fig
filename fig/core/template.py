"""Template Engine for Fig.
Parses, validates, auto-generates, and resolves mapping templates (fig.toml)
with support for user dotfiles, OS-specific path declarations, and explicitly
segregated system-level configuration specifications.
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
        system_mappings: Optional[Dict[str, str]] = None,
        os_system_mappings: Optional[Dict[str, Dict[str, str]]] = None,
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
        self.os_mappings = os_mappings or {}        # e.g. {"windows": {...}, "linux": {...}}
        self.os_presets = os_presets or {}          # e.g. {"windows": [...], "linux": [...]}
        self.system_mappings = system_mappings or {} # [system.mappings]
        self.os_system_mappings = os_system_mappings or {} # [os.windows.system.mappings]
        self.source_file = source_file

    @property
    def has_system_mappings(self) -> bool:
        """Return True if template contains any system-level configuration rules."""
        if self.system_mappings:
            return True
        for os_k, maps in self.os_system_mappings.items():
            if maps:
                return True
        return False

    @classmethod
    def load(cls, path: Path) -> Template:
        """Load template from a TOML file with OS-specific and system-level support."""
        with open(path, "rb") as f:
            data = tomllib.load(f)

        meta = data.get("meta", {})
        settings = data.get("settings", {})
        presets = data.get("presets", {}).get("include", [])
        raw_mappings = data.get("mappings", {})

        os_mappings: Dict[str, Dict[str, str]] = {}
        os_presets: Dict[str, List[str]] = {}
        os_system_mappings: Dict[str, Dict[str, str]] = {}

        # 1. Look for [os.<name>] sections
        os_blocks = data.get("os", {})
        for os_key, os_data in os_blocks.items():
            if isinstance(os_data, dict):
                # User mappings
                if "mappings" in os_data and isinstance(os_data["mappings"], dict):
                    os_mappings[os_key.lower()] = os_data["mappings"]
                elif "include" in os_data:
                    os_presets[os_key.lower()] = os_data["include"]
                else:
                    direct_mappings = {k: v for k, v in os_data.items() if isinstance(v, str)}
                    if direct_mappings:
                        os_mappings[os_key.lower()] = direct_mappings
                
                # Presets
                if "presets" in os_data and isinstance(os_data["presets"], dict):
                    os_presets[os_key.lower()] = os_data["presets"].get("include", [])

                # System mappings inside [os.<name>.system.mappings]
                if "system" in os_data and isinstance(os_data["system"], dict):
                    sys_block = os_data["system"]
                    if "mappings" in sys_block and isinstance(sys_block["mappings"], dict):
                        os_system_mappings[os_key.lower()] = sys_block["mappings"]
                    else:
                        os_system_mappings[os_key.lower()] = {k: v for k, v in sys_block.items() if isinstance(v, str)}

        # 2. Extract universal system mappings from [system.mappings] or [system]
        system_mappings: Dict[str, str] = {}
        raw_system = data.get("system", {})
        if isinstance(raw_system, dict):
            if "mappings" in raw_system and isinstance(raw_system["mappings"], dict):
                system_mappings = raw_system["mappings"]
            else:
                system_mappings = {k: v for k, v in raw_system.items() if isinstance(v, str)}

        # 3. Extract universal user mappings declared inside [mappings]
        universal_mappings: Dict[str, Union[str, Dict[str, str]]] = {}
        for src_key, target_val in raw_mappings.items():
            if isinstance(target_val, dict):
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
            system_mappings=system_mappings,
            os_system_mappings=os_system_mappings,
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

        # Universal user presets
        if self.presets:
            lines.append("[presets]")
            quoted_presets = [f'"{p}"' for p in self.presets]
            lines.append(f"include = [{', '.join(quoted_presets)}]")
            lines.append("")

        # Universal user mappings
        if self.mappings:
            lines.append("[mappings]")
            for src, dest in self.mappings.items():
                if isinstance(dest, str):
                    clean_dest = dest.replace("\\", "/")
                    lines.append(f'"{src}" = "{clean_dest}"')
            lines.append("")

        # OS-specific user mappings
        for os_name, os_map in sorted(self.os_mappings.items()):
            if os_map:
                lines.append(f"[os.{os_name}.mappings]")
                for src, dest in sorted(os_map.items()):
                    clean_dest = str(dest).replace("\\", "/")
                    lines.append(f'"{src}" = "{clean_dest}"')
                lines.append("")

        # OS-specific presets
        for os_name, presets in sorted(self.os_presets.items()):
            if presets:
                lines.append(f"[os.{os_name}.presets]")
                quoted = [f'"{p}"' for p in presets]
                lines.append(f"include = [{', '.join(quoted)}]")
                lines.append("")

        # Universal system mappings
        if self.system_mappings:
            lines.append("[system.mappings]")
            for src, dest in sorted(self.system_mappings.items()):
                clean_dest = str(dest).replace("\\", "/")
                lines.append(f'"{src}" = "{clean_dest}"')
            lines.append("")

        # OS-specific system mappings
        for os_name, sys_map in sorted(self.os_system_mappings.items()):
            if sys_map:
                lines.append(f"[os.{os_name}.system.mappings]")
                for src, dest in sorted(sys_map.items()):
                    clean_dest = str(dest).replace("\\", "/")
                    lines.append(f'"{src}" = "{clean_dest}"')
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
        is_system: bool = False,
    ) -> List[Tuple[Path, Path]]:
        """Compute the complete list of (source_path, destination_path) pairs for current OS.
        If is_system is False (default): returns ONLY user dotfiles. System mappings are strictly excluded.
        If is_system is True: returns ONLY system-level mappings. Explicit pathspecs are mandatory.
        """
        active_os = target_os or CURRENT_OS
        repo_root = repo_root.resolve()
        resolved: Dict[str, Tuple[Path, Path]] = {}

        if is_system:
            # SYSTEM CONFIGURATION MODE
            # 1. Universal system mappings
            for rel_src, target_expr in self.system_mappings.items():
                if not target_expr or not str(target_expr).strip():
                    raise ValueError(f"System mapping for '{rel_src}' is missing an explicit pathspec destination.")
                src_path = repo_root / rel_src
                dest_path = resolve_native_path(target_expr)
                resolved[str(dest_path.resolve())] = (src_path, dest_path)

            # 2. OS-specific system mappings (takes precedence)
            for os_key, os_sys_map in self.os_system_mappings.items():
                if matches_current_os(os_key, target_os=active_os):
                    for rel_src, target_expr in os_sys_map.items():
                        if not target_expr or not str(target_expr).strip():
                            raise ValueError(f"System mapping for '{rel_src}' ({os_key}) is missing an explicit pathspec destination.")
                        src_path = repo_root / rel_src
                        dest_path = resolve_native_path(target_expr)
                        resolved[str(dest_path.resolve())] = (src_path, dest_path)

            return list(resolved.values())

        # USER CONFIGURATION MODE
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

        # 2. Universal user mappings
        for rel_src, target_val in self.mappings.items():
            if self.is_ignored(rel_src):
                continue
            if isinstance(target_val, str):
                src_path = repo_root / rel_src
                dest_path = resolve_native_path(target_val)
                resolved[str(dest_path.resolve())] = (src_path, dest_path)

        # 3. OS-specific user mappings (takes precedence)
        for os_key, os_map in self.os_mappings.items():
            if matches_current_os(os_key, target_os=active_os):
                for rel_src, target_expr in os_map.items():
                    if self.is_ignored(rel_src):
                        continue
                    src_path = repo_root / rel_src
                    dest_path = resolve_native_path(target_expr)
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
