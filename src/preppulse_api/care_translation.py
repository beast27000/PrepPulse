"""On-demand, per-language care translations; signed source instructions stay immutable."""

import copy
import hashlib
import json
import re
import unicodedata
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

from preppulse_api.local_translation import MODEL_VERSION, translate_local

TRANSLATION_MODEL_VERSION = MODEL_VERSION

LANGUAGES = {
    "en": "English",
    "hi": "Hindi",
    "ta": "Tamil",
    "bn": "Bengali",
    "or": "Odia",
    "te": "Telugu",
}
SCRIPTS = {
    "hi": (0x0900, 0x097F),
    "ta": (0x0B80, 0x0BFF),
    "bn": (0x0980, 0x09FF),
    "or": (0x0B00, 0x0B7F),
    "te": (0x0C00, 0x0C7F),
}
executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="care-language")
WORKER_INSTANCE = uuid.uuid4().hex


def source_locale(text):
    letters = [c for c in text if c.isalpha()]
    for language, (lo, hi) in SCRIPTS.items():
        if letters and sum(lo <= ord(c) <= hi for c in letters) / len(letters) >= 0.25:
            return language
    return "en"


def segments(plan):
    result = [
        ("item:" + x["item_id"], x["text"], x.get("source_language", "en"))
        for x in plan.get("items", [])
    ]
    if plan.get("doctor_notes"):
        result.append(("notes", plan["doctor_notes"], plan.get("notes_language", "en")))
    for med in plan.get("medications", []):
        result.append(("dose:" + med["medication_id"], med["dose"], source_locale(med["dose"])))
    return result


def numbers(text):
    normalized = "".join(str(unicodedata.digit(c)) if c.isdigit() else c for c in text)
    return sorted(re.findall(r"\d+(?:[.,]\d+)?", normalized))


def usable(text, source, language, source_language="en"):
    if not isinstance(text, str) or not text.strip() or numbers(text) != numbers(source):
        return False
    for unit in re.findall(
        r"(?<![A-Za-z])(?:mg/dL|mg/g|mmol/mol|mmol/L|mL/min|mmHg|mcg|µg|mg|mL|kg|g|L|U|IU|HbA1c|eGFR|LDL|ACR)(?![A-Za-z])",
        source,
    ):
        if unit.casefold() not in text.casefold():
            return False
    if language == source_language:
        return text.strip() == source.strip()
    if not any(
        c.isalpha()
        for c in re.sub(r"(?<![A-Za-z])(?:mg|mcg|µg|mL|kg|g|L|IU|U)(?![A-Za-z])", "", source)
    ):
        return text.strip() == source.strip()
    if text.strip().casefold() == source.strip().casefold():
        return False
    if language in SCRIPTS:
        lo, hi = SCRIPTS[language]
        letters = [c for c in text if c.isalpha()]
        return bool(letters) and sum(lo <= ord(c) <= hi for c in letters) / len(letters) >= 0.25
    return bool(re.search(r"[A-Za-z]", text))


def source_hash(plan):
    return hashlib.sha256(json.dumps(segments(plan), ensure_ascii=False).encode()).hexdigest()


def translate_batch(batch, language):
    result = translate_local(batch, language)
    if not isinstance(result, dict) or set(result) - {key for key, _, _ in batch}:
        raise ValueError("Translation worker returned an invalid segment mapping")
    return result


def cache_key(plan, kind, identity, revision, language):
    return {
        "kind": kind,
        "identity": identity,
        "revision": revision,
        "language": language,
        "source_hash": hashlib.sha256(
            (TRANSLATION_MODEL_VERSION + source_hash(plan)).encode()
        ).hexdigest(),
    }


