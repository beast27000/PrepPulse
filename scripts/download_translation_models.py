"""Download pinned official model files once; inference never contacts Hugging Face."""

import argparse
import hashlib
import os
from pathlib import Path

# Direct HTTPS downloads resume predictably on Windows/WSL shared drives.
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

import httpx
from huggingface_hub import HfApi, get_token, hf_hub_url, snapshot_download
from huggingface_hub.errors import GatedRepoError

MODELS = {
    "en-indic": ("ai4bharat/indictrans2-en-indic-1B", "89cd0007fd7b9e0693a2fd4404d187e07dac79fd"),
    "indic-en": ("ai4bharat/indictrans2-indic-en-1B", "ac3daf0ecd37be3b6957764a9179ab2b07fa9d6a"),
}


def download_weights(repository, revision, folder):
    """Stream/resume large weights and verify the official LFS SHA-256 digest."""
    info = HfApi().model_info(repository, revision=revision, files_metadata=True)
    metadata = next(x for x in info.siblings if x.rfilename == "model.safetensors")
    target = folder / "model.safetensors"
    expected_hash = metadata.lfs.sha256
    if target.is_file() and target.stat().st_size == metadata.size:
        with target.open("rb") as source:
            if hashlib.file_digest(source, "sha256").hexdigest() == expected_hash:
                print(f"Verified {repository} weights", flush=True)
                return
    partial = folder / "model.safetensors.part"
    offset = partial.stat().st_size if partial.exists() else 0
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    if offset:
        headers["Range"] = f"bytes={offset}-"
    with (
        httpx.Client(follow_redirects=True, timeout=httpx.Timeout(120, connect=30)) as client,
        client.stream(
            "GET", hf_hub_url(repository, "model.safetensors", revision=revision), headers=headers
        ) as response,
    ):
        response.raise_for_status()
        if offset and response.status_code != 206:
            offset = 0
        if response.status_code == 206 and not response.headers.get(
            "content-range", ""
        ).startswith(f"bytes {offset}-"):
            raise ValueError("Model download returned an unexpected byte range")
        progress = offset // (256 * 1024 * 1024)
        with partial.open("ab" if offset else "wb") as output:
            for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                output.write(chunk)
                offset += len(chunk)
                if offset // (256 * 1024 * 1024) > progress:
                    progress = offset // (256 * 1024 * 1024)
                    print(
                        f"{repository}: {offset / 1e9:.2f}/{metadata.size / 1e9:.2f} GB",
                        flush=True,
                    )
    with partial.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    if offset != metadata.size or digest != expected_hash:
        raise ValueError(
            "Model checksum failed. Remove model.safetensors.part in this model folder and retry."
        )
    partial.replace(target)
    print(f"Verified {repository} weights", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / ".local_models/indictrans2",
    )
    args = parser.parse_args()
    for direction, (repository, revision) in MODELS.items():
        print(f"Downloading {repository} ({revision[:8]})", flush=True)
        try:
            folder = args.output / direction
            snapshot_download(
                repository,
                revision=revision,
                local_dir=folder,
                allow_patterns=[
                    "*.json",
                    "*.py",
                    "model.SRC",
                    "model.TGT",
                    "LICENSE",
                ],
            )
            download_weights(repository, revision, folder)
        except GatedRepoError:
            raise SystemExit(
                f"Model access is required: accept the conditions at https://huggingface.co/{repository}, then run hf auth login and retry."
            ) from None
    print(f"Local model files ready: {args.output.resolve()}")


if __name__ == "__main__":
    main()
