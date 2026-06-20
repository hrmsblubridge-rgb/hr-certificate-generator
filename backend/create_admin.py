#!/usr/bin/env python3
"""
Interactive admin bootstrap / password-reset utility.

Run this once on a fresh deployment when no `HR_USERNAME` / `HR_PASSWORD`
env vars are provided, or any time you need to reset the admin password
from outside the running app.

Usage (on Render shell, locally, or any host with `MONGO_URL`/`DB_NAME`
in the environment / `backend/.env`):

    python create_admin.py

The script:
  * Connects to MongoDB using `MONGO_URL` and `DB_NAME` from env.
  * Prompts for a username (default: `admin`) and a password (typed
    twice, never echoed). Minimum length: 8 characters.
  * Bcrypt-hashes the password and stores ONLY the hash in
    `users.<username>.password_hash`. The plain text is never written
    to disk, logs, or shell history.
  * If the user row already exists, asks for confirmation before
    overwriting the hash (use this path to reset a forgotten password).
"""
from __future__ import annotations

import asyncio
import getpass
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

# Load backend/.env so MONGO_URL / DB_NAME work both locally and on Render.
load_dotenv(Path(__file__).parent / ".env")

from auth import hash_password  # noqa: E402  (after env load)


MIN_PASSWORD_LEN = 8


def _read_username() -> str:
    raw = input("Admin username [admin]: ").strip().lower()
    return raw or "admin"


def _read_new_password() -> str:
    while True:
        pw = getpass.getpass("New password (min 8 chars, hidden): ")
        if len(pw) < MIN_PASSWORD_LEN:
            print(f"  -> too short, need at least {MIN_PASSWORD_LEN} chars")
            continue
        pw2 = getpass.getpass("Confirm password: ")
        if pw != pw2:
            print("  -> passwords do not match, try again")
            continue
        return pw


async def main() -> int:
    mongo_url = os.environ.get("MONGO_URL")
    db_name   = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        print("ERROR: MONGO_URL and DB_NAME must be set (check backend/.env "
              "or Render Environment).", file=sys.stderr)
        return 2

    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    username = _read_username()
    existing = await db.users.find_one({"_id": username})
    if existing is not None:
        ans = input(
            f"User '{username}' already exists (created "
            f"{existing.get('created_at')}). Overwrite password? [y/N]: "
        ).strip().lower()
        if ans not in ("y", "yes"):
            print("Aborted. No changes made.")
            return 1

    pw = _read_new_password()
    hashed = hash_password(pw)
    now = datetime.now(timezone.utc)

    if existing is None:
        await db.users.insert_one({
            "_id": username,
            "password_hash": hashed,
            "role": "admin",
            "created_at": now,
        })
        print(f"OK: admin '{username}' created.")
    else:
        await db.users.update_one(
            {"_id": username},
            {"$set": {"password_hash": hashed, "password_changed_at": now}},
        )
        print(f"OK: password for '{username}' rotated.")

    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
