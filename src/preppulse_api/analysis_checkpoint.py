"""Resume failed analysis nodes only when source, prompt, model and code identities match."""
import hashlib
import json
import os
from pathlib import Path

from pydantic import BaseModel

from preppulse_agents import schemas
from preppulse_api.store import now


def identity(patient, docs):
    import importlib.util

    from preppulse_agents.prompt_loader import _get_prompts_root
    files = [Path(importlib.util.find_spec(module).origin) for module in
             ("preppulse_agents.graph", "preppulse_api.clinical",
              "preppulse_agents.prompt_loader", "preppulse_rag.cloud_provider")]
    files += sorted(_get_prompts_root().rglob("*.yaml"))
    data = {"patient": patient, "docs": [d.get("stage_1_raw_ocr") for d in docs],
            "provider": os.getenv("PREPPULSE_AI_PROVIDER"), "sarvam_model": os.getenv("SARVAM_MODEL", "sarvam-105b"),
            "gemini_model": os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"),
            "azure_deployment": os.getenv("AZURE_OPENAI_DEPLOYMENT"),
            "azure_endpoint": os.getenv("AZURE_OPENAI_ENDPOINT"),
            "provider_order": os.getenv("PREPPULSE_AI_PROVIDER_ORDER"),
            "embedding": os.getenv("PREPPULSE_EMBED_REVISION"),
            "code": [hashlib.sha256(f.read_bytes()).hexdigest() for f in files if f.exists()]}
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


def encode(value):
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [encode(item) for item in value]
    return value


def restore(values):
    models = {"classification": schemas.PatientClassification, "trajectory": schemas.MetabolicTrajectory,
              "care_gaps": schemas.CareGaps, "mismatches": schemas.RecordMismatches,
              "caregiver_prep": schemas.CaregiverPrep, "final_brief": schemas.ConsultationBrief}
    lists = {"metric_series": schemas.LongitudinalMetricSeries,
             "comorbidity_findings": schemas.PriorityFindingItem, "assistive_bubbles": schemas.SmartPromptBubble}
    return {key: models[key].model_validate(value) if key in models and value is not None else
            [lists[key].model_validate(item) for item in value] if key in lists and value is not None else value
            for key, value in values.items()}


def save(store, key, state, next_node):
    values = {name: encode(value) for name, value in state.items() if name != "retriever"}
    store.db.analysis_checkpoints.update_one({"identity": key}, {"$set": {
        "patient_id": state["patient_id"], "values": values, "next_node": next_node,
        "updated_at": now(), "complete": False}}, upsert=True)
