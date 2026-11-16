"""Fig Standalone Build, Packaging & Workstation Installation Script.

Performs a complete end-to-end release & installation lifecycle:
  1. Compiles the standalone executable using PyInstaller (packaging/fig.spec).
  2. Packages the release to releases/ following project conventions:
     - Directory: releases/fig-v<version>-<platform>-<arch>/
     - Standalone release installer: install.bat / install.sh
     - Distribution archive: releases/fig-v<version>-<platform>-<arch>.zip
     - Computes SHA256 and updates packaging/scoop/fig.json.
  3. Installs the compiled executable to $HOME/.local/bin (with PATH registration & verification).

Usage:
  python scripts/release/install.py              # Full build, package & install
  python scripts/release/install.py --skip-build  # Use existing dist/ binary
  python scripts/release/install.py --skip-package # Build & install without creating zip
"""

from __future__ import annotations

import os
import sys
import shutil
import zipfile
import hashlib
import platform
import argparse
import subprocess
from pathlib import Path

# Repository root
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from fig import __version__


def get_platform_tag() -> tuple[str, str]:
    """Returns (os_arch_tag, exe_name)."""
    system = platform.system().lower()
    machine = platform.machine().lower()

    if "arm" in machine or "aarch64" in machine:
        arch = "arm64"
    else:
        arch = "amd64"

    if system == "windows":
        return f"windows-{arch}", "fig.exe"
    elif system == "darwin":
        return f"darwin-{arch}", "fig"
    else:
        return f"linux-{arch}", "fig"


