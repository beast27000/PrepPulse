"""Restore only into a separate verification database; never replace live data.

Run as root on the pilot VM after backup.sh completes. The operator retains the
encrypted backup and its separately stored key; plaintext verification files are
removed after successful checks.
"""
import hashlib
import json
import subprocess
import tarfile
from pathlib import Path


def main():
    archive = max(Path("/data/backups").glob("preppulse-*.tar.gz.enc"))
    folder = Path("/data/restore-verification")
    folder.mkdir(mode=0o700, exist_ok=True)
    plaintext = folder / "snapshot.tar.gz"
    subprocess.run(["openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-iter", "200000",
                    "-in", str(archive), "-out", str(plaintext), "-pass", "file:/etc/preppulse/backup.key"], check=True)
    mongo = folder / "mongodb.archive.gz"
    verified = 0
    with tarfile.open(plaintext) as package:
        with mongo.open("wb") as output:
            output.write(package.extractfile("private/mongodb.archive.gz").read())
        for item in package.getmembers():
            if item.isfile() and item.name.startswith("private/files/"):
                expected = Path(item.name).stem
                if len(expected) == 64:
                    digest = hashlib.sha256()
                    with package.extractfile(item) as member:
                        for chunk in iter(lambda: member.read(1024 * 1024), b""):
                            digest.update(chunk)
                    assert digest.hexdigest() == expected
                    verified += 1
    compose = ["docker", "compose", "-f", "/opt/preppulse/deployment/compose.yaml"]
    with mongo.open("rb") as handle:
        subprocess.run([*compose, "exec", "-T", "mongo", "mongorestore", "--quiet", "--archive", "--gzip",
                        "--drop", "--nsFrom", "preppulse.*", "--nsTo", "preppulse_restore_verification.*"],
                       stdin=handle, check=True, capture_output=True)
    expression = """const a=db.getSiblingDB('preppulse'),b=db.getSiblingDB('preppulse_restore_verification');
const names=b.getCollectionNames();const mismatch=names.filter(n=> !['audit_events','login_attempts','sessions'].includes(n) && a[n].countDocuments({})!==b[n].countDocuments({}));
print(JSON.stringify({collections:names.length,mismatch:mismatch,patients:b.patients.countDocuments({}),users:b.users.countDocuments({})}));"""
    result = subprocess.run([*compose, "exec", "-T", "mongo", "mongosh", "--quiet", "--eval", expression],
                            check=True, capture_output=True, text=True)
    counts = json.loads(result.stdout.strip())
    assert not counts["mismatch"], counts
    assert counts["collections"] > 15 and verified >= 68
    counts.update(ok=True, source_hashes_verified=verified, encrypted_archive=archive.name,
                  restored_database="preppulse_restore_verification")
    (folder / "result.json").write_text(json.dumps(counts))
    plaintext.unlink()
    mongo.unlink()
    print(json.dumps(counts))


if __name__ == "__main__":
    main()
