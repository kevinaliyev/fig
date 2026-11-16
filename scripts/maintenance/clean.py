"""Fig Cleanup & Maintenance CLI Tool.
Thin frontend delegating to fig.utils.cleanup.CleanupManager.
"""

from __future__ import annotations

import sys
import argparse
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from fig import __version__
from fig.utils.cleanup import CleanupManager


def main() -> None:
    parser = argparse.ArgumentParser(description="Fig Maintenance & Cleanup Tool")
    parser.add_argument("--releases", action="store_true", help="Prune obsolete version releases from releases/")
    parser.add_argument("--all", action="store_true", help="Full clean (builds, caches, clutter, and old releases)")
    parser.add_argument("-n", "--dry-run", action="store_true", help="Simulate without deleting files")
    args = parser.parse_args()

    mode_tag = "DRY-RUN (SIMULATION)" if args.dry_run else "EXECUTING"
    print(f"[*] Starting Fig repository cleanup [{mode_tag}]...")
    print(f"[*] Active Fig Version: v{__version__}\n")

    mgr = CleanupManager()
    clean_releases = args.releases or args.all
    res = mgr.clean_repo_artifacts(repo_root=REPO_ROOT, clean_releases=clean_releases, dry_run=args.dry_run)

    print("[1/4] Checking repository root clutter...")
    if res["clutter"]:
        for item in res["clutter"]:
            print(f"  [{'WOULD REMOVE' if args.dry_run else 'REMOVED'}] {item}")
    else:
        print("  [OK] Root directory is clean.")

    print("\n[2/4] Checking build artifacts (build/, dist/, egg-info)...")
    if res["build"]:
        for item in res["build"]:
            print(f"  [{'WOULD REMOVE' if args.dry_run else 'REMOVED'}] {item}")
    else:
        print("  [OK] No temporary build artifacts found.")

    print("\n[3/4] Checking Python bytecode caches (__pycache__, *.pyc)...")
    if res["caches"]:
        for item in res["caches"][:15]:
            print(f"  [{'WOULD REMOVE' if args.dry_run else 'REMOVED'}] {item}")
        if len(res["caches"]) > 15:
            print(f"  ... and {len(res['caches']) - 15} more cache items.")
    else:
        print("  [OK] Python caches clean.")

    if clean_releases:
        print(f"\n[4/4] Checking releases/ for obsolete versions (preserving v{__version__})...")
        if res["releases"]:
            for item in res["releases"]:
                print(f"  [{'WOULD REMOVE' if args.dry_run else 'REMOVED'}] {item}")
        else:
            print("  [OK] No obsolete releases found.")
    else:
        print(f"\n[4/4] Skipping releases cleanup (use --releases or --all to prune old releases).")

    total = sum(len(items) for items in res.values())
    action_word = "Would purge" if args.dry_run else "Purged"
    print(f"\n[DONE] {action_word} {total} item(s).")


if __name__ == "__main__":
    main()
