"""Deterministic chart routing; the language model never supplies plotted values."""

import re
from datetime import date

VISUAL_WORDS = r"charts?|graphs?|plots?|plotted|plotting|visuali[sz]\w*|timelines?"
CHART_WORDS = VISUAL_WORDS + r"|tabular|tables?"
METRIC_PATTERNS = (
    ("HbA1c", r"\bhba1c\b|\ba1c\b|glycated ha?emoglobin"),
    ("Fasting glucose", r"fasting|\bfpg\b|\bfbs\b"),
    ("Post-meal glucose", r"post.meal|postprandial|\bppbs\b"),
    ("eGFR", r"\begfr\b"),
    ("Urine ACR", r"\bu?acr\b|albumin"),
    ("Creatinine", r"creatinine"),
    ("LDL cholesterol", r"\bldl\b|cholesterol"),
    ("Systolic BP", r"blood pressure|\bbp\b|systolic"),
    ("Diastolic BP", r"blood pressure|\bbp\b|diastolic"),
)
SUPPORTED_NAMES = {name for name, _ in METRIC_PATTERNS}
CARDIAC = r"\b(heart|cardiac|coronary|cardiovascular|cardiology|ejection|lvef|troponin|ecg|ekg|echocardiogram|echocardiography)\b"
OTHER_UNSUPPORTED = r"\b(hdl|triglycerides?|thyroid|tsh|t3|t4|liver|alt|ast|cancer|tumou?r|weight|bmi|sodium|potassium|ha?emoglobin|blood count|platelets?|oxygen|spo2)\b"
EVENTS = r"admission|hospitali[sz]|procedure|surger|consultation|medication|prescription"
NUMBERS = {
    word: i
    for i, word in enumerate(
        ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten")
    )
}
DURATION = (
    r"\b(\d{1,3}|zero|one|two|three|four|five|six|seven|eight|nine|ten)[ -]*(?:years?|yrs?)\b"
)
NO_CHART = r"\b(?:no|without)\s+(?:a\s+|any\s+)?(?:charts?|graphs?|plots?)\b|\b(?:do not|don't)\s+(?:(?:show|make|generate|draw)\s+)?(?:a\s+|any\s+)?(?:charts?|graphs?|plot|visuali[sz]\w*)\b"


def chart_requested(question: str) -> bool:
    return bool(re.search(rf"\b(?:{CHART_WORDS})\b", question, re.IGNORECASE)) and not bool(
        re.search(NO_CHART, question, re.IGNORECASE)
    )


def metric_names(question: str) -> list[str]:
    names = [
        name for name, pattern in METRIC_PATTERNS if re.search(pattern, question, re.IGNORECASE)
    ]
    if re.search(r"glucose|blood sugars?|glyc[ae]mi", question, re.IGNORECASE) and not any(
        "glucose" in name for name in names
    ):
        names.extend(["Fasting glucose", "Post-meal glucose"])
    if not names and re.search(r"kidney|renal", question, re.IGNORECASE):
        names = ["eGFR", "Urine ACR", "Creatinine"]
    return names


def cardiac_chart_requested(question: str) -> bool:
    return bool(re.search(CARDIAC, question, re.IGNORECASE))


