import pytest
from langchain_core.documents import Document

from preppulse_agents.graph import create_clinical_review_workflow
from preppulse_agents.schemas import ConsultationBrief
from preppulse_rag.retriever import HybridEnsembleRetriever

# ---------- test fixtures ----------


@pytest.fixture
def mock_patient_chart() -> list[Document]:
    # Documents simulating a diabetic patient chart with lab reports and prescriptions
    return [
        Document(
            page_content="Glycaemic Panel\nHbA1c: 8.4 % HIGH\nFasting Blood Glucose: 142 mg/dL HIGH",
            metadata={
                "patient_id": "patient_meera",
                "document_id": "lab_01",
                "source_file": "Lab report - 14 Mar 2024",
                "visit_date": "2024-03-14",
                "page_number": 2,
                "bbox": [100, 200, 500, 260],
            },
        ),
        Document(
            page_content="Renal Function Profile\neGFR: 68 mL/min/1.73m² (Normal: > 60)\nUrine ACR albumin creatinine ratio: 42 mg/g",
            metadata={
                "patient_id": "patient_meera",
                "document_id": "lab_02",
                "source_file": "Lab report - 14 Mar 2024",
                "visit_date": "2024-03-14",
                "page_number": 2,
                "bbox": [590, 94, 656, 906],
            },
        ),
        Document(
            page_content="Clinic prescription slip: Glargine insulin 14U at bedtime. Empagliflozin 10mg once daily.",
            metadata={
                "patient_id": "patient_meera",
                "document_id": "rx_01",
                "source_file": "Clinic Slip - 14 Mar 2024",
                "visit_date": "2024-03-14",
                "page_number": 1,
                "bbox": [80, 210, 400, 230],
            },
        ),
        Document(
            page_content="Hospital discharge summary: Glargine insulin 20U subcutaneous daily. Follow up in 4 weeks.",
            metadata={
                "patient_id": "patient_meera",
                "document_id": "dc_01",
                "source_file": "Hospital Discharge - 01 Mar 2024",
                "visit_date": "2024-03-01",
                "page_number": 1,
                "bbox": [150, 400, 500, 430],
            },
        ),
    ]


# ---------- tests ----------


def test_langgraph_clinical_review_workflow(mock_patient_chart: list[Document]):
    # Verifies end-to-end execution of LangGraph review workflow and ConsultationBrief generation
    retriever = HybridEnsembleRetriever(mock_patient_chart)
    workflow = create_clinical_review_workflow()

    initial_state = {
        "patient_id": "patient_meera",
        "patient_name": "Meera Joshi",
        "mrn": "DB-4091",
        "age_sex": "62 years / Female",
        "diabetes_type": "Type 2 diabetes",
        "retriever": retriever,
        "trajectory": None,
        "care_gaps": None,
        "mismatches": None,
        "caregiver_prep": None,
        "final_brief": None,
    }

    final_state = workflow.invoke(initial_state)

    brief: ConsultationBrief = final_state["final_brief"]
    assert brief is not None
    assert brief.patient_name == "Meera Joshi"
    assert brief.mrn == "DB-4091"

    # 1. Verify Metabolic Trajectory (Category 1)
    kpis = brief.trajectory.kpis
    assert len(kpis) >= 2
    hba1c_kpi = next((k for k in kpis if k.name == "HbA1c"), None)
    assert hba1c_kpi is not None
    assert "8.4%" in hba1c_kpi.value
    # Citation bounding box must be valid [0, 1000]
    assert hba1c_kpi.citation is not None
    bbox = hba1c_kpi.citation.bbox
    assert len(bbox) == 4
    assert all(0 <= coord <= 1000 for coord in bbox)

    # 2. Verify Care Gaps (Category 2)
    assert len(brief.care_gaps.items) >= 1
    foot_gap = next((g for g in brief.care_gaps.items if "foot" in g.title.lower()), None)
    assert foot_gap is not None

    # 3. Verify Record Mismatches (Category 3)
    assert len(brief.mismatches.items) >= 1
    insulin_mismatch = next((m for m in brief.mismatches.items if "insulin" in m.title.lower()), None)
    assert insulin_mismatch is not None
    assert insulin_mismatch.source_a_citation is not None
    assert insulin_mismatch.source_b_citation is not None

    # 4. Verify Caregiver Prep (Category 4 with bilingual support)
    checklist = brief.caregiver_prep.checklist
    assert len(checklist) >= 3
    # Check that both English and Hindi strings exist
    for item in checklist:
        assert len(item.text_en) > 0
        assert len(item.text_hi) > 0

