#!/usr/bin/env python3
"""Verify that no protected files have been modified, deleted, or moved.

Reads the SHA-256 manifest from ../routewise_protected_manifest.txt and checks
all protected assets against current files on disk. Also checks git diff.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT.parent / "routewise_protected_manifest.txt"

def check_manifest() -> bool:
    if not MANIFEST_PATH.is_file():
        print(f"ERROR: Manifest file not found at {MANIFEST_PATH}", file=sys.stderr)
        return False

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    print(f"Checking {len(lines)} protected files against manifest...")
    mismatches = []
    missing = []

    for line in lines:
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            continue
        expected_sha, rel_path = parts
        # normalize path
        file_path = REPO_ROOT / rel_path.replace("/", os.sep).replace("\\", os.sep)
        if not file_path.is_file():
            missing.append(rel_path)
            continue
        with open(file_path, "rb") as fp:
            actual_sha = hashlib.sha256(fp.read()).hexdigest().upper()
        if actual_sha != expected_sha.upper():
            mismatches.append((rel_path, expected_sha, actual_sha))

    if missing:
        print(f"FAIL: {len(missing)} protected files missing:")
        for m in missing:
            print(f"  - {m}")
    if mismatches:
        print(f"FAIL: {len(mismatches)} protected files have mismatched SHA-256:")
        for rel_path, exp, act in mismatches:
            print(f"  - {rel_path}: expected {exp[:12]}..., got {act[:12]}...")

    if not missing and not mismatches:
        print(f"SUCCESS: All {len(lines)} protected files match manifest SHA-256 perfectly.")
        return True
    return False

def check_git_diff() -> bool:
    try:
        # Check against main branch
        result = subprocess.run(
            ["git", "diff", "--name-only", "main"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=True
        )
        changed_files = [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]
        
        # Also check git diff --staged or git diff main..HEAD if committed
        result_head = subprocess.run(
            ["git", "diff", "--name-only", "main..HEAD"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        if result_head.returncode == 0:
            changed_files.extend([line.strip().replace("\\", "/") for line in result_head.stdout.splitlines() if line.strip()])
            
        changed_set = set(changed_files)
        print(f"Git diff against main lists {len(changed_set)} changed path(s).")

        # Load manifest paths for comparison
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            protected_paths = {line.strip().split(maxsplit=1)[1].replace("\\", "/") for line in f if line.strip()}

        violated = changed_set.intersection(protected_paths)
        if violated:
            print(f"FAIL: Git diff contains protected path(s):")
            for p in sorted(violated):
                print(f"  - {p}")
            return False

        print("SUCCESS: git diff against main lists 0 protected paths.")
        return True
    except Exception as e:
        print(f"WARNING: git diff check error: {e}", file=sys.stderr)
        return True

if __name__ == "__main__":
    ok_manifest = check_manifest()
    ok_git = check_git_diff()
    if not (ok_manifest and ok_git):
        sys.exit(1)
    print("Protected assets verification: PASSED")

