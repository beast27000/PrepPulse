"""Upload an encrypted snapshot using the VM managed identity; no account keys."""
import hashlib
import os
import sys
from pathlib import Path

from azure.identity import ManagedIdentityCredential
from azure.storage.blob import BlobServiceClient

if __name__ == "__main__":
    path = Path(sys.argv[1])
    if path.suffix != ".enc" or not path.is_file():
        raise SystemExit("Only encrypted archives are accepted")
    client = BlobServiceClient("https://" + os.environ["AZURE_STORAGE_ACCOUNT"] + ".blob.core.windows.net",
                               credential=ManagedIdentityCredential())
    blob = client.get_blob_client("backups", path.name)
    with path.open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
        handle.seek(0)
        blob.upload_blob(handle, overwrite=False, metadata={"sha256": digest})
    assert blob.get_blob_properties().size == path.stat().st_size
    assert hashlib.sha256(blob.download_blob().readall()).hexdigest() == digest
    print("Encrypted backup uploaded and downloaded checksum verified")
