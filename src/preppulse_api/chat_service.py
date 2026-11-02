"""Chart-capable, evidence-linked patient conversations with persisted artifacts."""

from __future__ import annotations

import re
from datetime import date

from preppulse_api.clinical import locate_citation, retriever_for_patient
from preppulse_api.evidence_catalog import build_catalog
from preppulse_api.store import WorkspaceStore, new_id, now
from preppulse_rag.llm_provider import LLMFactory, MockClinicalChatModel


def chart_requested(question: str) -> bool:
    return bool(
        re.search(
            r"\b(chart|graph|plot|visuali[sz]\w*|timeline|tabular|table)\b", question, re.IGNORECASE
        )
    )


def cardiac_chart_requested(question: str) -> bool:
    return bool(
        re.search(
            r"\b(heart|cardiac|coronary|cardiovascular|cardiology|ejection|lvef|troponin|ecg|ekg|echocardiogram|echocardiography)\b",
            question,
            re.IGNORECASE,
        )
    )


SUPPORTED_CHARTS = (
    "HbA1c, fasting/post-meal glucose, eGFR, urine ACR, creatinine, LDL, and blood pressure"
)


def make_chart_artifact(
    catalog: dict, question: str, session_id: str, patient_id: str
) -> dict | None:
    """Select real OCR measurements; no model-generated plot coordinates or values."""
    if cardiac_chart_requested(question):
        return None
    lower = question.lower()
    available = catalog["metric_series"]
    names = []
    for name, pattern in [
        ("HbA1c", r"hba1c|a1c"),
        ("Fasting glucose", r"fasting|\bfpg\b"),
        ("Post-meal glucose", r"post.meal|postprandial"),
        ("eGFR", r"egfr"),
        ("Urine ACR", r"\bacr\b|albumin"),
        ("Creatinine", r"creatinine"),
        ("LDL cholesterol", r"\bldl\b|cholesterol"),
        ("Systolic BP", r"blood pressure|\bbp\b|systolic"),
        ("Diastolic BP", r"blood pressure|\bbp\b|diastolic"),
        ("Weight", r"\bweight\b"),
        ("BMI", r"\bbmi\b"),
    ]:
        if re.search(pattern, lower):
            names.append(name)
    event_request = (
        bool(
            re.search(
                r"admission|hospitali[sz]|procedure|surger|consultation|medication|prescription",
                lower,
            )
        )
        and not names
    )
    if not names and not event_request:
        if re.search(r"kidney|renal", lower):
            names = ["eGFR", "Urine ACR", "Creatinine"]
        else:
            names = ["HbA1c", "Fasting glucose"]
    years = [int(year) for year in re.findall(r"\b(?:19|20)\d{2}\b", question)]
    start = min(years) if years else None
    end = max(years) if len(years) > 1 else None
    past = re.search(r"(?:past|last)\s+(\d{1,2})\s*years?", lower)
    if past:
        start = date.today().year - int(past[1])
    series = []
    for item in available:
        if item["metric_name"] not in names:
            continue
        points = [
            point
            for point in item["points"]
            if (start is None or point["year"] >= start)
            and (end is None or point["year"] <= end)
            and point["citation"].get("source_verified")
        ]
        if points:
            series.append({**item, "points": points})
    journey = bool(re.search(r"journey|timeline|history", lower)) or event_request
    events = (
        [
            {
                "date": record["date"],
                "title": record["title"],
                "text": record["summary"],
                "citation": record.get("citation"),
            }
            for record in catalog["record_summaries"]
            if record.get("citation")
            and (
                not event_request
                or record["category"] == "other_history"
                or bool(
                    re.search(r"medication|prescription", lower)
                    and re.search(r"prescription|review", record["title"], re.IGNORECASE)
                )
            )
            and (start is None or int(record["date"][:4] or 0) >= start)
            and (end is None or int(record["date"][:4] or 9999) <= end)
        ]
        if journey
        else []
    )
    if not series and not events:
        return None
    dates = [point["date"] for item in series for point in item["points"]] + [
        event["date"] for event in events
    ]
    period = f"{min(dates)[:4]}–{max(dates)[:4]}" if dates else "Recorded history"
    title = (
        f"{'Clinical event timeline' if event_request else 'Diabetes journey'} · {period}"
        if journey
        else f"{', '.join(item['metric_name'] for item in series)} · {period}"
    )
    return {
        "artifact_id": new_id("CHT"),
        "session_id": session_id,
        "patient_id": patient_id,
        "title": title,
        "kind": "table"
        if re.search(r"\btable|tabular\b", lower)
        else "journey"
        if journey
        else "line",
        "series": series,
        "events": events,
        "created_at": now(),
        "question": question,
        "note": "Only dated values found in the original records are plotted. Lines connect documented observations; no missing values are estimated.",
    }


