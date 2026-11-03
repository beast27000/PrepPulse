import pytest
from test_caregiver_workflow import setup_people, start_and_save
from test_ui_api import workspace as workspace_fixture  # noqa: F401

from preppulse_api.care import care_suggestions


@pytest.fixture
def workspace(workspace_fixture):  # noqa: F811
    return workspace_fixture


def test_visit_checkboxes_persist_without_changing_translations_or_caregiver_reports(workspace):
    _, _, doctor, dh, caregiver, ch, patient, _ = setup_people(workspace)
    visit, draft = start_and_save(doctor, dh, patient)
    url = f"/api/care/visits/{visit['visit_id']}/checks/check-1"
    assert doctor.put(url, json={"completed": True}, headers=dh).status_code == 200
    saved = doctor.get(f"/api/care/patients/{patient['patient_id']}").json()["draft"]
    assert saved["checks"] == {"check-1": True}
    assert saved["revision"] == draft["revision"]
    assert saved["translation_status"] == draft["translation_status"]
    assert workspace.db.care_reports.count_documents({}) == 0
    assert caregiver.put(url, json={"completed": True}, headers=ch).status_code == 403
    assert (
        doctor.put(
            url.replace("check-1", "wrong"), json={"completed": True}, headers=dh
        ).status_code
        == 404
    )
    assert doctor.put(url, json={"completed": False}, headers=dh).status_code == 200
    assert (
        doctor.get(f"/api/care/patients/{patient['patient_id']}").json()["draft"]["checks"][
            "check-1"
        ]
        is False
    )


def test_preparation_fallback_uses_everyday_actions_instead_of_raw_clinical_findings(workspace):
    workspace.db.briefs.insert_one(
        {
            "patient_id": "PRP-PLAIN",
            "brief": {
                "caregiver_prep": {
                    "checklist": [
                        {
                            "text_en": "Review the documented finding with the clinician: eGFR: 90 mL/min/1.73m²"
                        }
                    ]
                },
                "priority_findings": [
                    {
                        "title": "discharge acute gastroenteritis with dehydration",
                        "citation": {"source_verified": True},
                    }
                ],
            },
        }
    )
    items = care_suggestions(workspace, "PRP-PLAIN")
    text = " ".join(x["text_en"] for x in items)
    assert "Bring earlier test reports" in text
    assert "new or returning symptoms" in text
    assert "eGFR" not in text
    assert "gastroenteritis" not in text
    assert "constantly" not in text


def test_caregiver_prompt_receives_dated_context_without_ordering_new_monitoring(monkeypatch):
    from langchain_core.messages import AIMessage

    from preppulse_agents.graph import caregiver_prep_agent
    from preppulse_agents.schemas import LongitudinalMetricSeries, TimeSeriesPoint
    from preppulse_rag.llm_provider import LLMFactory

    messages = []

    class Model:
        def invoke(self, supplied):
            messages.extend(supplied)
            return AIMessage(content='[{"text_en":"Bring earlier test reports to the visit."}]')

    class Retriever:
        def retrieve(self, *args, **kwargs):
            return []

    monkeypatch.setattr(LLMFactory, "get_chat_model", lambda **kwargs: Model())
    result = caregiver_prep_agent(
        {
            "patient_id": "PRP-CONTEXT",
            "retriever": Retriever(),
            "metric_series": [
                LongitudinalMetricSeries(
                    metric_name="HbA1c",
                    points=[
                        TimeSeriesPoint(date="2024-01-01", year=2024, value=7.2, unit="%"),
                        TimeSeriesPoint(date="2025-01-01", year=2025, value=7.9, unit="%"),
                    ],
                )
            ],
        }
    )
    assert "2024-01-01: 7.2" in messages[1]["content"]
    assert "2025-01-01: 7.9" in messages[1]["content"]
    assert "Do not instruct new testing, constant monitoring" in messages[0]["content"]
    assert (
        result["caregiver_prep"].checklist[0].text_en == "Bring earlier test reports to the visit."
    )
