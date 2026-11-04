"""Clone the local workspace for an isolated rehearsal. Never clear an existing database."""
from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import subprocess
from pathlib import Path

from pymongo import MongoClient

from preppulse_rag.runtime import ROOT


def rewrite(value, old_root, new_root):
    if isinstance(value, dict):
        return {key: rewrite(item, old_root, new_root) for key, item in value.items()}
    if isinstance(value, list):
        return [rewrite(item, old_root, new_root) for item in value]
    if isinstance(value, str) and value.casefold().startswith(str(old_root).casefold() + os.sep):
        return str(new_root / Path(value).relative_to(old_root))
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default="preppulse_ui_testing")
    args = parser.parse_args()
    if subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip() != "ui_testing":
        raise SystemExit("Switch to ui_testing before preparing the rehearsal")
    if not args.database.startswith("preppulse_ui_testing"):
        raise SystemExit("Only preppulse_ui_testing* target databases are permitted")
    source_name = os.getenv("PREPPULSE_MONGO_DB", "preppulse")
    if source_name == args.database:
        raise SystemExit("Source and target must differ")
    old_root = Path(os.getenv("PREPPULSE_PRIVATE_ROOT", str(ROOT / "private_data"))).resolve()
    new_root = ROOT / ".tmp/ui_testing/private_data"
    if old_root == new_root or old_root.is_relative_to(new_root) or new_root.is_relative_to(old_root):
        raise SystemExit("Source and target file roots must be disjoint")
    client = MongoClient(os.getenv("PREPPULSE_MONGO_URI", "mongodb://127.0.0.1:27017"),
                         serverSelectionTimeoutMS=3000)
    target, source = client[args.database], client[source_name]
    if target.list_collection_names():
        raise SystemExit("Test database already exists. It was left intact; reuse it or choose a fresh suffix.")
    shutil.copytree(old_root, new_root, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("*.sqlite3*", "*.log"))
    counts = {}
    for name in source.list_collection_names():
        rows = [rewrite(row, old_root, new_root) for row in source[name].find({})]
        if rows:
            target[name].insert_many(rows)
        counts[name] = len(rows)
    profile = ROOT / ".tmp/ui_testing/profile.json"
    if not profile.exists():
        profile.write_text(json.dumps({"private_root": str(new_root),
                                      "session_secret": secrets.token_hex(32)}), encoding="utf-8")
    print(json.dumps({"database": args.database, "collections_copied": counts,
                      "source_unchanged": True}, indent=2))
    client.close()


if __name__ == "__main__":
    main()