def overlay(store, plan, kind, identity, revision):
    result = copy.deepcopy(plan)
    # Discard legacy chat-model translations. Only complete snapshots from the
    # selected translation model may populate a target language.
    for item in result.get("items", []):
        item["texts"] = {item.get("source_language", "en"): item["text"]}
    for med in result.get("medications", []):
        med["dose_texts"] = {source_locale(med["dose"]): med["dose"]}
    result["notes_texts"] = {result.get("notes_language", "en"): result.get("doctor_notes", "")}
    originals = {key: (text, source) for key, text, source in segments(plan)}
    statuses = {}
    for row in store.db.care_language_cache.find(
        {
            "kind": kind,
            "identity": identity,
            "revision": revision,
            "source_hash": cache_key(plan, kind, identity, revision, "en")["source_hash"],
        }
    ):
        statuses[row["language"]] = {
            k: row.get(k) for k in ("status", "completed", "total", "error")
        }
        valid = {
            key: value
            for key, value in row.get("texts", {}).items()
            if key in originals
            and usable(value, originals[key][0], row["language"], originals[key][1])
        }
        if row.get("status") != "complete" or len(valid) != len(originals):
            if row.get("status") == "complete":
                statuses[row["language"]]["status"] = "unavailable"
            continue
        for key, text in valid.items():
            if key in originals and usable(
                text, originals[key][0], row["language"], originals[key][1]
            ):
                if key == "notes":
                    result.setdefault("notes_texts", {})[row["language"]] = text
                elif key.startswith("item:"):
                    next((x for x in result["items"] if x["item_id"] == key[5:]), {}).setdefault(
                        "texts", {}
                    )[row["language"]] = text
                elif key.startswith("dose:"):
                    next(
                        (x for x in result.get("medications", []) if x["medication_id"] == key[5:]),
                        {},
                    ).setdefault("dose_texts", {})[row["language"]] = text
    result["language_status"] = statuses
    return result


def segment_key(text, source, language):
    return hashlib.sha256(
        json.dumps(
            [TRANSLATION_MODEL_VERSION, source, language, text],
            ensure_ascii=False,
        ).encode()
    ).hexdigest()


def translated_segments(plan, language, store=None):
    result = {}
    for key, text, source in segments(plan):
        if source == language:
            result[key] = text
        elif store is not None:
            row = store.db.care_segment_cache.find_one(
                {
                    "patient_id": plan.get("patient_id"),
                    "key": segment_key(text, source, language),
                }
            )
            if row and usable(row.get("text"), text, language, source):
                result[key] = row["text"]
    return result


def request_language(store, plan, kind, identity, revision, language):
    from pymongo import ReturnDocument
    from pymongo.errors import DuplicateKeyError

    from preppulse_api.store import now

    if language not in LANGUAGES:
        raise ValueError("Unsupported translation language")
    key = cache_key(plan, kind, identity, revision, language)
    existing = store.db.care_language_cache.find_one(key) or {}
    ready = translated_segments(plan, language, store)
    originals = {segment: (text, source) for segment, text, source in segments(plan)}
    ready.update(
        {
            k: v
            for k, v in existing.get("texts", {}).items()
            if k in originals and usable(v, originals[k][0], language, originals[k][1])
        }
    )
    total = len(segments(plan))
    if len(ready) == total:
        store.db.care_language_cache.update_one(
            key,
            {"$set": {"status": "complete", "texts": ready, "completed": total, "total": total}},
            upsert=True,
        )
        return {"status": "complete"}
    cutoff = (datetime.now(UTC) - timedelta(minutes=15)).isoformat()
    if (
        existing.get("status") in {"queued", "running"}
        and existing.get("updated_at", "") > cutoff
        and existing.get("worker_instance") == WORKER_INSTANCE
    ):
        return {"status": existing["status"]}
    try:
        store.db.care_language_cache.update_one(
            key, {"$setOnInsert": {"status": "pending", "texts": ready}}, upsert=True
        )
    except DuplicateKeyError:
        pass
    claimed = store.db.care_language_cache.find_one_and_update(
        {
            **key,
            "$or": [
                {"status": {"$nin": ["queued", "running"]}},
                {"updated_at": {"$lte": cutoff}},
                {"worker_instance": {"$ne": WORKER_INSTANCE}},
            ],
        },
        {
            "$set": {
                "status": "queued",
                "texts": ready,
                "completed": len(ready),
                "total": total,
                "updated_at": now(),
                "worker_instance": WORKER_INSTANCE,
                "error": None,
            }
        },
        return_document=ReturnDocument.AFTER,
    )
    if claimed:
        executor.submit(run_language_job, kind, identity, revision, language)
    return {"status": "queued" if claimed else "running"}


