"""CLI utility to provision trusted Patrol Officer accounts.

Usage:
    python -m app.create_patrol --email officer@routewise.ai --name "Inspector Rathore" --password "Patrol2026!"
"""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.services.auth_service import auth_service


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Provision a verified RouteWise Highway Patrol account."
    )
    parser.add_argument("--email", type=str, help="Patrol officer email address")
    parser.add_argument("--name", type=str, help="Patrol officer full name")
    parser.add_argument("--password", type=str, help="Account password (min 6 characters)")
    args = parser.parse_args()

    email = args.email
    name = args.name
    password = args.password

    if not email:
        email = input("Enter Patrol Officer Email: ").strip()
    if not name:
        name = input("Enter Patrol Officer Full Name: ").strip()
    if not password:
        password = getpass.getpass("Enter Patrol Password (min 6 chars): ").strip()

    if not email or "@" not in email:
        print("Error: Valid email address is required.", file=sys.stderr)
        sys.exit(1)
    if not name or len(name) < 2:
        print("Error: Officer full name must be at least 2 characters.", file=sys.stderr)
        sys.exit(1)
    if not password or len(password) < 6:
        print("Error: Password must be at least 6 characters long.", file=sys.stderr)
        sys.exit(1)

    try:
        profile = auth_service.create_patrol_user(
            email=email,
            name=name,
            password=password,
            is_simulated=0,
        )
        print(f"Successfully provisioned patrol account:")
        print(f"  ID:     {profile.id}")
        print(f"  Email:  {profile.email}")
        print(f"  Name:   {profile.name}")
        print(f"  Role:   {profile.role}")
        print("Account is active and ready for patrol dashboard operations.")
    except Exception as e:
        print(f"Error provisioning patrol account: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
