import copy
import importlib
import json
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from jsonschema import ValidationError

from preppulse_preprocessing.config import GroundingConfig
from preppulse_preprocessing.fhir import to_fhir_bundle, validate_bundle
from preppulse_preprocessing.ground import ground_entities
from preppulse_rag.cloud_provider import ProviderUnavailable, RoutedChatModel
from preppulse_rag.runtime import BudgetExceeded, finish, ledger, reserve


@pytest.fixture
def budget(monkeypatch, tmp_path):
    monkeypatch.delenv("Main_Sarvam_AI_Credits", raising=False)
    monkeypatch.setenv("PREPPULSE_PRIVATE_ROOT", str(tmp_path))
    monkeypatch.setenv("SARVAM_AI_CREDITS_ACC_1", "test-key-one")
    monkeypatch.setenv("SARVAM_AI_CREDITS_ACC_2", "test-key-two")
    monkeypatch.setenv("SARVAM_AI_CREDITS_ACC_3", "")
    monkeypatch.setenv("PREPPULSE_SYNTHETIC_ONLY", "1")
    monkeypatch.setenv("Gemini_free_api_keys", "test-gemini")
    return tmp_path


def response(code, text="ok", usage=None):
    return httpx.Response(code, json={"choices": [{"message": {"content": text}, "finish_reason": "stop"}],
                                      "usage": usage or {"prompt_tokens": 10, "completion_tokens": 2}})


def test_exhausted_key_rotates_without_exposing_credentials(budget, monkeypatch):
    calls = []
    def post(self, url, **kwargs):
        calls.append(kwargs["headers"]["api-subscription-key"])
        return response(402) if len(calls) == 1 else response(200, "Grounded answer")
    monkeypatch.setattr(httpx.Client, "post", post)
    answer = RoutedChatModel(provider="sarvam").invoke("Synthetic evidence")
    assert answer.content == "Grounded answer"
    assert answer.response_metadata["account"] == "ACC_2"
    with ledger() as db:
        serialized = json.dumps(db.execute("SELECT * FROM calls").fetchall())
    assert "test-key" not in serialized and "Synthetic evidence" not in serialized


def test_rate_limit_does_not_rotate_sarvam_keys(budget, monkeypatch):
    calls = []
    def post(self, url, **kwargs):
        calls.append(url)
        return response(429)
    monkeypatch.setattr(httpx.Client, "post", post)
    with pytest.raises(ProviderUnavailable):
        RoutedChatModel(provider="sarvam").invoke("Synthetic evidence")
    assert len(calls) == 1


@pytest.mark.parametrize("enable_gemini, expected", [("1", "gemini"), ("0", "local")])
def test_auto_fallback_preserves_order_and_gemini_opt_in(budget, monkeypatch, enable_gemini, expected):
    monkeypatch.setenv("PREPPULSE_GEMINI_ENABLED", enable_gemini)
    calls = []

    def post(self, url, **kwargs):
        calls.append(url)
        return response(503) if "sarvam" in url else response(200, "Verified fallback")

    monkeypatch.setattr(httpx.Client, "post", post)
    answer = RoutedChatModel(provider="auto").invoke("Synthetic evidence")
    assert answer.response_metadata["provider"] == expected
    assert len(calls) == 3  # Two eligible Sarvam accounts, then the selected fallback.
    assert "sarvam" in calls[0] and "sarvam" in calls[1]
    assert ("googleapis.com" in calls[-1]) == (expected == "gemini")


def test_budget_reservations_are_atomic_and_survive_reopen(budget, monkeypatch):
    monkeypatch.setenv("PREPPULSE_SARVAM_BUDGET_INR", "1")
    def attempt(_):
        try:
            return reserve("sarvam", "ACC_1", "test", .3)
        except BudgetExceeded:
            return None
    with ThreadPoolExecutor(max_workers=8) as pool:
        accepted = [item for item in pool.map(attempt, range(20)) if item]
    assert len(accepted) == 3
    finish(accepted[0], "ok", .3)
    with ledger() as db:
        assert db.execute("SELECT COUNT(*) FROM calls").fetchone()[0] == 3


def test_shared_pool_threshold_and_unknown_balance(budget, monkeypatch):
    monkeypatch.setenv("SARVAM_ACC_1_STARTING_CREDITS", "10.1")
    with pytest.raises(BudgetExceeded):
        reserve("sarvam", "ACC_1", "test", .2)
    monkeypatch.delenv("SARVAM_ACC_1_STARTING_CREDITS")
    assert reserve("sarvam", "ACC_1", "test", .2)


def test_gemini_synthetic_guard_and_empty_answer(budget, monkeypatch):
    monkeypatch.setenv("PREPPULSE_SYNTHETIC_ONLY", "0")
    with pytest.raises(ProviderUnavailable, match="synthetic"):
        RoutedChatModel(provider="gemini").invoke("hello")
    monkeypatch.setenv("PREPPULSE_SYNTHETIC_ONLY", "1")
    monkeypatch.setattr(httpx.Client, "post", lambda *a, **kw: response(200, ""))
    with pytest.raises(ProviderUnavailable, match="Empty"):
        RoutedChatModel(provider="gemini").invoke("hello")


