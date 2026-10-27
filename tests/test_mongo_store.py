import pytest

from preppulse_db.mongo_store import MongoStore
from preppulse_db.schemas import (
    DocumentChunk,
    LabEntity,
    MedicationEntity,
    PageRecord,
    PatientDocument,
    Stage1RawOcr,
    Stage2StructuredEntities,
    TableRecord,
    TokenRecord,
)

# ---------- fixtures ----------


@pytest.fixture
def test_store():
    # Provides an isolated MongoStore using test database
    store = MongoStore(uri="mongodb://localhost:27017", db_name="preppulse_test")
    try:
        store.connect()
        store.clear_database()
        yield store
    finally:
        store.clear_database()
        store.close()


# ---------- tests ----------


def test_write_and_read_stage1_document(test_store: MongoStore):
    # Verifies Stage 1 compound document persistence and bounding box integrity
    page = PageRecord(
        page_number=1,
        extraction_method="native_pdf",
        full_text="HbA1c: 7.2 %",
        tokens=[
            TokenRecord(text="HbA1c:", bbox=[120, 340, 180, 360], confidence=1.0, source="native"),
            TokenRecord(text="7.2", bbox=[190, 340, 220, 360], confidence=1.0, source="native"),
        ],
        tables=[TableRecord(table_id=0, rows=[["Test", "Result"], ["HbA1c", "7.2"]], bbox=[50, 300, 600, 500])],
    )
    doc = PatientDocument(
        document_id="TEST_DOC_001",
        patient_id="PATIENT_01",
        visit_date="2024-03-15",
        document_type="lab_report",
        source_file="test_lab.pdf",
        stage_1_raw_ocr=Stage1RawOcr(page_count=1, pages=[page]),
    )

    doc_id = test_store.write_stage1(doc)
    assert doc_id == "TEST_DOC_001"

    retrieved = test_store.get_document("TEST_DOC_001")
    assert retrieved is not None
    assert retrieved["patient_id"] == "PATIENT_01"
    assert retrieved["status"] == "stage_1_complete"
    assert retrieved["stage_2_structured_entities"] is None

    stage1 = retrieved["stage_1_raw_ocr"]
    assert stage1["page_count"] == 1
    tokens = stage1["pages"][0]["tokens"]
    assert len(tokens) == 2
    assert tokens[0]["bbox"] == [120, 340, 180, 360]
    assert stage1["pages"][0]["tables"][0]["rows"] == [["Test", "Result"], ["HbA1c", "7.2"]]


def test_update_stage2_structured_entities(test_store: MongoStore):
    # Verifies Stage 2 structured facts update onto existing document
    page = PageRecord(page_number=1, full_text="Empagliflozin 10mg")
    doc = PatientDocument(
        document_id="TEST_DOC_002",
        patient_id="PATIENT_02",
        visit_date="2024-04-01",
        document_type="prescription",
        source_file="test_rx.pdf",
        stage_1_raw_ocr=Stage1RawOcr(page_count=1, pages=[page]),
    )
    test_store.write_stage1(doc)

    stage2 = Stage2StructuredEntities(
        compiled_by="test_extractor",
        medications=[
            MedicationEntity(
                name="Empagliflozin",
                rxnorm_code="1656339",
                dosage="10mg",
                frequency="once daily",
                source_bbox=[80, 200, 350, 220],
                confidence=0.96,
                anchor_text="Empagliflozin 10mg",
            )
        ],
        labs=[
            LabEntity(
                test_name="HbA1c",
                loinc_code="4548-4",
                value=7.2,
                unit="%",
                confidence=0.99,
            )
        ],
        advice="Maintain diet control.",
    )

    updated = test_store.write_stage2("TEST_DOC_002", stage2)
    assert updated is True

    record = test_store.get_document("TEST_DOC_002")
    assert record["status"] == "stage_2_complete"
    meds = record["stage_2_structured_entities"]["medications"]
    assert len(meds) == 1
    assert meds[0]["name"] == "Empagliflozin"
    assert meds[0]["dosage"] == "10mg"
    assert meds[0]["source_bbox"] == [80, 200, 350, 220]


def test_chunk_lifecycle(test_store: MongoStore):
    # Verifies intermediate chunk write and query operations for Teammate A and B
    chunk = DocumentChunk(
        chunk_id="CHK_TEST_P1_C1",
        document_id="TEST_DOC_003",
        patient_id="PATIENT_03",
        section_type="medications",
        chunk_text="Empagliflozin 10mg once daily",
        source_page=1,
        source_bbox=[80, 200, 350, 220],
    )
    test_store.write_chunk(chunk)

    chunks = test_store.get_chunks("TEST_DOC_003")
    assert len(chunks) == 1
    assert chunks[0]["chunk_id"] == "CHK_TEST_P1_C1"
    assert chunks[0]["section_type"] == "medications"
    assert chunks[0]["source_bbox"] == [80, 200, 350, 220]


def test_stage2_accepts_dynamic_extra_fields(test_store: MongoStore):
    # Verifies that new clinical fields from LLM are preserved without schema errors
    doc = PatientDocument(
        document_id="TEST_DOC_004",
        patient_id="PATIENT_04",
        document_type="consultation",
        source_file="note.pdf",
        stage_1_raw_ocr=Stage1RawOcr(page_count=1, pages=[]),
    )
    test_store.write_stage1(doc)

    dynamic_entities = {
        "labs": [{"test_name": "HbA1c", "value": 8.1, "unit": "%"}],
        "medications": [{"name": "Metformin", "dosage": "500mg"}],
        "allergies": ["Penicillin", "Aspirin"],
        "surgical_history": ["Appendectomy 2018"],
        "family_history": "Mother had T2DM",
        "vitals": {"blood_pressure": "120/80", "pulse": 72},
    }

    ok = test_store.write_stage2("TEST_DOC_004", dynamic_entities)
    assert ok is True

    fhir_bundle = {
        "resourceType": "Bundle",
        "type": "transaction",
        "entry": [
            {
                "resource": {
                    "resourceType": "Observation",
                    "status": "final",
                    "valueQuantity": {"value": 8.1, "unit": "%"},
                }
            }
        ],
    }
    ok_fhir = test_store.write_stage3("TEST_DOC_004", fhir_bundle)
    assert ok_fhir is True

    record = test_store.get_document("TEST_DOC_004")
    assert record["status"] == "stage_3_complete"
    assert record["stage_3_fhir_output"]["resourceType"] == "Bundle"
    stage2 = record["stage_2_structured_entities"]
    assert stage2["allergies"] == ["Penicillin", "Aspirin"]
    assert stage2["surgical_history"] == ["Appendectomy 2018"]
    assert stage2["family_history"] == "Mother had T2DM"
    assert stage2["vitals"]["blood_pressure"] == "120/80"