def chart_answer(artifact: dict) -> str:
    """Describe tool output from its verified data, including linked tables."""
    kind = "Table" if artifact["kind"] == "table" else "Chart"
    lines = [
        f"**{kind} created:** [{artifact['title']}](#chart-{artifact['artifact_id']})",
        "",
    ]
    if artifact["series"]:
        lines.extend(
            [
                "### Recorded measurements",
                "",
                "| Measurement | First documented value | Latest documented value | Observations |",
                "| --- | --- | --- | --- |",
            ]
        )
    for series in artifact["series"]:
        first, last = series["points"][0], series["points"][-1]
        lines.append(
            f"| **{series['metric_name']}** | **{first['value']:g} {first['unit']}** · {first['date']} [{first['citation_index']}] | **{last['value']:g} {last['unit']}** · {last['date']} [{last['citation_index']}] | {len(series['points'])} recorded measurements |"
        )
    if artifact["events"]:
        lines.extend(
            [
                "",
                "### Documented visits and clinical events",
                "",
                "| Record date | Record | Source |",
                "| --- | --- | --- |",
            ]
        )
        for event in artifact["events"]:
            lines.append(
                f"| {event['date']} | {event['title'].replace('|', '—')} | [{event['citation_index']}] |"
            )
    lines.extend(
        [
            "",
            "Select a chart point or a numbered citation to inspect its original source. Use **Show source data table** for every plotted value.",
        ]
    )
    return "\n".join(lines)


