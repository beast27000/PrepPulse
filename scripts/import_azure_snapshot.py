"""Run inside the Azure API image against a NEW, empty target database."""
import hashlib
import json
from pathlib import Path

from bson import json_util

from preppulse_api.store import WorkspaceStore


def main():
    root = Path("/data/private")
    manifest = json.loads((root / "manifest.json").read_text())
    store = WorkspaceStore()
    if any(store.db[name].count_documents({}) for name in store.db.list_collection_names()):
        raise SystemExit("Refusing to overwrite a nonempty deployment database")
    for rel, expected in manifest["sha256"].items():
        if hashlib.sha256((root / rel).read_bytes()).hexdigest() != expected:
            raise SystemExit("Private source-file checksum failed")
    for name, expected in manifest["collections"].items():
        rows = json_util.loads((root / (name + ".json")).read_text())
        if rows:
            store.db[name].insert_many(rows)
        if store.db[name].count_documents({}) != expected:
            raise SystemExit("Collection verification failed")
    store.indexes()
    print(json.dumps({"imported": manifest["collections"], "files_verified": len(manifest["sha256"])}))
    store.client.close()


if __name__ == "__main__":
    main()
