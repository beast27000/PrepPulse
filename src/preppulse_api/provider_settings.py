"""Private shared routing preference read by both the API and worker."""
import json
import os
from pathlib import Path


def routing():
    path = Path(os.getenv("PREPPULSE_PRIVATE_ROOT", "private_data")) / "ai-routing.json"
    try:
        value = json.loads(path.read_text())
        if value.get("mode") in {"auto", "azure", "sarvam", "disabled"}:
            return value["mode"]
    except (OSError, ValueError):
        pass
    return "auto"


def save(mode):
    path = Path(os.getenv("PREPPULSE_PRIVATE_ROOT", "private_data")) / "ai-routing.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps({"mode": mode}))
    temp.replace(path)