def unsupported_chart_requested(question: str) -> bool:
    # "Glycated haemoglobin" names HbA1c, rather than a general blood-count chart.
    without_a1c = re.sub(r"glycated ha?emoglobin", "HbA1c", question, flags=re.IGNORECASE)
    if cardiac_chart_requested(question) or re.search(
        OTHER_UNSUPPORTED, without_a1c, re.IGNORECASE
    ):
        return True
    if metric_names(question) or re.search(r"diabet|metabolic|" + EVENTS, question, re.IGNORECASE):
        return False
    # Generic "generate charts for this patient" is valid; an unknown target is not
    # permission to substitute an unrelated HbA1c chart.
    allowed = {
        "can",
        "could",
        "would",
        "will",
        "you",
        "please",
        "pls",
        "kindly",
        "generate",
        "generated",
        "make",
        "draw",
        "show",
        "display",
        "give",
        "me",
        "us",
        "the",
        "a",
        "an",
        "some",
        "all",
        "any",
        "this",
        "that",
        "these",
        "those",
        "patient",
        "patients",
        "for",
        "of",
        "to",
        "and",
        "his",
        "her",
        "their",
        "record",
        "records",
        "values",
        "data",
        "measurements",
        "report",
        "reports",
        "trend",
        "trends",
        "over",
        "past",
        "last",
        "previous",
        "most",
        "recent",
        "year",
        "years",
        "yr",
        "yrs",
        "from",
        "between",
        "since",
        "until",
        "till",
        "through",
        "now",
        "in",
        "as",
        "on",
        "by",
        "at",
        "it",
        "them",
        "with",
        "chart",
        "charts",
        "graph",
        "graphs",
        "plot",
        "plots",
        "plotted",
        "plotting",
        "visualize",
        "visualise",
        "visualization",
        "visualisation",
        "timeline",
        "timelines",
        "table",
        "tables",
        "tabular",
        "diabetes",
        "diabetic",
        "journey",
        "history",
        "metabolic",
    } | set(NUMBERS)
    allowed |= {
        "s",
        "period",
        "periods",
        "across",
        "throughout",
        "covering",
        "using",
        "available",
        "about",
        "line",
        "interactive",
        "again",
        "also",
        "i",
        "get",
        "need",
        "want",
        "relevant",
        "important",
        "medical",
        "clinical",
        "hey",
    }
    return any(word not in allowed for word in re.findall(r"[a-z]+", question.lower()))


def resolve_chart_question(question: str, previous: list[dict]) -> str:
    """Resolve a short chart follow-up from the last relevant USER topic, never old citations."""
    if metric_names(question) or unsupported_chart_requested(question):
        return question
    if re.search(r"diabet|metabolic|" + EVENTS, question, re.IGNORECASE):
        return question
    for entry in reversed(previous):
        text = entry.get("text", "")
        if entry.get("role") != "user" or text.strip() == question.strip():
            continue
        names = metric_names(text)
        if cardiac_chart_requested(text) or re.search(OTHER_UNSUPPORTED, text, re.IGNORECASE):
            # Preserve the topic, but do not import arbitrary old numbers as dates.
            topic = re.search(CARDIAC + "|" + OTHER_UNSUPPORTED, text, re.IGNORECASE)[0]
        elif names:
            topic = ", ".join(names)
        elif re.search(r"diabet|metabolic", text, re.IGNORECASE):
            topic = "diabetes"
        else:
            continue
        if not re.search(DURATION + r"|\b(?:19|20)\d{2}\b", question, re.IGNORECASE):
            duration = re.search(DURATION, text, re.IGNORECASE)
            years = re.findall(r"\b(?:19|20)\d{2}\b", text)
            if duration:
                topic += " over the past " + duration[0]
            elif years:
                topic += " from " + " to ".join(years[:2])
        return question + " · " + topic
    return question


def chart_window(question: str, today: date | None = None) -> tuple[str | None, str | None]:
    today = today or date.today()
    duration = re.search(DURATION, question, re.IGNORECASE)
    if duration:
        token = duration[1].lower()
        years = NUMBERS[token] if token in NUMBERS else int(token)
        if not 1 <= years <= 10:
            raise ValueError(
                "Choose a chart window from 1 to 10 years, or give explicit calendar years."
            )
        try:
            start = today.replace(year=today.year - years)
        except ValueError:
            start = today.replace(year=today.year - years, day=28)
        return start.isoformat(), today.isoformat()
    years = [int(y) for y in re.findall(r"\b(?:19|20)\d{2}\b", question)]
    if years:
        return f"{min(years):04d}-01-01", (
            today.isoformat()
            if len(years) == 1 and re.search(r"since", question, re.IGNORECASE)
            else f"{max(years):04d}-12-31"
        )
    return None, None


def chart_offer(question: str) -> bool:
    return not re.search(NO_CHART, question, re.IGNORECASE) and bool(
        metric_names(question) or re.search(r"diabet", question, re.IGNORECASE)
    )