def sha256_file(path: Path) -> str:
    """Computes SHA256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def build_executable(verbose: bool = False) -> Path:
    """Runs PyInstaller on packaging/fig.spec and returns the path to the built binary."""
    spec_path = REPO_ROOT / "packaging" / "fig.spec"
    dist_dir = REPO_ROOT / "dist"
    build_dir = REPO_ROOT / "build"
    _, exe_name = get_platform_tag()
    output_exe = dist_dir / exe_name

    if not spec_path.is_file():
        raise FileNotFoundError(f"PyInstaller spec file not found at: {spec_path}")

    print(f"[*] Compiling standalone binary with PyInstaller...")
    print(f"    Spec:   {spec_path.relative_to(REPO_ROOT)}")
    print(f"    Output: {output_exe.relative_to(REPO_ROOT)}")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        str(spec_path),
        "--distpath", str(dist_dir),
        "--workpath", str(build_dir),
        "--noconfirm",
    ]

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            capture_output=not verbose,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"\n[ERROR] PyInstaller compilation failed (exit code {e.returncode}):", file=sys.stderr)
        if e.stderr:
            print(e.stderr, file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print("[ERROR] PyInstaller is not installed. Run: pip install pyinstaller", file=sys.stderr)
        sys.exit(1)

    if not output_exe.is_file():
        raise FileNotFoundError(f"Expected compiled binary at {output_exe}, but it was not created.")

    print(f"[OK] Successfully built {output_exe.name} ({output_exe.stat().st_size:,} bytes)")
    return output_exe


def cleanup_build_artifacts() -> None:
    """Removes transient PyInstaller build and dist directories from the repository root."""
    for folder_name in ("dist", "build", ".pyinstaller_dist", ".pyinstaller_build"):
        p = REPO_ROOT / folder_name
        if p.exists():
            try:
                shutil.rmtree(p, ignore_errors=True)
            except Exception:
                pass


def stage_and_package_release(built_exe: Path, create_zip: bool = False) -> tuple[Path, Optional[Path], str]:
    """Stages release directory and standalone installer. If create_zip=True, also builds .zip archive."""
    platform_tag, exe_name = get_platform_tag()
    version_tag = f"v{__version__}"
    pkg_name = f"fig-{version_tag}-{platform_tag}"

    releases_dir = REPO_ROOT / "releases"
    target_dir = releases_dir / pkg_name
    target_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n[*] Staging release folder in releases/{pkg_name}/...")

    # 1. Copy binary if not already at destination
    staged_exe = target_dir / exe_name
    if built_exe.resolve() != staged_exe.resolve():
        try:
            if staged_exe.is_file():
                staged_exe.unlink(missing_ok=True)
            shutil.copy2(built_exe, staged_exe)
        except (PermissionError, OSError):
            import time
            time.sleep(0.5)
            try:
                shutil.copy2(built_exe, staged_exe)
            except Exception as e:
                print(f"    [!] Warning: Could not overwrite {staged_exe.name} ({e})")
    print(f"    [+] Staged executable: {staged_exe.name}")

    # 2. Stage standalone install script
    if platform_tag.startswith("windows"):
        template_install = REPO_ROOT / "packaging" / "install.bat"
        staged_install = target_dir / "install.bat"
        if template_install.is_file():
            shutil.copy2(template_install, staged_install)
            print(f"    [+] Staged installer:  {staged_install.name}")
    else:
        template_install = REPO_ROOT / "packaging" / "install.sh"
        staged_install = target_dir / "install.sh"
        if template_install.is_file():
            shutil.copy2(template_install, staged_install)
            staged_install.chmod(0o755)
            print(f"    [+] Staged installer:  {staged_install.name}")

    exe_hash = sha256_file(staged_exe)
    print(f"    [SHA256] {exe_hash} ({staged_exe.name})")

    # 3. Optional zip distribution archive (skipped by default)
    zip_path: Optional[Path] = None
    zip_hash: str = ""
    if create_zip:
        zip_path = releases_dir / f"{pkg_name}.zip"
        print(f"[*] Generating release archive {zip_path.name}...")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(staged_exe, arcname=exe_name)
            if staged_install.is_file():
                zf.write(staged_install, arcname=staged_install.name)

        zip_hash = sha256_file(zip_path)
        print(f"    [OK] Archive created ({zip_path.stat().st_size:,} bytes)")
        print(f"    [SHA256] {zip_hash} ({zip_path.name})")

    # 4. Update Scoop manifest if on Windows
    scoop_manifest = REPO_ROOT / "packaging" / "scoop" / "fig.json"
    if scoop_manifest.is_file():
        try:
            import json
            data = json.loads(scoop_manifest.read_text(encoding="utf-8"))
            data["version"] = __version__
            if "architecture" in data and "64bit" in data["architecture"]:
                if zip_path:
                    data["architecture"]["64bit"]["url"] = (
                        f"https://github.com/yourusername/fig/releases/download/{version_tag}/{pkg_name}.zip"
                    )
                    data["architecture"]["64bit"]["hash"] = zip_hash
            scoop_manifest.write_text(json.dumps(data, indent=4) + "\n", encoding="utf-8")
            print(f"    [+] Updated Scoop manifest: {scoop_manifest.relative_to(REPO_ROOT)}")
        except Exception as e:
            print(f"    [!] Warning: Failed to update Scoop manifest: {e}", file=sys.stderr)

    return target_dir, zip_path, (zip_hash or exe_hash)


def install_to_local_bin(source_exe: Path) -> Path:
    """Installs the compiled binary to $HOME/.local/bin, registers PATH, and checks Scoop shims."""
    local_bin = Path.home() / ".local" / "bin"
    local_bin.mkdir(parents=True, exist_ok=True)
    target_exe = local_bin / source_exe.name

    print(f"\n[*] Installing {source_exe.name} to {local_bin}...")

    try:
        shutil.copy2(source_exe, target_exe)
        if not source_exe.name.endswith(".exe"):
            target_exe.chmod(0o755)
        print(f"    [OK] Copied binary to {target_exe}")
    except PermissionError:
        print(f"\n[ERROR] Permission denied writing to {target_exe}.", file=sys.stderr)
        print("Please ensure no running instances of fig are active and retry.", file=sys.stderr)
        sys.exit(1)

    # Windows PATH registration & Scoop shim sync
    if platform.system().lower() == "windows":
        _ensure_windows_path(local_bin)
        _sync_windows_scoop_shim(source_exe)
    else:
        _verify_posix_path(local_bin)

    return target_exe


def _ensure_windows_path(local_bin: Path) -> None:
    """Verifies that %USERPROFILE%\\.local\\bin is registered in the user's PATH environment."""
    try:
        bin_str = str(local_bin)
        ps_cmd = (
            f"$bin = '{bin_str}'; "
            f"$userPath = [Environment]::GetEnvironmentVariable('Path', 'User'); "
            f"if ($userPath -notlike ('*' + $bin + '*')) {{ "
            f"    $newPath = if ([string]::IsNullOrEmpty($userPath)) {{ $bin }} else {{ $userPath.TrimEnd(';') + ';' + $bin }}; "
            f"    [Environment]::SetEnvironmentVariable('Path', $newPath, 'User'); "
            f"    Write-Output 'ADDED'; "
            f"}} else {{ Write-Output 'EXISTS'; }}"
        )
        res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True)
        if "ADDED" in res.stdout:
            print(f"    [+] Added {local_bin} to user PATH environment variable.")
        else:
            print(f"    [OK] User PATH already contains {local_bin}.")
    except Exception as e:
        print(f"    [!] Warning: Could not verify user PATH: {e}", file=sys.stderr)


