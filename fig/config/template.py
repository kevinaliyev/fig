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

from fig.config.platform import (
    CURRENT_OS,
    OperatingSystem,
    matches_current_os,
    resolve_native_path,
)
from fig.config.presets import (
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


class ResolvedLink(tuple):
    """Subclass of tuple (src, dest) that preserves 2-element tuple unpacking
    while carrying per-link attributes like .mode.
    """
    src: Path
    dest: Path
    mode: Optional[str]

    def __new__(cls, src: Path, dest: Path, mode: Optional[str] = None):
        inst = super().__new__(cls, (src, dest))
        inst.src = src
        inst.dest = dest
        inst.mode = mode
        return inst


class Template:
    def __init__(
        self,
        name: str = "default",
        version: str = "1.0.0",
        description: str = "Fig dotfile template",
        link_mode: str = "auto",
        backup_on_collision: bool = True,
        ignore_patterns: Optional[List[str]] = None,
        mappings: Optional[Dict[str, Union[str, Dict[str, Any]]]] = None,
        presets: Optional[List[str]] = None,
        os_mappings: Optional[Dict[str, Dict[str, Union[str, Dict[str, Any]]]]] = None,
        os_presets: Optional[Dict[str, List[str]]] = None,
        system_mappings: Optional[Dict[str, Union[str, Dict[str, Any]]]] = None,
        os_system_mappings: Optional[Dict[str, Dict[str, Union[str, Dict[str, Any]]]]] = None,
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

    @staticmethod
    def _extract_target_and_mode(target_val: Union[str, Dict[str, Any]]) -> Tuple[str, Optional[str]]:
        """Extract destination path expression and optional link mode from mapping value."""
        if isinstance(target_val, dict):
            dest = str(target_val.get("target") or target_val.get("dest") or target_val.get("path") or "")
            mode = target_val.get("mode")
            return dest, str(mode) if mode else None
        return str(target_val), None

    @staticmethod
    def _serialize_mapping_val(val: Union[str, Dict[str, Any]]) -> str:
        """Serialize a mapping value cleanly for TOML."""
        if isinstance(val, dict):
            target = str(val.get("target") or val.get("dest") or val.get("path") or "").replace("\\", "/")
            mode = val.get("mode")
            if mode:
                return f'{{ target = "{target}", mode = "{mode}" }}'
            return f'"{target}"'
        clean = str(val).replace("\\", "/")
        return f'"{clean}"'

    @classmethod
    def load(cls, path: Path) -> Template:
        """Load template from a TOML file with OS-specific and system-level support."""
        with open(path, "rb") as f:
            data = tomllib.load(f)

        meta = data.get("meta", {})
        settings = data.get("settings", {})
        presets = data.get("presets", {}).get("include", [])
        raw_mappings = data.get("mappings", {})

        os_mappings: Dict[str, Dict[str, Any]] = {}
        os_presets: Dict[str, List[str]] = {}
        os_system_mappings: Dict[str, Dict[str, Any]] = {}

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
                    direct_mappings = {k: v for k, v in os_data.items() if isinstance(v, (str, dict))}
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
                        os_system_mappings[os_key.lower()] = {k: v for k, v in sys_block.items() if isinstance(v, (str, dict))}

        # 2. Extract universal system mappings from [system.mappings] or [system]
        system_mappings: Dict[str, Any] = {}
        raw_system = data.get("system", {})
        if isinstance(raw_system, dict):
            if "mappings" in raw_system and isinstance(raw_system["mappings"], dict):
                system_mappings = raw_system["mappings"]
            else:
                system_mappings = {k: v for k, v in raw_system.items() if isinstance(v, (str, dict))}

        # 3. Extract universal user mappings declared inside [mappings]
        universal_mappings: Dict[str, Union[str, Dict[str, Any]]] = {}
        for src_key, target_val in raw_mappings.items():
            if isinstance(target_val, dict):
                # Check if it is an inline table specifying target & mode, OR an OS dict
                os_candidates = ("windows", "win", "win32", "linux", "macos", "darwin", "osx", "posix", "unix")
                is_os_dict = any(k.lower() in os_candidates for k in target_val.keys())
                if is_os_dict:
                    for os_k, dest in target_val.items():
                        os_mappings.setdefault(os_k.lower(), {})[src_key] = dest
                else:
                    universal_mappings[src_key] = target_val
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

        # Universal user presets (only if explicitly populated)
        if self.presets:
            lines.append("[presets]")
            quoted_presets = [f'"{p}"' for p in self.presets]
            lines.append(f"include = [{', '.join(quoted_presets)}]")
            lines.append("")

        # Universal user mappings
        if self.mappings:
            lines.append("[mappings]")
            for src, target_val in sorted(self.mappings.items()):
                val_str = self._serialize_mapping_val(target_val)
                lines.append(f'"{src}" = {val_str}')
            lines.append("")

        # OS-specific user mappings
        for os_name, os_map in sorted(self.os_mappings.items()):
            if os_map:
                lines.append(f"[os.{os_name}.mappings]")
                for src, target_val in sorted(os_map.items()):
                    val_str = self._serialize_mapping_val(target_val)
                    lines.append(f'"{src}" = {val_str}')
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
            for src, target_val in sorted(self.system_mappings.items()):
                val_str = self._serialize_mapping_val(target_val)
                lines.append(f'"{src}" = {val_str}')
            lines.append("")

        # OS-specific system mappings
        for os_name, sys_map in sorted(self.os_system_mappings.items()):
            if sys_map:
                lines.append(f"[os.{os_name}.system.mappings]")
                for src, target_val in sorted(sys_map.items()):
                    val_str = self._serialize_mapping_val(target_val)
                    lines.append(f'"{src}" = {val_str}')
                lines.append("")

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
        self.source_file = path.resolve()

    def is_ignored(self, rel_path: str) -> bool:
        """Check if relative path matches any ignore patterns."""
        norm_path = rel_path.replace("\\", "/").strip("/")
        for pattern in self.ignore_patterns:
            pat = pattern.replace("\\", "/").strip("/")
            if fnmatch.fnmatch(norm_path, pat):
                return True
            # Prefix directory match (e.g. ignoring 'tmux' ignores 'tmux/foo')
            if norm_path.startswith(f"{pat}/"):
                return True
            # Basename match only for filename patterns without directory separators (e.g. '*.log', '*.tmp')
            if "/" not in pat and ("*" in pat or "?" in pat):
                if fnmatch.fnmatch(Path(norm_path).name, pat):
                    return True
        return False

    def resolve_plan(
        self,
        repo_root: Path,
        target_os: Optional[OperatingSystem] = None,
        is_system: bool = False,
    ) -> List[ResolvedLink]:
        """Compute the complete list of ResolvedLink pairs for current OS.
        If is_system is False (default): returns ONLY user dotfiles. System mappings are strictly excluded.
        If is_system is True: returns ONLY system-level mappings. Explicit pathspecs are mandatory.
        """
        active_os = target_os or CURRENT_OS
        repo_root = repo_root.resolve()
        resolved: Dict[str, ResolvedLink] = {}

        if is_system:
            # SYSTEM CONFIGURATION MODE
            # 1. Universal system mappings
            for rel_src, target_val in self.system_mappings.items():
                target_expr, item_mode = self._extract_target_and_mode(target_val)
                if not target_expr or not str(target_expr).strip():
                    raise ValueError(f"System mapping for '{rel_src}' is missing an explicit pathspec destination.")
                src_path = repo_root / rel_src
                dest_path = resolve_native_path(target_expr)
                resolved[str(dest_path.resolve())] = ResolvedLink(src_path, dest_path, mode=item_mode)

            # 2. OS-specific system mappings (takes precedence)
            for os_key, os_sys_map in self.os_system_mappings.items():
                if matches_current_os(os_key, target_os=active_os):
                    for rel_src, target_val in os_sys_map.items():
                        target_expr, item_mode = self._extract_target_and_mode(target_val)
                        if not target_expr or not str(target_expr).strip():
                            raise ValueError(f"System mapping for '{rel_src}' ({os_key}) is missing an explicit pathspec destination.")
                        src_path = repo_root / rel_src
                        dest_path = resolve_native_path(target_expr)
                        resolved[str(dest_path.resolve())] = ResolvedLink(src_path, dest_path, mode=item_mode)

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
                resolved[str(dest_path.resolve())] = ResolvedLink(src_path, dest_path, mode=None)

        # 2. Universal user mappings (explicit mappings are always honored)
        for rel_src, target_val in self.mappings.items():
            src_path = repo_root / rel_src
            target_expr, item_mode = self._extract_target_and_mode(target_val)
            dest_path = resolve_native_path(target_expr)
            resolved[str(dest_path.resolve())] = ResolvedLink(src_path, dest_path, mode=item_mode)

        # 3. OS-specific user mappings (takes precedence over universal mappings)
        for os_key, os_map in self.os_mappings.items():
            if matches_current_os(os_key, target_os=active_os):
                for rel_src, target_val in os_map.items():
                    src_path = repo_root / rel_src
                    target_expr, item_mode = self._extract_target_and_mode(target_val)
                    dest_path = resolve_native_path(target_expr)
                    resolved[str(dest_path.resolve())] = ResolvedLink(src_path, dest_path, mode=item_mode)

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
