"""Live synthetic-patient rehearsal. Each provider has its own cloned database.

Run prepare_ui_testing.py first. Reports and clinical responses stay in ignored .tmp.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import traceback
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=["sarvam", "gemini"], required=True)
    parser.add_argument("--stage", choices=["analyze", "chat", "translation", "speech", "all"], default="all")
    parser.add_argument("--alias", default="PP001")
    parser.add_argument("--fresh-ocr", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    os.environ.update({"PREPPULSE_MONGO_DB": "preppulse_ui_testing" + ("_gemini" if args.provider == "gemini" else ""),
                       "PREPPULSE_PRIVATE_ROOT": str(root / ".tmp/ui_testing/private_data"),
                       "PREPPULSE_AI_PROVIDER": args.provider, "PREPPULSE_SYNTHETIC_ONLY": "1",
                       "PREPPULSE_FHIR_ENABLED": "1", "PREPPULSE_STRICT_AI": "1",
                       "PREPPULSE_RESUME_ANALYSIS": "1", "PREPPULSE_AI_TIMEOUT": "180",
                       "PREPPULSE_GEMINI_REQUEST_LIMIT": "200",
                       "PREPPULSE_EMBED_PROVIDER": "python",
                       "GEMINI_MODEL": "gemini-3.5-flash-lite",
                       "PREPPULSE_EMBED_REVISION": "614241f622f53c4eeff9890bdc4f31cfecc418b3"})
    from preppulse_api.care import ensure_draft, local_day
    from preppulse_api.chat_service import run_chat_turn
    from preppulse_api.clinical import process_patient
    from preppulse_api.cloud_services import speak_sarvam, transcribe_sarvam, translate_sarvam
    from preppulse_api.store import WorkspaceStore, new_id, now
    store = WorkspaceStore()
    store.indexes()
    if not store.db.name.startswith("preppulse_ui_testing"):
        raise RuntimeError("Test database required")
    alias = store.db.patient_aliases.find_one({"alias": args.alias})
    if not alias or args.alias not in {"PP001", "PP002", "PP003", "PP004"}:
        raise RuntimeError("Select an imported synthetic demonstration patient")
    pid = alias["patient_id"]
    records = list(store.db.workspace_documents.find({"patient_id": pid}, {"_id": 0}))
    file_hashes = sorted(hashlib.sha256(Path(r["source_path"]).read_bytes()).hexdigest() for r in records)
    report_path = root / ".tmp/ui_testing/results" / f"{args.provider}-{args.stage}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
    report.update({"provider": args.provider, "patient_alias": args.alias,
                   "source_hashes": file_hashes, "record_count": len(records)})

    def save():
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    def progress(*stage):
        print(json.dumps({"provider": args.provider, "progress": stage}), flush=True)

    def execute(name, operation):
        started = time.monotonic()
        try:
            result = operation()
            report[name] = {"status": "passed", "seconds": round(time.monotonic()-started, 2), "result": result}
        except Exception as exc:  # noqa: BLE001 - collect failures without leaking prompts
            # Keep errors content-free: exception strings can contain clinical prompts.
            report[name] = {"status": "failed", "seconds": round(time.monotonic()-started, 2),
                            "error_type": type(exc).__name__, "frames": [
                                {"file": Path(f.filename).name, "line": f.lineno, "function": f.name}
                                for f in traceback.extract_tb(exc.__traceback__)[-4:]]}
            print(json.dumps({"stage": name, "error_type": type(exc).__name__}), flush=True)
        save()

    if args.stage in {"analyze", "all"}:
        doctor = store.db.patient_access.find_one({"patient_id": pid})["doctor_id"]
        appointment_id = new_id("APT")
        store.db.appointments.insert_one({"appointment_id": appointment_id, "patient_id": pid,
            "doctor_id": doctor, "date": local_day().isoformat(), "time": "11:30",
            "status": "scheduled", "reason": "Synthetic API rehearsal", "created_at": now()})
        if args.fresh_ocr:
            store.db.patient_documents.delete_many({"patient_id": pid})
            store.db.briefs.delete_many({"patient_id": pid})
        def analysis():
            brief = process_patient(store, pid, progress)
            visit = {"visit_id": new_id("VIS"), "appointment_id": appointment_id, "patient_id": pid,
                     "doctor_id": doctor, "status": "active", "admitted": False,
                     "started_at": now(), "doctor_notes": ""}
            store.db.visits.insert_one(visit)
            draft = ensure_draft(store, visit)
            return {"findings": len(brief["priority_findings"]),
                    "metric_series": len(brief["metric_series"]), "checklist_items": len(draft["items"]),
                    "structured": brief.get("structured_processing"), "visit_id": visit["visit_id"]}
        execute("analysis", analysis)
    if args.stage in {"chat", "all"}:
        session = {"session_id": new_id("CHAT"), "patient_id": pid,
                   "user_id": store.db.patient_access.find_one({"patient_id": pid})["doctor_id"],
                   "title": f"{args.provider} API rehearsal", "created_at": now(), "updated_at": now()}
        store.db.chat_sessions.insert_one(session)
        history = []
        for i, question in enumerate([
            "Summarize this patient's documented diabetes journey and changes in HbA1c, with source citations.",
            "What admissions and other conditions are explicitly documented? Cite the records and do not invent dates.",
            "Plot HbA1c and fasting glucose over the past 3 years.",
            "Show a chart of this patient's heart disease.",
        ]):
            def chat(question=question):
                result = run_chat_turn(store, session, question, history, progress)
                for artifact in result.get("artifacts", []):
                    store.db.chat_artifacts.insert_one({**artifact, "user_id": session["user_id"]})
                answer = result.get("text") or result.get("answer") or ""
                for role, text in [("user", question), ("assistant", answer)]:
                    store.db.chat_messages.insert_one({"message_id": new_id("MSG"),
                        "session_id": session["session_id"], "role": role, "text": text,
                        "created_at": now(), **({"citations": result.get("citations", []),
                                                 "artifacts": result.get("artifacts", [])} if role == "assistant" else {})})
                    history.append({"role": role, "text": text})
                return result
            execute(f"chat_{i+1}", chat)
    if args.stage in {"translation", "all"}:
        batch = [("a", "Bring earlier test reports and prescriptions to the visit.", "en"),
                 ("b", "Record the HbA1c result of 8.3% and ask the doctor about the change.", "en"),
                 ("c", "Take 10 mg only as prescribed by the doctor.", "en")]
        for language in ["hi", "ta", "bn", "or", "te"]:
            execute("translation_" + language, lambda language=language: translate_sarvam(batch, language))
    if args.stage in {"speech", "all"}:
        def speech():
            audio = speak_sarvam("Please show the recorded blood sugar results.")
            (report_path.parent / "synthetic-voice.wav").write_bytes(audio)
            return {"wav_bytes": len(audio), "transcript": transcribe_sarvam(audio, "en", "sample.wav")}
        execute("speech_roundtrip", speech)
    print(json.dumps({"report": str(report_path), "checks": {k: v["status"] for k,v in report.items()
                                                             if isinstance(v, dict) and "status" in v}}), flush=True)
    store.client.close()
    if any(isinstance(value, dict) and value.get("status") == "failed" for value in report.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
