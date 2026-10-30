"""Create the initial local admin account from environment variables.

Set PREPPULSE_ADMIN_USER, PREPPULSE_ADMIN_NAME, PREPPULSE_ADMIN_PASSWORD,
and PREPPULSE_SESSION_SECRET before running. No public signup route exists.
"""

from __future__ import annotations

import os
import sys

from pwdlib import PasswordHash

from preppulse_api.store import WorkspaceStore, new_id, now


def main() -> None:
    username = os.getenv("PREPPULSE_ADMIN_USER", "").strip().lower()
    name = os.getenv("PREPPULSE_ADMIN_NAME", "").strip()
    password = os.getenv("PREPPULSE_ADMIN_PASSWORD", "")
    if not username or not name or len(password) < 12:
        sys.exit(
            "Set PREPPULSE_ADMIN_USER, PREPPULSE_ADMIN_NAME, and a 12+ character PREPPULSE_ADMIN_PASSWORD"
        )
    store = WorkspaceStore()
    try:
        store.ready()
        store.indexes()
        if store.db.users.find_one({"username": username}):
            sys.exit("Account already exists")
        store.db.users.insert_one(
            {
                "user_id": new_id("USR"),
                "name": name,
                "username": username,
                "role": "admin",
                "password_hash": PasswordHash.recommended().hash(password),
                "disabled": False,
                "created_at": now(),
            }
        )
        print("Initial PrepPulse admin created")
    finally:
        store.client.close()


if __name__ == "__main__":
    main()
