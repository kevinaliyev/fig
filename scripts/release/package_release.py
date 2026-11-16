"""Automated release packager for Fig.
Builds the standalone binary, stages it in releases/fig-v<version>-<os>-<arch>/,
creates the distribution .zip, and updates the Scoop manifest with the SHA256 hash.
"""

from __future__ import annotations

import os
import sys
import shutil
import hashlib
import zipfile
from pathlib import Path

# Repo root
REPO_ROOT = Path(__file__).resolve().parents[2]

# Read version
sys.path.insert(0, str(REPO_ROOT))
from fig import __version__


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def package() -> None:
    version = f"v{__version__}"
    arch = "windows-amd64" if sys.platform.startswith("win") else f"{sys.platform}-amd64"
    pkg_name = f"fig-{version}-{arch}"

    releases_dir = REPO_ROOT / "releases"
    target_dir = releases_dir / pkg_name
    target_dir.mkdir(parents=True, exist_ok=True)

    dist_exe = REPO_ROOT / "dist" / "fig.exe"
    spec_file = REPO_ROOT / "packaging" / "fig.spec"
    if not dist_exe.is_file():
        print(f"[ERROR] Could not find {dist_exe}. Build with: pyinstaller {spec_file.relative_to(REPO_ROOT)} --distpath dist --workpath build", file=sys.stderr)
        sys.exit(1)

    # 1. Copy binary
    dest_exe = target_dir / "fig.exe"
    shutil.copy2(dist_exe, dest_exe)
    print(f"[*] Staged executable: {dest_exe}")

    # 2. Stage install.bat
    template_install = REPO_ROOT / "packaging" / "install.bat"
    dest_install = target_dir / "install.bat"
    if template_install.is_file():
        shutil.copy2(template_install, dest_install)
        print(f"[*] Staged installer:  {dest_install}")

    # 3. Create zip archive
    zip_path = releases_dir / f"{pkg_name}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(dest_exe, arcname="fig.exe")
        if dest_install.is_file():
            zf.write(dest_install, arcname="install.bat")
    print(f"[*] Created archive:   {zip_path}")

    # 4. Compute hash and update scoop manifest
    zip_hash = sha256_file(zip_path)
    print(f"[*] SHA256 Checksum:  {zip_hash}")

    scoop_manifest = REPO_ROOT / "packaging" / "scoop" / "fig.json"
    if scoop_manifest.is_file():
        content = scoop_manifest.read_text(encoding="utf-8")
        import json
        data = json.loads(content)
        data["version"] = __version__
        if "architecture" in data and "64bit" in data["architecture"]:
            data["architecture"]["64bit"]["url"] = f"https://github.com/yourusername/fig/releases/download/{version}/{pkg_name}.zip"
            data["architecture"]["64bit"]["hash"] = zip_hash
        scoop_manifest.write_text(json.dumps(data, indent=4) + "\n", encoding="utf-8")
        print(f"[*] Updated Scoop:    {scoop_manifest}")

    print("\n[SUCCESS] Release packaging complete!")


if __name__ == "__main__":
    package()
