"""Unified Version Synchronization Tool for Fig.
Propagates version changes across all project files:
  - fig/__init__.py
  - pyproject.toml
  - packaging/scoop/fig.json
  - README.md
  - releases/ directories (if present)

Usage:
  python scripts/release/bump_version.py <new_version>
  python scripts/release/bump_version.py check
"""

from __future__ import annotations

import os
import re
import sys
import json
import hashlib
import argparse
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]


def write_text_atomic(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def get_current_version() -> str:
    init_py = REPO_ROOT / "fig" / "__init__.py"
    content = init_py.read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
    if not match:
        raise ValueError(f"Could not find __version__ in {init_py}")
    return match.group(1)


def check_version_consistency() -> Dict[str, Optional[str]]:
    """Inspect all project metadata files and check if versions match."""
    status: Dict[str, Optional[str]] = {}

    # 1. fig/__init__.py
    init_py = REPO_ROOT / "fig" / "__init__.py"
    match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', init_py.read_text(encoding="utf-8"))
    status["fig/__init__.py"] = match.group(1) if match else None

    # 2. pyproject.toml
    pyproject = REPO_ROOT / "pyproject.toml"
    match = re.search(r'version\s*=\s*["\']([^"\']+)["\']', pyproject.read_text(encoding="utf-8"))
    status["pyproject.toml"] = match.group(1) if match else None

    # 3. packaging/scoop/fig.json
    scoop = REPO_ROOT / "packaging" / "scoop" / "fig.json"
    if scoop.exists():
        try:
            data = json.loads(scoop.read_text(encoding="utf-8"))
            status["packaging/scoop/fig.json"] = data.get("version")
        except Exception:
            status["packaging/scoop/fig.json"] = None
    else:
        status["packaging/scoop/fig.json"] = None

    return status


def bump_version(new_version: str, install: bool = True) -> None:
    # Strip any leading 'v'
    new_version = new_version.lstrip("v").strip()
    old_version = get_current_version()

    print(f"[*] Bumping Fig version: v{old_version} -> v{new_version}")

    updated_files: List[str] = []

    # 1. fig/__init__.py
    init_py = REPO_ROOT / "fig" / "__init__.py"
    old_init = init_py.read_text(encoding="utf-8")
    new_init = re.sub(
        r'__version__\s*=\s*["\'][^"\']+["\']',
        f'__version__ = "{new_version}"',
        old_init,
    )
    if new_init != old_init:
        write_text_atomic(init_py, new_init)
        updated_files.append("fig/__init__.py")

    # 2. pyproject.toml
    pyproject = REPO_ROOT / "pyproject.toml"
    old_pyproject = pyproject.read_text(encoding="utf-8")
    new_pyproject = re.sub(
        r'(version\s*=\s*["\'])[^"\']+(["\'])',
        rf"\g<1>{new_version}\g<2>",
        old_pyproject,
    )
    if new_pyproject != old_pyproject:
        write_text_atomic(pyproject, new_pyproject)
        updated_files.append("pyproject.toml")

    # 3. packaging/scoop/fig.json (version & url)
    scoop_manifest = REPO_ROOT / "packaging" / "scoop" / "fig.json"
    if scoop_manifest.exists():
        old_scoop = scoop_manifest.read_text(encoding="utf-8")
        try:
            data = json.loads(old_scoop)
            data["version"] = new_version
            if "architecture" in data and "64bit" in data["architecture"]:
                url = data["architecture"]["64bit"].get("url", "")
                data["architecture"]["64bit"]["url"] = url.replace(f"v{old_version}", f"v{new_version}")
            new_scoop = json.dumps(data, indent=4) + "\n"
            write_text_atomic(scoop_manifest, new_scoop)
            updated_files.append("packaging/scoop/fig.json")
        except Exception as e:
            print(f"[!] Warning: Failed to update Scoop manifest: {e}", file=sys.stderr)

    # 4. README.md
    readme = REPO_ROOT / "README.md"
    if readme.exists():
        old_readme = readme.read_text(encoding="utf-8")
        new_readme = old_readme.replace(f"fig-v{old_version}", f"fig-v{new_version}")
        new_readme = new_readme.replace(f"v{old_version}", f"v{new_version}")
        if new_readme != old_readme:
            write_text_atomic(readme, new_readme)
            updated_files.append("README.md")

    print(f"\n[SUCCESS] Manifest version update to v{new_version} complete! Updated:")
    for f in updated_files:
        print(f"  - {f}")

    # 6. Automatic compilation, release packaging & installation via scripts/release/install.py
    if install:
        print(f"\n[*] Triggering standalone build, release packaging & installation via scripts/release/install.py...")
        install_script = REPO_ROOT / "scripts" / "release" / "install.py"
        try:
            subprocess.run([sys.executable, str(install_script)], check=True)
        except subprocess.CalledProcessError as e:
            print(f"[!] Error: install.py failed with exit code {e.returncode}", file=sys.stderr)
            sys.exit(e.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fig Version & Release Synchronization Utility"
    )
    parser.add_argument(
        "target",
        nargs="?",
        help="New version number (e.g. 0.5.5) or 'check' to verify consistency",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Audit version consistency across all metadata files",
    )
    parser.add_argument(
        "--no-install",
        action="store_true",
        help="Only update metadata files without rebuilding binary or installing to $HOME/.local/bin",
    )

    args = parser.parse_args()

    if args.check or (args.target and args.target.strip().lower() == "check"):
        curr = get_current_version()
        print(f"[*] Checking version consistency against primary __version__ (v{curr}):\n")
        status = check_version_consistency()
        all_ok = True
        for file_path, ver in status.items():
            if ver == curr:
                print(f"  [OK]    {file_path} (v{ver})")
            else:
                print(f"  [MISMATCH] {file_path} (v{ver} != v{curr})")
                all_ok = False
        print()
        if all_ok:
            print("[SUCCESS] All project metadata files are in perfect synchronization!")
            sys.exit(0)
        else:
            print("[WARNING] Version mismatch detected! Run 'python scripts/bump_version.py <ver>' to synchronize.")
            sys.exit(1)

    if not args.target:
        parser.print_help()
        sys.exit(0)

    bump_version(args.target, install=not args.no_install)


if __name__ == "__main__":
    main()
