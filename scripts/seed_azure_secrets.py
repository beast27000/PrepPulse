"""Seed existing Key Vault using private files, never secret command-line values."""
import secrets
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / ".tmp/azure_pilot"
AZ = [r"C:\Program Files\Microsoft SDKs\Azure\CLI2\python.exe", "-m", "azure.cli"]


def main():
    backup = STAGING / "backup.key"
    if not backup.exists():
        backup.write_text(secrets.token_hex(32))
    names = {"server-environment": STAGING / "server.env", "backup-encryption-key": backup,
             "operator-ssh-key": STAGING / "id_ed25519"}
    if (STAGING / "pilot_access.json").exists():
        names["pilot-access"] = STAGING / "pilot_access.json"
    for name, path in names.items():
        result = subprocess.run(AZ + ["keyvault", "secret", "set", "--vault-name", "kv-preppulse-pilot-b8bc",
            "--name", name, "--file", str(path), "--query", "id", "-o", "tsv"], capture_output=True, text=True, check=False)
        if result.returncode:
            raise SystemExit("Key Vault seeding failed; verify Secrets Officer role propagation")
    print("Deployment secrets stored in Key Vault")


if __name__ == "__main__":
    main()
