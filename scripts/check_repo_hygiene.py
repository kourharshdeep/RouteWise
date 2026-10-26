"""Repository Hygiene and Secret Verification Script.

Ensures no tracked files contain:
1. The old compromised default secret string.
2. The old hardcoded demo passwords.
3. Any tracked .env file.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# Construct target forbidden strings dynamically so the script file itself is clean
FORBIDDEN_CREDENTIALS = [
    ("routewise" + "-nh44-ramban-banihal-secure-salt-2026", "Compromised default secret key"),
    ("Demo" + "Patrol2026!", "Compromised demo patrol password"),
    ("routewise" + "2026", "Compromised demo user password"),
]


def check_hygiene() -> bool:
    repo_root = Path(__file__).resolve().parent.parent
    try:
        output = subprocess.check_output(
            ["git", "ls-files"],
            cwd=repo_root,
            text=True,
            encoding="utf-8",
        )
    except Exception as e:
        print(f"Error executing git ls-files: {e}", file=sys.stderr)
        return False

    tracked_files = [line.strip() for line in output.splitlines() if line.strip()]
    violations = []

    # 1. Check for tracked .env files (excluding .env.example)
    for rel_path in tracked_files:
        name = Path(rel_path).name
        if name == ".env" or (name.startswith(".env.") and name != ".env.example"):
            violations.append(f"Tracked environment file found: {rel_path}")

    # 2. Check for leaked secret or credential strings in tracked text files
    for rel_path in tracked_files:
        if rel_path.replace("\\", "/") == "scripts/check_repo_hygiene.py":
            continue
        file_path = repo_root / rel_path
        if not file_path.is_file():
            continue
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                for secret_str, desc in FORBIDDEN_CREDENTIALS:
                    if secret_str in content:
                        violations.append(
                            f"Tracked file '{rel_path}' contains {desc} ('{secret_str}')"
                        )
        except Exception as e:
            violations.append(f"Unable to read tracked file '{rel_path}': {e}")

    if violations:
        print("FAIL: Repository hygiene violations detected:", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        return False

    print(f"PASS: Repository hygiene verified clean across {len(tracked_files)} tracked files.")
    return True


if __name__ == "__main__":
    success = check_hygiene()
    sys.exit(0 if success else 1)