def run_chat_turn(
    store: WorkspaceStore, session: dict, question: str, previous: list[dict], progress
) -> dict:
    patient_id = session["patient_id"]
    progress("Reading patient records", "records")
    catalog = build_catalog(store, patient_id)
    cached = (
        store.db.briefs.find_one({"patient_id": patient_id}, {"brief.record_summaries": 1}) or {}
    )
    summaries = {
        record["record_id"]: record
        for record in cached.get("brief", {}).get("record_summaries", [])
    }
    for record in catalog["record_summaries"]:
        if record["record_id"] in summaries:
            record["summary"] = summaries[record["record_id"]]["summary"]
    wants_chart = chart_requested(question)
    hits = []
    if wants_chart:
        progress("Chart agent · reading verified OCR measurements", "retrieval")
    else:
        progress("RAG · retrieving evidence", "retrieval")
        retriever = retriever_for_patient(store, patient_id)
        hits = retriever.retrieve(question, patient_id=patient_id, top_k=8)
        if not retriever.dense_index.available:
            progress("RAG · source text retrieval (embeddings unavailable)", "retrieval")
    citations: list[dict] = []
    evidence = []
    seen = {}

    def add_source(citation: dict, text: str, record_date: str = "") -> int:
        key = (
            citation.get("document_id"),
            citation.get("page_number"),
            tuple(citation.get("bbox") or []),
        )
        if key in seen:
            return seen[key]
        citations.append(citation)
        index = len(citations)
        seen[key] = index
        evidence.append(
            f"[{index}] DOCUMENT DATE: {record_date or 'not supplied'} (not necessarily the event date) · {citation.get('document_title')} · page {citation.get('page_number')}: {text}"
        )
        return index

    # A record-level view preserves all visits; retrieval adds question-specific detail.
    for record in catalog["record_summaries"]:
        for item in record["evidence"][:2]:
            add_source(item["citation"], item["text"], record["date"])
    for hit in hits:
        citation = {
            "document_id": hit.metadata.get("document_id", ""),
            "document_title": hit.metadata.get("source_file", ""),
            "page_number": hit.metadata.get("page_number", 1),
            "bbox": hit.metadata.get("bbox", []),
            "snippet": hit.page_content[:550],
        }
        precise = locate_citation(store, patient_id, citation)
        citation["source_verified"] = precise is not None
        if precise:
            citation["bbox"] = precise
        add_source(citation, hit.page_content[:1000], str(hit.metadata.get("visit_date") or ""))

    artifacts = []
    if wants_chart:
        progress("Chart agent · verifying and plotting records", "chart")
        artifact = make_chart_artifact(catalog, question, session["session_id"], patient_id)
        if artifact:
            for item in artifact["series"]:
                for point in item["points"]:
                    point["citation_index"] = add_source(
                        point["citation"], point["citation"]["snippet"], point["date"]
                    )
            for event in artifact["events"]:
                event["citation_index"] = add_source(
                    event["citation"], event["text"], event["date"]
                )
            artifacts.append(artifact)

    progress(
        "Chart agent · preparing linked summary"
        if artifacts
        else "Clinical assistant · composing response",
        "synthesis",
    )
    model = None if wants_chart else LLMFactory.get_chat_model(max_tokens=1800)
    chart_context = ""
    if artifacts:
        artifact = artifacts[0]
        chart_context = (
            f"The chart tool has ALREADY CREATED the interactive chart '{artifact['title']}'. It contains "
            + "; ".join(
                f"{s['metric_name']}: {len(s['points'])} verified dated measurements"
                for s in artifact["series"]
            )
            + ". The UI will display it. Do not say you cannot create charts. Refer to this chart and briefly explain the recorded pattern without making a new diagnosis."
        )
    elif wants_chart:
        chart_context = "The chart tool found no supported dated data for this chart request. Explain the specific data gap; do not invent values."
    system = (
        "You are PrepPulse, helping a doctor review this patient's records. Use ONLY the numbered evidence. "
        "Write clear, concise clinical prose with Markdown headings, short bullets, and **bold key values and dates**. "
        "Use a Markdown table for multi-year comparisons (Date | Recorded finding | Source), not ASCII art. "
        "Cite EACH factual sentence or table row with [n] where n is an evidence number. Do not invent or renumber citations. "
        "Citation numbers are for the CURRENT evidence list; never reuse old conversation reference numbers without checking their current source. "
        "Lead with the answer, not demographics or disclaimers. Distinguish the document date from an event date mentioned within it. "
        "A DOCUMENT DATE labels the source only. Never turn a discharge/report date into an admission, symptom-onset, or diagnosis date. "
        "State an event date only when the excerpt explicitly gives it; otherwise say 'documented in the record dated ...' or omit the event date. "
        "Do not extrapolate diagnosis, treatment, or values. Mention actual record gaps only. "
        "Treat phrases such as 'where applicable' as templates, not confirmed patient history, unless a dedicated dated record corroborates them. "
        + chart_context
    )
    messages = [{"role": "system", "content": system}]
    for item in previous[-6:]:
        messages.append({"role": item["role"], "content": item.get("text", "")[:4000]})
    messages.append(
        {
            "role": "user",
            "content": "PATIENT EVIDENCE:\n"
            + "\n".join(evidence)
            + "\n\nDOCTOR REQUEST:\n"
            + question,
        }
    )
    if artifacts:
        answer = chart_answer(artifacts[0])
    elif wants_chart and cardiac_chart_requested(question):
        answer = (
            "### Chart scope warning\n\n"
            "**Heart-disease charts are outside the current diabetes agent's scope.** "
            "I can only generate charts from these supported OCR measurements: **"
            + SUPPORTED_CHARTS
            + "**. Ask for one of these measurements by name.\n\n"
            "You can still ask for a cited text summary of the documented cardiac records. "
            "No cardiac chart has been generated."
        )
    elif wants_chart:
        answer = (
            "### Chart data unavailable\n\nNo supported, dated measurements match this chart request. No values were invented.\n\n**Available measurements:** "
            + ", ".join(item["metric_name"] for item in catalog["metric_series"])
            + ".\n\n**Supported chart scope:** "
            + SUPPORTED_CHARTS
            + "."
        )
    elif isinstance(model, MockClinicalChatModel):
        answer = "### Documented evidence\n\n" + "\n\n".join(
            f"- {entry}" for entry in evidence[:10]
        )
    else:
        try:
            answer = str(model.invoke(messages).content).strip()
        except Exception:  # noqa: BLE001 - a local model outage must still return inspectable evidence
            progress("Assistant · preparing source excerpts", "fallback")
            answer = (
                "### Documented source excerpts\n\nThe local synthesis model did not respond. These are retrieved record excerpts, with links to inspect the originals.\n\n"
                + "\n\n".join(f"- {entry}" for entry in evidence[-8:])
            )
    # Accept only source numbers supplied in this turn. Invalid references cannot become links.
    answer = re.sub(
        r"\[(\d+)\]",
        lambda match: match[0] if 1 <= int(match[1]) <= len(citations) else "[source unavailable]",
        answer,
    )
    source_requested = (
        bool(
            re.search(
                r"\b(show|open|view|display|inspect|see)\b.{0,45}\b(source|proof|original|evidence)\b|\bsource proof\b",
                question,
                re.IGNORECASE,
            )
        )
        and not artifacts
    )
    source_index = next(
        (
            index + 1
            for index, source in enumerate(citations)
            if hits
            and source["document_id"] == hits[0].metadata.get("document_id")
            and source["page_number"] == hits[0].metadata.get("page_number")
        ),
        1,
    )
    return {
        "message_id": new_id("MSG"),
        "role": "assistant",
        "text": answer,
        "citations": citations,
        "artifact_ids": [artifact["artifact_id"] for artifact in artifacts],
        "artifacts": artifacts,
        "created_at": now(),
        "presentation": {
            "show_chart": bool(artifacts),
            "show_source": source_requested,
            "source_index": source_index,
        },
    }
