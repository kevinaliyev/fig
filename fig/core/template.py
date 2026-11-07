"""Template Engine for Fig.
Parses, validates, auto-generates, and resolves mapping templates (fig.toml).
"""

from __future__ import annotations

import os
import sys
import fnmatch
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore

from fig.builtins.catalog import PRESET_CATALOG, resolve_preset_mappings


TEMPLATE_CANDIDATE_NAMES = [
    "fig.toml",
    ".fig.toml",
    "fig.template.toml",
    ".fig.template.toml",
]


def expand_path_expr(expr: str) -> Path:
    """Expand environment variables ($HOME, %APPDATA%) and user home (~) in path."""
    expanded = os.path.expandvars(expr)
    expanded = os.path.expanduser(expanded)
    return Path(expanded)


class Template:
    def __init__(
        self,
        name: str = "default",
        version: str = "1.0.0",
        description: str = "Fig dotfile template",
        link_mode: str = "auto",
        backup_on_collision: bool = True,
        ignore_patterns: Optional[List[str]] = None,
        mappings: Optional[Dict[str, str]] = None,
        presets: Optional[List[str]] = None,
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
        self.source_file = source_file

    @classmethod
    def load(cls, path: Path) -> Template:
        """Load template from a TOML file."""
        with open(path, "rb") as f:
            data = tomllib.load(f)

        meta = data.get("meta", {})
        settings = data.get("settings", {})
        presets = data.get("presets", {}).get("include", [])
        mappings = data.get("mappings", {})

        return cls(
            name=meta.get("name", path.stem),
            version=meta.get("version", "1.0.0"),
            description=meta.get("description", ""),
            link_mode=settings.get("link_mode", "auto"),
            backup_on_collision=settings.get("backup_on_collision", True),
            ignore_patterns=settings.get("ignore", [".git", ".gitignore", "README.md", "fig.toml"]),
            mappings=mappings,
            presets=presets,
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

        # Ignore patterns
        quoted_ignores = [f'"{p}"' for p in self.ignore_patterns]
        lines.append(f"ignore = [{', '.join(quoted_ignores)}]")
        lines.append("")

        if self.presets:
            lines.append("[presets]")
            quoted_presets = [f'"{p}"' for p in self.presets]
            lines.append(f"include = [{', '.join(quoted_presets)}]")
            lines.append("")

        lines.append("[mappings]")
        for src, dest in self.mappings.items():
            clean_dest = str(dest).replace("\\", "/")
            lines.append(f'"{src}" = "{clean_dest}"')

        lines.append("")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines), encoding="utf-8")
        self.source_file = path.resolve()

    def is_ignored(self, rel_path: str) -> bool:
        """Check if relative path matches any ignore patterns."""
        norm_path = rel_path.replace("\\", "/")
        for pattern in self.ignore_patterns:
            if fnmatch.fnmatch(norm_path, pattern) or fnmatch.fnmatch(Path(norm_path).name, pattern):
                return True
        return False

    def resolve_plan(self, repo_root: Path) -> List[Tuple[Path, Path]]:
        """Compute the complete list of (source_path, destination_path) pairs.
        Combines explicit mappings and matching presets.
        """
        repo_root = repo_root.resolve()
        resolved: Dict[str, Tuple[Path, Path]] = {}

        # 1. Preset mappings (if matched in repo)
        preset_map = resolve_preset_mappings(self.presets)
        for cand_src, target_expr in preset_map.items():
            src_path = repo_root / cand_src
            if src_path.exists() and not self.is_ignored(cand_src):
                dest_path = expand_path_expr(target_expr)
                resolved[str(dest_path.resolve())] = (src_path, dest_path)

        # 2. Explicit mappings take highest precedence
        for rel_src, target_expr in self.mappings.items():
            if self.is_ignored(rel_src):
                continue
            src_path = repo_root / rel_src
            dest_path = expand_path_expr(target_expr)
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
    """Inspect repo_root for common dotfiles and generate a ready-to-use Template."""
    repo_root = repo_root.resolve()
    detected_mappings: Dict[str, str] = {}
    activated_presets: List[str] = []

    # Check each preset from catalog
    for preset_name, candidates in PRESET_CATALOG.items():
        found = False
        for rel_src, dest in candidates.items():
            p = repo_root / rel_src
            if p.exists():
                detected_mappings[rel_src] = dest
                found = True
        if found:
            activated_presets.append(preset_name)

    # If repo has other files not in presets (excluding git), map them to ~/<filename>
    for item in repo_root.iterdir():
        rel = item.name
        if rel in [".git", "fig.toml", ".fig.toml", "README.md", "LICENSE"]:
            continue
        if rel not in detected_mappings and not any(rel.startswith(k) for k in detected_mappings):
            detected_mappings[rel] = f"~/{rel}"

    return Template(
        name=repo_root.name or "auto-dotfiles",
        description="Auto-generated by Fig",
        link_mode="auto",
        backup_on_collision=True,
        mappings=detected_mappings,
        presets=activated_presets,
    )
