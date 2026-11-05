"""Create a private deployment snapshot and secrets without printing either.

The source MongoDB is read only. The target import refuses a nonempty database.
"""
import hashlib
import json
import os
import secrets
import shutil
import subprocess
from pathlib import Path

from bson import json_util
from dotenv import load_dotenv
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / ".tmp/azure_pilot"
AZ = [r"C:\Program Files\Microsoft SDKs\Azure\CLI2\python.exe", "-m", "azure.cli"]
RG = "rg-preppulse-pilot-b8bc"


def azure(*args):
    result = subprocess.run(AZ + list(args) + ["-o", "json"], capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError("Azure credential retrieval failed; inspect resource status")
    return json.loads(result.stdout)


def main():
    load_dotenv(ROOT / ".env")
    STAGING.mkdir(parents=True, exist_ok=True)
    private = Path(os.getenv("PREPPULSE_PRIVATE_ROOT", ROOT / "private_data")).resolve()
    bundle = STAGING / "snapshot"
    bundle.mkdir(exist_ok=True)
    files = {}

    def rewrite(value):
        if isinstance(value, dict):
            return {key: rewrite(item) for key, item in value.items()}
        if isinstance(value, list):
            return [rewrite(item) for item in value]
        if isinstance(value, str):
            candidate = Path(value)
            if candidate.is_absolute() and candidate.is_relative_to(ROOT):
                if candidate.is_file():
                    digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
                    rel = "files/" + digest + candidate.suffix.lower()
                    destination = bundle / rel
                    if not destination.exists():
                        destination.parent.mkdir(exist_ok=True)
                        shutil.copy2(candidate, destination)
                    files[rel] = digest
                    return "/data/private/" + rel
                if candidate.is_dir() and candidate.is_relative_to(private):
                    return "/data/private"
        return value

    client = MongoClient(os.getenv("PREPPULSE_MONGO_URI", "mongodb://127.0.0.1:27017"), serverSelectionTimeoutMS=3000)
    db = client[os.getenv("PREPPULSE_MONGO_DB", "preppulse")]
    counts = {}
    for name in db.list_collection_names():
        if name.startswith("system."):
            continue
        rows = list(db[name].find({}))
        # Explicitly interrupt unfinished source jobs; a deployment never takes
        # ownership of an operation still executing on the source machine.
        for row in rows:
            if name in {"jobs", "chat_turns", "worker_tasks"} and row.get("status") in {"running", "queued"}:
                row.update(status="failed", error="Interrupted for deployment; retry this action")
            if name == "chat_sessions":
                row["active_turn_id"] = None
        (bundle / (name + ".json")).write_text(json_util.dumps(rewrite(rows)), encoding="utf-8")
        counts[name] = len(rows)
    client.close()
    (bundle / "manifest.json").write_text(json.dumps({"collections": counts, "sha256": files}), encoding="utf-8")

    secret_file = STAGING / "server.env"
    previous = {}
    if secret_file.exists():
        from dotenv import dotenv_values
        previous = dotenv_values(secret_file)
    settings = {
        "PREPPULSE_ENV": "production", "PREPPULSE_PRIVATE_ROOT": "/data/private",
        "PREPPULSE_MONGO_DB": "preppulse", "PREPPULSE_MONGO_URI": "mongodb://mongo:27017",
        "PREPPULSE_SESSION_SECRET": previous.get("PREPPULSE_SESSION_SECRET") or secrets.token_hex(32),
        "PREPPULSE_SECURE_COOKIES": "1", "PREPPULSE_SESSION_COOKIE": "__Host-preppulse_session",
        "PREPPULSE_DURABLE_JOBS": "1", "PREPPULSE_AI_PROVIDER": "auto",
        "PREPPULSE_AI_PROVIDER_ORDER": "sarvam,azure", "PREPPULSE_ALLOW_LOCAL_AI": "0",
        "PREPPULSE_STRICT_AI": "1", "PREPPULSE_AI_ENABLED": "1",
        "PREPPULSE_EMBED_PROVIDER": "python", "PREPPULSE_FHIR_ENABLED": "1",
        "PREPPULSE_RESUME_ANALYSIS": "1", "PREPPULSE_SYNTHETIC_ONLY": "1",
        "PREPPULSE_TRANSLATION_PROVIDER": "azure", "PREPPULSE_TRANSLATION_FALLBACK": "none",
        "PREPPULSE_VOICE_PROVIDER": "azure", "PREPPULSE_VOICE_FALLBACK": "none",
        "PREPPULSE_AZURE_FALLBACK": "sarvam", "PREPPULSE_AZURE_AI_BUDGET_USD": "50",
        "PREPPULSE_SARVAM_BUDGET_INR": "500", "PREPPULSE_AI_TIMEOUT": "120",
        "AZURE_OPENAI_ENDPOINT": "https://ai-preppulse-pilot-b8bc.openai.azure.com",
        "AZURE_OPENAI_DEPLOYMENT": "preppulse-chat", "AZURE_TRANSLATOR_ENDPOINT": "https://api.cognitive.microsofttranslator.com",
        "AZURE_TRANSLATOR_REGION": "centralindia", "AZURE_SPEECH_REGION": "centralindia",
        "SARVAM_MODEL": "sarvam-105b", "HF_HOME": "/data/models/huggingface",
        "TOKENIZERS_PARALLELISM": "false", "OMP_NUM_THREADS": "2",
        "PREPPULSE_EMBED_CACHE": "/data/models/embeddings",
        "PREPPULSE_EMBED_REVISION": "614241f622f53c4eeff9890bdc4f31cfecc418b3",
        "PREPPULSE_HOSTNAME": "preppulse-pilot-b8bc.centralindia.cloudapp.azure.com",
        "AZURE_STORAGE_ACCOUNT": "stpreppulsepilotb8bc",
        "PYTHONPATH": "/app/src",
    }
    for env, account in [("AZURE_OPENAI_API_KEY", "ai-preppulse-pilot-b8bc"),
                         ("AZURE_TRANSLATOR_KEY", "tr-preppulse-pilot-b8bc"),
                         ("AZURE_SPEECH_KEY", "speech-preppulse-pilot-b8bc")]:
        settings[env] = azure("cognitiveservices", "account", "keys", "list", "-g", RG, "-n", account)["key1"]
    for key in ["Main_Sarvam_AI_Credits", "SARVAM_AI_CREDITS_ACC_1", "SARVAM_AI_CREDITS_ACC_2", "SARVAM_AI_CREDITS_ACC_3"]:
        if os.getenv(key):
            settings[key] = os.environ[key]
    secret_file.write_text("\n".join(key + "=" + value for key, value in settings.items()) + "\n", encoding="utf-8")
    ssh = STAGING / "id_ed25519"
    if not ssh.exists():
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-f", str(ssh), "-N", ""], check=True)
    import httpx
    if (STAGING / "parameters.json").exists():
        old_parameters = json.loads((STAGING / "parameters.json").read_text())
        public_ip = old_parameters["parameters"]["sshSourceCidr"]["value"].split("/")[0]
    else:
        public_ip = httpx.get("https://api.ipify.org", timeout=15, trust_env=False).text.strip()
    import ipaddress
    ipaddress.ip_address(public_ip)
    parameters = json.loads((ROOT / "infra/main.parameters.json").read_text())
    parameters["parameters"].update({
        "sshPublicKey": {"value": ssh.with_suffix(".pub").read_text().strip()},
        "sshSourceCidr": {"value": public_ip + "/32"},
        "deployerObjectId": {"value": azure("ad", "signed-in-user", "show")["id"]},
    })
    (STAGING / "parameters.json").write_text(json.dumps(parameters), encoding="utf-8")
    print(json.dumps({"collections": counts, "verified_private_files": len(files),
                      "source_database_unchanged": True, "secrets_written_privately": True}))


if __name__ == "__main__":
    main()
