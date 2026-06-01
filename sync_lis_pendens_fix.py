#!/usr/bin/env python3
"""
Sync the lis-pendens classifier fix from the framework repo into all 7
county repos.

Copies ONLY the universal files — no county-specific config is touched.

Usage:
    python sync_lis_pendens_fix.py              # dry-run (default)
    python sync_lis_pendens_fix.py --apply      # actually copy files
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

FRAMEWORK_ROOT = Path(__file__).resolve().parent

COUNTY_REPOS_ROOT = Path.home() / "dev" / "Bot Development"

COUNTY_REPOS = [
    "albany-county-ny-intel",
    "baltimore-county-md-intel",
    "broward-county-fl-intel",
    "dallas-tx-intel",
    "davidson-county-tn-intel",
    "fulton-county-ga-intel",
    "washington-dc-intel",
]

# Universal files: identical across all counties.
# These are copied verbatim from the framework repo.
UNIVERSAL_FILES = [
    "scaffold/pipeline/state_profile.py",       # NEW — per-state profiles
    "scaffold/pipeline/review.py",               # address guard + lis pendens routing
    "scaffold/pipeline/classify.py",             # lis_pendens -> messy_title
    "scaffold/pipeline/scoring_seam.py",         # sentinel resolution + state threading
    "scaffold/pipeline/run_pipeline_staged.py",  # state param threading
    "scaffold/pipeline/build_leads.py",          # state param passthrough
    "scaffold/pipeline/normalize.py",            # CANONICAL loader (unchanged but sync)
    "scaffold/pipeline/contracts/scored_lead_record.schema.json",  # property_class in parcel_display
    "knowledge_base/domain/canonical_doc_types.json",  # LIS_PENDENS sentinel
]

# County-specific files: NOT synced. Listed for operator awareness.
COUNTY_SPECIFIC = [
    "config/counties/<county_id>.json",
    "scrapers/*",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync lis-pendens fix to county repos")
    parser.add_argument("--apply", action="store_true",
                        help="Actually copy files (default is dry-run)")
    args = parser.parse_args()

    print("=" * 70)
    print("LIS PENDENS CLASSIFIER FIX — SYNC SCRIPT")
    print("=" * 70)
    print()

    # --- Print file lists ---
    print("UNIVERSAL files (will be synced):")
    for f in UNIVERSAL_FILES:
        src = FRAMEWORK_ROOT / f
        tag = "OK" if src.exists() else "MISSING"
        print(f"  [{tag}]  {f}")
    print()
    print("COUNTY-SPECIFIC files (NOT synced):")
    for f in COUNTY_SPECIFIC:
        print(f"  [skip]  {f}")
    print()

    # --- Verify all source files exist ---
    missing_sources = [f for f in UNIVERSAL_FILES if not (FRAMEWORK_ROOT / f).exists()]
    if missing_sources:
        print("ERROR: Source files MISSING from framework repo:")
        for f in missing_sources:
            print(f"  MISSING  {FRAMEWORK_ROOT / f}")
        print("\nRefusing to proceed. Fix the framework repo first.")
        return 1

    # --- Verify all target repos exist ---
    missing_repos = [r for r in COUNTY_REPOS if not (COUNTY_REPOS_ROOT / r).is_dir()]
    if missing_repos:
        print("ERROR: County repos MISSING:")
        for r in missing_repos:
            print(f"  MISSING  {COUNTY_REPOS_ROOT / r}")
        print("\nRefusing to proceed.")
        return 1

    # --- Check for macOS " 2" duplicates ---
    dup_found = False
    for repo_name in COUNTY_REPOS:
        repo_root = COUNTY_REPOS_ROOT / repo_name
        for f in UNIVERSAL_FILES:
            stem = Path(f).stem
            suffix = Path(f).suffix
            parent = (repo_root / f).parent
            dup_name = f"{stem} 2{suffix}"
            dup_path = parent / dup_name
            if dup_path.exists():
                print(f"  WARNING: macOS duplicate found (will skip): {dup_path}")
                dup_found = True
    if dup_found:
        print()

    # --- Verify all target paths resolve (existing files or new) ---
    all_ok = True
    for repo_name in COUNTY_REPOS:
        repo_root = COUNTY_REPOS_ROOT / repo_name
        for f in UNIVERSAL_FILES:
            target = repo_root / f
            target_dir = target.parent
            if not target_dir.is_dir():
                print(f"  MISSING target dir: {target_dir}")
                all_ok = False

    if not all_ok:
        print("\nERROR: Some target directories are missing. Refusing to --apply.")
        return 1

    # --- Dry-run / apply ---
    if not args.apply:
        print("DRY RUN — per-repo changes that WOULD be applied:")
        print()

    for repo_name in COUNTY_REPOS:
        repo_root = COUNTY_REPOS_ROOT / repo_name
        print(f"--- {repo_name} ---")
        for f in UNIVERSAL_FILES:
            src = FRAMEWORK_ROOT / f
            dst = repo_root / f
            if dst.exists():
                # Check if content differs
                src_content = src.read_bytes()
                dst_content = dst.read_bytes()
                if src_content == dst_content:
                    tag = "identical"
                else:
                    tag = "WILL UPDATE" if not args.apply else "UPDATED"
                    if args.apply:
                        shutil.copy2(src, dst)
            else:
                tag = "WILL CREATE" if not args.apply else "CREATED"
                if args.apply:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
            print(f"  [{tag}]  {f}")
        print()

    if args.apply:
        print("SYNC COMPLETE. Review git diff in each repo before committing.")
    else:
        print("DRY RUN COMPLETE. Re-run with --apply to execute.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