def test_fhir_is_stable_resolves_subject_and_rejects_unknown_fields():
    entities = {"labs": [{"test_name": "HbA1c", "value": 8.3, "unit": "%", "source_page": 1,
                          "source_bbox": [100, 200, 300, 220], "anchor_text": "HbA1c 8.3%"}]}
    a = to_fhir_bundle(entities, "PRP-TEST", "DOC-TEST")
    assert a == to_fhir_bundle(entities, "PRP-TEST", "DOC-TEST")
    assert a["entry"][1]["resource"]["subject"]["reference"] == a["entry"][0]["fullUrl"]
    invalid = copy.deepcopy(a)
    invalid["entry"][1]["resource"]["_provenance"] = {"bbox": [1, 2, 3, 4]}
    with pytest.raises(ValidationError):
        validate_bundle(invalid)
    invalid = copy.deepcopy(a)
    invalid["entry"][1]["resource"]["subject"]["reference"] = "urn:uuid:missing"
    with pytest.raises(ValueError, match="Unresolved"):
        validate_bundle(invalid)


def test_grounding_rejects_number_from_another_row():
    doc = {"stage_1_raw_ocr": {"pages": [{"page_number": 1,
        "full_text": "HbA1c 8.3\nCreatinine 1.2", "tokens": [
            {"text": "HbA1c", "bbox": [1, 1, 20, 10]}, {"text": "8.3", "bbox": [21, 1, 30, 10]},
            {"text": "Creatinine", "bbox": [1, 20, 20, 30]}, {"text": "1.2", "bbox": [21, 20, 30, 30]}]}]}}
    result = ground_entities({"labs": [{"test_name": "HbA1c", "value": 1.2,
                                         "anchor_text": "HbA1c 8.3", "source_page": 1}]}, doc, GroundingConfig())
    assert not result["labs"] and result["review_queue"]
    medication = ground_entities({"medications": [{"name": "Synthetic medication", "dosage": "100 mg",
        "anchor_text": "HbA1c 8.3", "source_page": 1}]}, doc, GroundingConfig())
    assert not medication["medications"] and medication["review_queue"]


def test_translation_validates_every_segment_before_publication(budget, monkeypatch):
    module = importlib.import_module("preppulse_api.cloud_services")
    monkeypatch.setattr(module, "sarvam_request", lambda *a, **kw: {"translated_text": "மருத்துவரிடம் பேசுங்கள்"})
    from langchain_core.messages import AIMessage
    monkeypatch.setattr(RoutedChatModel, "invoke", lambda *a, **kw: AIMessage(content='{"translation":"மருத்துவரிடம் பேசுங்கள்"}'))
    with pytest.raises(ValueError, match="protected"):
        module.translate_sarvam([("i", "Ask about HbA1c 8.3%.", "en")], "ta")


def test_prompt_contract_and_classification_alias_are_not_silently_prediabetic(monkeypatch):
    from types import SimpleNamespace

    from langchain_core.documents import Document
    from langchain_core.messages import AIMessage

    from preppulse_agents.graph import classification_agent
    from preppulse_agents.prompt_loader import format_agent_prompt
    from preppulse_rag.llm_provider import LLMFactory
    system, _, _ = format_agent_prompt("classification_agent", context_text="Synthetic evidence")
    assert "OUTPUT CONTRACT" in system and "non_diabetic" in system
    retriever = SimpleNamespace(retrieve=lambda *a, **kw: [Document(
        page_content="Documented Type 2 diabetes", metadata={"source_file": "synthetic.pdf"})])
    monkeypatch.setenv("PREPPULSE_STRICT_AI", "1")
    monkeypatch.setattr(LLMFactory, "get_chat_model", lambda **kw: SimpleNamespace(invoke=lambda *a: AIMessage(
        content='{"category":"diabetes","stage":"Type 2 Diabetes","diagnostic_basis":"Documented diagnosis"}')))
    result = classification_agent({"patient_id": "TEST", "retriever": retriever})
    assert result["classification"].category == "diabetic"
    monkeypatch.setattr(LLMFactory, "get_chat_model", lambda **kw: SimpleNamespace(invoke=lambda *a: AIMessage(
        content='{"category":"unrecognised","stage":"Diagnosed"}')))
    with pytest.raises(ValueError, match="contract"):
        classification_agent({"patient_id": "TEST", "retriever": retriever})


def test_checkpoint_state_roundtrip_and_patient_source_isolation(budget, monkeypatch):
    from types import SimpleNamespace

    import mongomock

    from preppulse_agents.schemas import PatientClassification
    from preppulse_api.analysis_checkpoint import identity, restore, save
    store = SimpleNamespace(db=mongomock.MongoClient().test)
    patient = {"patient_id": "A", "name": "Synthetic"}
    docs = [{"stage_1_raw_ocr": {"pages": []}}]
    key = identity(patient, docs)
    save(store, key, {"patient_id": "A", "classification": PatientClassification(category="diabetic"),
                      "retriever": object()}, "trajectory_agent")
    cached = store.db.analysis_checkpoints.find_one({"identity": key})
    assert "retriever" not in cached["values"]
    assert restore(cached["values"])["classification"].category == "diabetic"
    assert key != identity({**patient, "patient_id": "B"}, docs)
    assert key != identity(patient, [{"stage_1_raw_ocr": {"pages": ["changed"]}}])


