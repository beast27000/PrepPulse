from __future__ import annotations

import re

from langchain_core.tools import Tool

from preppulse_agents.schemas import (
    LongitudinalMetricSeries,
    SourceProofCitation,
    TimeSeriesPoint,
)
from preppulse_rag.retriever import HybridEnsembleRetriever


def extract_metric_timeseries(
    metric_name: str,
    retriever: HybridEnsembleRetriever,
    patient_id: str | None = None,
    category: str = "glycemic",
    value_regex: str | None = None,
    unit: str = "",
) -> LongitudinalMetricSeries | None:
    # Dynamically queries retriever for any named laboratory metric across up to 10 years
    hits = retriever.retrieve(metric_name, patient_id=patient_id, top_k=8)
    if not hits:
        return None

    points: list[TimeSeriesPoint] = []
    tabular: dict[str, float | None] = {}
    seen_dates: set[str] = set()

    default_regex = value_regex or r"(\d+\.?\d*)\s*(?:%|mg/dL|g/dL|mL/min|U/L|mmol/L)?"

    for hit in hits:
        content = hit.page_content
        content_lower = content.lower()

        # Ensure the hit actually references the requested metric or relevant lab context
        metric_lower = metric_name.lower()
        if metric_lower == "hba1c":
            if "hba1c" not in content_lower and "a1c" not in content_lower and "%" not in content:
                continue
            match = re.search(r"(?:hba1c|a1c)[^\d]*(\d+\.?\d*)", content, re.IGNORECASE) or re.search(r"(\d+\.?\d*)\s*%", content)
        elif "glucose" in metric_lower:
            if "glucose" not in content_lower and "fpg" not in content_lower and "fbg" not in content_lower:
                continue
            match = re.search(r"(?:glucose|fasting|fpg|fbg)[^\d]*(\d{2,3})", content, re.IGNORECASE)
        elif "egfr" in metric_lower:
            if "egfr" not in content_lower and "gfr" not in content_lower:
                continue
            match = re.search(r"(?:egfr|gfr)[^\d]*(\d+)", content, re.IGNORECASE)
        elif value_regex:
            match = re.search(value_regex, content)
        else:
            if metric_lower not in content_lower:
                continue
            match = re.search(rf"{re.escape(metric_name)}[^\d]*(\d+\.?\d*)", content, re.IGNORECASE) or re.search(default_regex, content)

        if not match:
            continue
        try:
            val = float(match.group(1))
        except (ValueError, TypeError):
            continue

        year = hit.metadata.get("year")
        date_str = str(hit.metadata.get("visit_date") or (f"{year}-01-01" if year else ""))
        if not date_str or date_str in seen_dates:
            continue
        seen_dates.add(date_str)

        resolved_year = year or (int(date_str[:4]) if len(date_str) >= 4 and date_str[:4].isdigit() else 2024)

        cit = SourceProofCitation(
            document_id=hit.metadata.get("document_id", ""),
            document_title=hit.metadata.get("source_file", "Lab Report"),
            date_formatted=date_str,
            page_number=hit.metadata.get("page_number", 1),
            bbox=hit.metadata.get("bbox", [100, 200, 300, 250]),
            extracted_text=content[:120],
        )

        status = "normal"
        if metric_name.lower() in ("hba1c", "glycemic panel") and val >= 5.7 or metric_name.lower() in ("fasting glucose", "glucose") and val >= 100:
            status = "high"

        points.append(
            TimeSeriesPoint(
                date=date_str,
                year=resolved_year,
                value=val,
                unit=unit,
                status=status,
                citation=cit,
            )
        )
        tabular[str(resolved_year)] = val

    if not points:
        return None

    points.sort(key=lambda p: p.date)
    trend = "stable"
    if len(points) > 1:
        if points[-1].value > points[0].value:
            trend = "worsening" if category == "glycemic" else "elevated"
        elif points[-1].value < points[0].value:
            trend = "improving"

    return LongitudinalMetricSeries(
        metric_name=metric_name,
        category=category,
        points=points,
        ten_year_trend=trend,
        tabular_flow=tabular,
    )


def build_clinical_toolset(
    retriever: HybridEnsembleRetriever,
    patient_id: str | None = None,
) -> list[Tool]:
    # Builds a suite of LangChain Tools for agent workflows
    def _search_chart(query: str) -> str:
        hits = retriever.retrieve(query, patient_id=patient_id, top_k=5)
        if not hits:
            return "No matching clinical documentation found."
        formatted = []
        for h in hits:
            src = h.metadata.get("source_file", "Document")
            date = h.metadata.get("visit_date") or h.metadata.get("year", "")
            page = h.metadata.get("page_number", 1)
            formatted.append(f"[{src} p.{page} date:{date}]: {h.page_content}")
        return "\n\n".join(formatted)

    def _chart_metric(metric_name: str) -> str:
        series = extract_metric_timeseries(metric_name, retriever, patient_id=patient_id)
        if not series or not series.points:
            return f"No documented data points found for '{metric_name}'."
        pts_str = ", ".join(f"{p.date}: {p.value} {p.unit}" for p in series.points)
        return f"Metric: {series.metric_name} | Trend: {series.ten_year_trend} | Points: [{pts_str}]"

    tools = [
        Tool(
            name="clinical_chart_retriever",
            description="Searches patient clinical notes, lab reports, discharge summaries, and prescriptions.",
            func=_search_chart,
        ),
        Tool(
            name="metric_timeseries_tool",
            description="Extracts multi-year longitudinal measurements and trend for any given laboratory analyte name.",
            func=_chart_metric,
        ),
    ]
    return tools
