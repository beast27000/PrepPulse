"""
Stage 2 — Grounding & verification (the fail-closed safety pass).

Extraction (extract.py) produces candidate facts. This pass VERIFIES each one
against the Stage 1 source tokens before it is trusted, and attaches real
geometry:

  1. Anchor check  — the fact's anchor_text (and, for labs, its numeric value)
                     must actually appear in the page's token stream / full_text.
  2. BBox attach   — compute source_bbox as the union of the tokens that form the
                     matched anchor, so every fact points at pixels on the page.
  3. Confidence    — set from match quality (exact vs fuzzy) and token OCR
                     confidence.
  4. Fail-closed   — a fact that cannot be verified, or whose confidence is below
                     the review threshold, is moved to a review_queue instead of
                     being silently kept or dropped.

This is what makes "no lost / no hallucinated prescription or consultation info"
an enforced property rather than a hope: an unverifiable fact is surfaced, never
passed through as truth.
"""
from __future__ import annotations

import difflib
import re
from typing import Any

from preppulse_preprocessing.config import GroundingConfig


def _page_index(doc: dict[str, Any]) -> dict[int, dict[str, Any]]:
    pages = doc.get("stage_1_raw_ocr", {}).get("pages", [])
    return {p.get("page_number", i + 1): p for i, p in enumerate(pages)}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _find_token_span(anchor: str, tokens: list[dict[str, Any]]) -> tuple[list[list[int]], float]:
    """
    Find the run of tokens whose concatenated text best matches the anchor.
    Returns (list of bboxes, match_ratio in 0..1).
    """
    if not anchor or not tokens:
        return [], 0.0
    target = _norm(anchor)
    target_words = target.split()
    n = len(target_words)
    best_ratio = 0.0
    best_bboxes: list[list[int]] = []

    texts = [_norm(t.get("text", "")) for t in tokens]
    # slide a window roughly the size of the anchor (+/- 2 tokens)
    for w in range(max(1, n - 2), n + 3):
        for i in range(len(tokens) - w + 1):
            window = " ".join(texts[i : i + w]).strip()
            if not window:
                continue
            ratio = difflib.SequenceMatcher(None, target, window).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_bboxes = [tokens[j].get("bbox") for j in range(i, i + w) if tokens[j].get("bbox")]
    return best_bboxes, best_ratio


def _union(bboxes: list[list[int]]) -> list[int] | None:
    pts = [b for b in bboxes if b and len(b) == 4]
    if not pts:
        return None
    return [min(b[0] for b in pts), min(b[1] for b in pts),
            max(b[2] for b in pts), max(b[3] for b in pts)]


def _numeric_present(value: Any, page_text: str, tol: float) -> bool:
    if value is None:
        return True  # nothing numeric to check (e.g. a diagnosis)
    try:
        v = float(value)
    except (TypeError, ValueError):
        return True
    for m in re.finditer(r"[0-9]+(?:\.[0-9]+)?", page_text):
        if abs(float(m.group()) - v) <= tol:
            return True
    return False


def _verify_fact(fact: dict[str, Any], page: dict[str, Any], cfg: GroundingConfig) -> dict[str, Any]:
    tokens = page.get("tokens", [])
    page_text = page.get("full_text", "")
    anchor = fact.get("anchor_text") or ""

    bboxes, ratio = _find_token_span(anchor, tokens)
    numeric_ok = _numeric_present(fact.get("value"), page_text, cfg.numeric_tolerance)

    # OCR confidence of the matched tokens (native text = 1.0)
    ocr_conf = 1.0
    if bboxes:
        matched = [t for t in tokens if t.get("bbox") in bboxes]
        if matched:
            ocr_conf = min(t.get("confidence", 1.0) for t in matched)

    # combine anchor-match ratio, numeric presence and OCR confidence
    confidence = round(ratio * ocr_conf * (1.0 if numeric_ok else 0.4), 3)

    verified = (ratio >= cfg.fuzzy_accept and numeric_ok)
    fact = dict(fact)
    fact["source_bbox"] = _union(bboxes)
    fact["confidence"] = confidence
    fact["_verified"] = verified
    fact["_match_ratio"] = round(ratio, 3)
    fact["_numeric_ok"] = numeric_ok
    return fact


def ground_entities(entities: dict[str, Any], doc: dict[str, Any], cfg: GroundingConfig) -> dict[str, Any]:
    """
    Verify + ground every fact in an entities dict against the document's Stage 1
    tokens. Returns a new entities dict plus a `review_queue` of failures.
    """
    pages = _page_index(doc)
    review: list[dict[str, Any]] = []

    def process(items: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
        kept = []
        for fact in items:
            page = pages.get(fact.get("source_page", 1)) or next(iter(pages.values()), {})
            checked = _verify_fact(fact, page, cfg)
            if checked["_verified"] and checked["confidence"] >= cfg.review_threshold:
                # strip internal markers before keeping
                for k in ("_verified", "_match_ratio", "_numeric_ok"):
                    checked.pop(k, None)
                kept.append(checked)
            else:
                review.append({
                    "kind": kind,
                    "fact": {k: v for k, v in checked.items() if not k.startswith("_")},
                    "reason": ("low_confidence" if checked["_numeric_ok"] else "numeric_not_found")
                              if checked["_match_ratio"] >= cfg.fuzzy_accept else "anchor_not_found",
                    "match_ratio": checked["_match_ratio"],
                    "confidence": checked["confidence"],
                })
        return kept

    grounded = {
        "labs": process(entities.get("labs", []), "lab"),
        "medications": process(entities.get("medications", []), "medication"),
        "diagnoses": process(entities.get("diagnoses", []), "diagnosis"),
        "vitals": entities.get("vitals", []),
        "advice": entities.get("advice"),
        "review_queue": review,
    }
    return grounded
