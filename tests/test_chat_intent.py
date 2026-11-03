from datetime import date

import pytest
from test_ui_api import seed_chat_patient
from test_ui_api import workspace as workspace_fixture  # noqa: F401

from preppulse_api.chart_intent import chart_requested, chart_window, resolve_chart_question
from preppulse_api.chat_service import make_chart_artifact, run_chat_turn
from preppulse_api.evidence_catalog import build_catalog


@pytest.fixture
def workspace(workspace_fixture):  # noqa: F811
    return workspace_fixture


@pytest.mark.parametrize(
    "question",
    [
        "Can you generate me the charts for this patient?",
        "Show graphs for this patient's values",
        "Plot it for me",
        "Visualize HbA1c",
        "Visualise fasting glucose for two years",
        "Show HbA1c plots for the last 3 yrs",
        "Draw a graph of blood sugar",
    ],
)
def test_visual_requests_always_use_chart_tool_without_a_model(workspace, monkeypatch, question):
    seed_chat_patient(workspace)
    workspace.db.patient_documents.update_one(
        {"document_id": "DOC-CHAT"},
        {
            "$push": {
                "stage_1_raw_ocr.pages.0.tokens": {
                    "$each": [
                        {"text": "Fasting glucose", "bbox": [100, 300, 280, 312]},
                        {"text": "142", "bbox": [400, 300, 440, 312]},
                        {"text": "mg/dL", "bbox": [800, 300, 850, 312]},
                    ]
                }
            }
        },
    )
    import preppulse_api.chat_service as service

    def forbidden(*args, **kwargs):
        raise AssertionError("A chart request must not depend on text/embedding services")

    monkeypatch.setattr(service, "retriever_for_patient", forbidden)
    monkeypatch.setattr(service.LLMFactory, "get_chat_model", forbidden)
    result = run_chat_turn(
        workspace,
        {"patient_id": "PRP-CHAT", "session_id": "CHAT-1"},
        question,
        [],
        lambda *args: None,
    )
    assert result["artifacts"]
    assert result["presentation"]["show_chart"] is True
    assert result["artifacts"][0]["series"][0]["points"][0]["value"] in {7.2, 142}


@pytest.mark.parametrize("years", range(1, 11))
def test_one_to_ten_year_windows_are_exact(years):
    start, end = chart_window(f"Plot blood sugar for the past {years} years", date(2026, 11, 3))
    assert start == f"{2026 - years}-11-03"
    assert end == "2026-11-03"


def test_word_windows_explicit_years_and_followup_context():
    assert chart_window("last three years", date(2026, 11, 3))[0] == "2023-11-03"
    assert chart_window("HbA1c between 2020 and 2023") == ("2020-01-01", "2023-12-31")
    previous = [{"role": "user", "text": "Summarize fasting glucose from 2016 to 2026"}]
    assert "Fasting glucose" in resolve_chart_question("Plot it for the last two years", previous)
    assert "2016" not in resolve_chart_question("Plot it for the last two years", previous)
    for duration in (0, 11, 100):
        with pytest.raises(ValueError, match="1 to 10"):
            chart_window(f"Chart for {duration} years")
    assert not chart_requested("No charts, summarize HbA1c only")
    assert not chart_requested("Don't generate a chart, just summarize HbA1c")


def test_window_excludes_older_values_instead_of_relabelling_whole_history(workspace):
    seed_chat_patient(workspace)
    catalog = build_catalog(workspace, "PRP-CHAT")
    assert make_chart_artifact(catalog, "Plot HbA1c in 2024", "CHAT-1", "PRP-CHAT") is None
    assert make_chart_artifact(catalog, "Plot HbA1c in 2025", "CHAT-1", "PRP-CHAT")["series"]


def test_unsupported_chart_returns_owned_source_table_and_no_unrelated_plot(workspace):
    seed_chat_patient(workspace)
    row = {"text": "Cardiac review: ECG normal", "bbox": [100, 250, 800, 265]}
    workspace.db.patient_documents.update_one(
        {"document_id": "DOC-CHAT"}, {"$push": {"stage_1_raw_ocr.pages.0.tokens": row}}
    )
    result = run_chat_turn(
        workspace,
        {"patient_id": "PRP-CHAT", "session_id": "CHAT-1"},
        "Generate charts for heart disease",
        [],
        lambda *args: None,
    )
    assert result["artifacts"] == []
    assert "Chart scope warning" in result["text"]
    assert "Cardiac review: ECG normal" in result["text"]
    assert "| Source record date |" in result["text"]
    assert all(c["document_id"] == "DOC-CHAT" for c in result["citations"])


def test_information_reply_offers_chart_without_creating_one(workspace, monkeypatch):
    seed_chat_patient(workspace)
    import preppulse_api.chat_service as service
    from preppulse_rag.llm_provider import MockClinicalChatModel

    class Retriever:
        class dense_index:
            available = False

        def retrieve(self, *args, **kwargs):
            return []

    monkeypatch.setattr(service, "retriever_for_patient", lambda *args: Retriever())
    monkeypatch.setattr(
        service.LLMFactory, "get_chat_model", lambda **kwargs: MockClinicalChatModel()
    )
    session = {"patient_id": "PRP-CHAT", "session_id": "CHAT-1"}
    result = run_chat_turn(workspace, session, "Summarize HbA1c", [], lambda *args: None)
    assert not result["artifacts"]
    assert "Would you like a chart" in result["text"]
    result = run_chat_turn(workspace, session, "No charts, summarize HbA1c", [], lambda *args: None)
    assert "Would you like a chart" not in result["text"]


def test_table_for_other_condition_does_not_claim_a_chart_was_requested(workspace):
    seed_chat_patient(workspace)
    result = run_chat_turn(
        workspace,
        {"patient_id": "PRP-CHAT", "session_id": "CHAT-1"},
        "Show heart records as a table",
        [],
        lambda *args: None,
    )
    assert not result["artifacts"]
    assert "Chart scope warning" not in result["text"]