def test_structured_processing_resumes_only_failed_documents(budget, monkeypatch):
    import mongomock

    from preppulse_api.preprocessing import process_structured
    from preppulse_api.store import WorkspaceStore
    from preppulse_preprocessing.pipeline import Pipeline
    store = WorkspaceStore.__new__(WorkspaceStore)
    store.db = mongomock.MongoClient().test
    store.db.patients.insert_one({"patient_id": "TEST", "name": "Synthetic"})
    for record in ["ONE", "TWO"]:
        store.db.patient_documents.insert_one({"document_id": record, "patient_id": "TEST",
                                               "stage_1_raw_ocr": {"pages": []}})
    class FakePipeline:
        def __init__(self):
            self.broken = True
            self.calls = []
        def process_document(self, doc, persist):
            self.calls.append(doc["document_id"])
            if self.broken and doc["document_id"] == "TWO":
                raise ValueError("Synthetic extraction failure")
            return {"stage_2": {"labs": [], "medications": [], "diagnoses": [], "vitals": [],
                                "review_queue": []}, "review_queue": 0}
    pipeline = FakePipeline()
    monkeypatch.setattr(Pipeline, "build", lambda *a, **kw: pipeline)
    monkeypatch.setenv("PREPPULSE_AI_PROVIDER", "mock")
    monkeypatch.setenv("PREPPULSE_STRICT_AI", "1")
    mongo = type("Mongo", (), {"get_patient_documents": lambda _, pid: list(
        store.db.patient_documents.find({"patient_id": pid}))})()
    with pytest.raises(ValueError):
        process_structured(store, mongo, "TEST")
    pipeline.broken = False
    result = process_structured(store, mongo, "TEST")
    assert pipeline.calls == ["ONE", "TWO", "TWO"]
    assert result["complete"] == 2 and result["failed"] == 0
    assert store.db.fhir_versions.count_documents({}) == 2
    assert all(doc["stage_1_raw_ocr"] == {"pages": []} for doc in store.db.patient_documents.find({}))


def test_long_dictation_is_chunked_before_the_service(budget, monkeypatch):
    import io
    import wave

    from preppulse_api import cloud_services
    source = io.BytesIO()
    with wave.open(source, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * 16000 * 61)
    durations = []
    def service(path, **kwargs):
        with wave.open(io.BytesIO(kwargs["files"]["file"][1]), "rb") as wav:
            durations.append(wav.getnframes() / wav.getframerate())
        return {"transcript": "Synthetic dictation"}
    monkeypatch.setattr(cloud_services, "sarvam_request", service)
    transcript = cloud_services.transcribe_sarvam(source.getvalue())
    assert durations == [25, 25, 11]
    assert transcript.count("Synthetic dictation") == 3


def test_catalog_reconciliation_recovers_only_verified_owned_measurements():
    from preppulse_api.verified_measurements import reconcile
    doc = {"document_id": "DOC-A", "stage_1_raw_ocr": {"pages": []}}
    point = {"value": 90.0, "unit": "mL/min/1.73m2", "date": "2026-01-01",
             "citation": {"document_id": "DOC-A", "source_verified": True, "page_number": 1,
                          "bbox": [10, 10, 90, 20], "snippet": "eGFR >90"}}
    catalog = {"metric_series": [{"metric_name": "eGFR", "points": [point]}]}
    result = reconcile(doc, {"labs": []}, catalog)
    assert result["labs"][0]["value_comparator"] == ">"
    assert reconcile(doc, result, catalog) == result
    catalog["metric_series"][0]["points"][0]["citation"]["document_id"] = "DOC-B"
    assert not reconcile(doc, {"labs": []}, catalog)["labs"]


def test_fast_fhir_schema_dispatch_matches_the_original_schema():
    from jsonschema import Draft6Validator

    from preppulse_preprocessing.fhir import validator
    bundle = to_fhir_bundle({"labs": [{"test_name": "HbA1c", "value": 7.2,
                                       "source_bbox": [1, 2, 3, 4], "source_page": 1}]}, "TEST")
    original = Draft6Validator(validator().schema)
    cases = [bundle]
    for field, value in [("status", "bogus"), ("resourceType", "NotAResource"), ("_provenance", {})]:
        invalid = copy.deepcopy(bundle)
        invalid["entry"][1]["resource"][field] = value
        cases.append(invalid)
    for case in cases:
        assert validator().is_valid(case) == original.is_valid(case)


def test_chat_citations_are_individual_valid_and_dates_are_qualified():
    from preppulse_api.chat_service import normalize_answer
    answer = normalize_answer("- **2026-01-01**: Admission noted [1, 2]. More [999] and [<12].",
                              2, {"2026-01-01"})
    assert "Record dated 2026-01-01" in answer
    assert "[1][2]" in answer and "[999]" not in answer and "[<12]" not in answer