def _sync_windows_scoop_shim(source_exe: Path) -> None:
    """If a Scoop shim exists at ~/scoop/shims/fig.exe, updates it to prevent shadowing."""
    scoop_shim = Path.home() / "scoop" / "shims" / "fig.exe"
    if scoop_shim.is_file():
        try:
            shutil.copy2(source_exe, scoop_shim)
            print(f"    [+] Synced copy to Scoop shim at {scoop_shim} (preventing PATH collision).")
        except Exception:
            pass


def _verify_posix_path(local_bin: Path) -> None:
    """Verifies ~/.local/bin is present in PATH on POSIX systems."""
    path_env = os.environ.get("PATH", "")
    if str(local_bin) not in path_env.split(":"):
        print(f"    [!] Notice: {local_bin} is not in your current PATH.")
        print(f"        Add this to your ~/.bashrc or ~/.zshrc:")
        print(f"        export PATH=\"{local_bin}:$PATH\"")
    else:
        print(f"    [OK] {local_bin} is in your PATH.")


def verify_installation(installed_exe: Path) -> None:
    """Runs fig --version using the newly installed binary to confirm functionality."""
    print(f"\n[*] Verifying installed binary ({installed_exe})...")
    try:
        res = subprocess.run([str(installed_exe), "--version"], capture_output=True, text=True, timeout=5)
        out = (res.stdout or res.stderr).strip()
        print(f"    [OK] Verified output: {out}")
    except Exception as e:
        print(f"    [!] Warning: Verification command failed: {e}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fig Standalone Build, Release Packaging & Workstation Installation Utility"
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Skip PyInstaller compilation and use existing staged release binary",
    )
    parser.add_argument(
        "--skip-package",
        action="store_true",
        help="Skip staging releases/ directory",
    )
    parser.add_argument(
        "--zip",
        action="store_true",
        help="Generate a compressed .zip distribution archive alongside the release folder (default: False)",
    )
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="Only build and stage to releases/, do not install to $HOME/.local/bin",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show detailed PyInstaller build output",
    )

    args = parser.parse_args()

    print("=" * 80)
    print(f" Fig Standalone Installer & Release Manager (v{__version__})")
    print("=" * 80)

    # 1. Build Executable
    platform_tag, exe_name = get_platform_tag()
    version_tag = f"v{__version__}"
    pkg_name = f"fig-{version_tag}-{platform_tag}"
    staged_candidate = REPO_ROOT / "releases" / pkg_name / exe_name
    dist_candidate = REPO_ROOT / "dist" / exe_name

    if args.skip_build:
        if staged_candidate.is_file():
            built_exe = staged_candidate
            print(f"[*] Using existing staged binary at {staged_candidate.relative_to(REPO_ROOT)}")
        elif dist_candidate.is_file():
            built_exe = dist_candidate
            print(f"[*] Using existing binary at {dist_candidate.relative_to(REPO_ROOT)}")
        else:
            print(f"[ERROR] Binary not found at {staged_candidate} or {dist_candidate}. Run without --skip-build to compile.", file=sys.stderr)
            sys.exit(1)
    else:
        built_exe = build_executable(verbose=args.verbose)

    # 2. Package to releases/
    if not args.skip_package:
        stage_and_package_release(built_exe, create_zip=args.zip)

    # 3. Install to $HOME/.local/bin
    if not args.skip_install:
        installed_exe = install_to_local_bin(built_exe)
        verify_installation(installed_exe)

    # 4. Automatically cleanup transient build artifacts (dist/, build/)
    cleanup_build_artifacts()
    print("    [+] Cleaned up transient build directories (dist/, build/).")

    print("\n" + "=" * 80)
    print(" [SUCCESS] Fig installation & release packaging complete!")
    print("=" * 80)
    print(" You can now run 'fig' from any terminal session:")
    print("   fig --version")
    print("   fig build")
    print("   fig")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