def run_language_job(kind, identity, revision, language):
    from preppulse_api.store import WorkspaceStore, now

    store = WorkspaceStore()
    try:
        if kind == "draft":
            plan = store.db.care_drafts.find_one({"visit_id": identity, "revision": revision})
        elif kind == "preview":
            from preppulse_api.care import suggestion_plan

            plan = suggestion_plan(store, identity)
            if plan["revision"] != revision:
                return
        else:
            plan = store.db.pathways.find_one({"pathway_id": identity})
        if not plan:
            return
        from preppulse_api.operations import assert_not_deleting
        assert_not_deleting(store, plan["patient_id"])
        key = cache_key(plan, kind, identity, revision, language)
        row = store.db.care_language_cache.find_one(key) or {}
        originals = {segment: (text, source) for segment, text, source in segments(plan)}
        texts = {
            k: v
            for k, v in row.get("texts", {}).items()
            if k in originals and usable(v, originals[k][0], language, originals[k][1])
        }
        texts.update(translated_segments(plan, language, store))
        missing = [
            seg for seg in segments(plan) if not usable(texts.get(seg[0]), seg[1], language, seg[2])
        ]
        failures = []
        store.db.care_language_cache.update_one(
            key, {"$set": {"status": "running", "updated_at": now()}}
        )
        for start in range(0, len(missing), 3):
            batch = missing[start : start + 3]
            try:
                data = translate_batch(batch, language)
            except Exception as exc:  # noqa: BLE001 - preserve successful batches on provider failure
                failures.append(str(exc)[:200])
                continue
            assert_not_deleting(store, plan["patient_id"])
            for segment, source_text, source_language in batch:
                value = data.get(segment)
                if usable(value, source_text, language, source_language):
                    texts[segment] = value.strip()
                    store.db.care_segment_cache.update_one(
                        {
                            "patient_id": plan.get("patient_id"),
                            "key": segment_key(source_text, source_language, language),
                        },
                        {"$set": {"text": value.strip()}},
                        upsert=True,
                    )
                else:
                    failures.append("Incomplete or changed translation")
            if kind == "draft" and not store.db.care_drafts.find_one(
                {"visit_id": identity, "revision": revision}
            ):
                return
            store.db.care_language_cache.update_one(
                key, {"$set": {"texts": texts, "completed": len(texts), "updated_at": now()}}
            )
        status = (
            "complete"
            if len(texts) == len(segments(plan))
            else "partial"
            if texts
            else "unavailable"
        )
        store.db.care_language_cache.update_one(
            key,
            {
                "$set": {
                    "status": status,
                    "texts": texts,
                    "completed": len(texts),
                    "total": len(segments(plan)),
                    "error": failures[0] if failures else None,
                    "updated_at": now(),
                }
            },
        )
        if (
            status == "complete"
            and kind == "signed"
            and language == "en"
            and plan.get("patient_id")
            and plan.get("approved_at")
        ):
            assert_not_deleting(store, plan["patient_id"])
            from preppulse_api.care import archive_pdf

            archive_pdf(store, overlay(store, plan, kind, identity, revision))
    except Exception as exc:  # noqa: BLE001 - keep failed jobs retryable after worker failure
        if "key" in locals():
            store.db.care_language_cache.update_one(
                key,
                {"$set": {"status": "unavailable", "error": str(exc)[:200], "updated_at": now()}},
            )
    finally:
        store.client.close()
