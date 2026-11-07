"""Assert what leaves the HTTP boundary, not just what the UI displays."""
import json
import re

import httpx
import pytest

from preppulse_rag.privacy import PrivacyFilter, PrivacyUnavailable, local_endpoint

IDENTITY = {"name": "Ananya Baruah", "dob": "1970-04-09", "patient_id": "PRP-A2DE5B85F1074A09",
            "external_aliases": ["PP001", "PP001_Ananya_Baruah"],
            "email": "ananya@example.org", "phone": "9876543210", "address": "42 Sample Road"}


@pytest.fixture
def registry(monkeypatch):
    monkeypatch.setattr("preppulse_rag.privacy.load_identifiers", lambda: [IDENTITY])


def test_redaction_preserves_clinical_evidence_and_restores_exact_anchors():
    privacy = PrivacyFilter([IDENTITY])
    source = ("Patient: Ananya Baruah | DOB: 09-Apr-1970 | Age: 56 | Female\n"
              "PP001_Ananya_Baruah/2019-10-01_lab.pdf PRP-A2DE5B85F1074A09\n"
              "Email: ananya@example.org Phone: 9876543210 Address: 42 Sample Road\n"
              "HbA1c 8.3% Fasting glucose 168 mg/dL eGFR 69 mL/min/1.73m2 BP 114/72 mmHg\n"
              "Metformin 500 mg twice daily. Report date 2026-10-08. [1] page 2 box [114,235,651,244]")
    safe = privacy.redact(source)
    for value in ("Ananya", "Baruah", "PP001", IDENTITY["patient_id"], IDENTITY["email"],
                  IDENTITY["phone"], IDENTITY["address"], "09-Apr-1970"):
        assert value not in safe
    for value in ("8.3%", "168 mg/dL", "114/72 mmHg", "500 mg", "2026-10-08", "[1]", "[114,235,651,244]"):
        assert value in safe
    assert privacy.restore(safe) == source
    assert PrivacyFilter([IDENTITY]).redact(source) != safe  # No cross-request stable tracking token.


def test_unknown_labelled_identifiers_and_json_keys():
    privacy = PrivacyFilter([])
    source = {"patient_name": "Unknown", "text": "Patient: Ravi Kapoor | DOB: 02 Jan 1960\nPhone: +1 212 555 0199\nEmail: ravi@example.org\nHbA1c 7.9%"}
    safe = privacy.redact(source)
    assert "Ravi Kapoor" not in safe["text"] and "1960" not in safe["text"]
    assert "+1 212 555 0199" not in safe["text"] and "7.9%" in safe["text"]
    assert "patient_name" in safe
    assert safe["patient_name"] != "Unknown"
    source = json.dumps({"address": '42 "Sample" Road\\Unit 1', "dob": "1970-04-09", "value": 8.3})
    assert json.loads(privacy.restore(privacy.redact(source))) == json.loads(source)


def test_cloud_http_payload_is_private_and_output_citations_restored(registry, monkeypatch, tmp_path):
    RoutedChatModel = pytest.importorskip("preppulse_rag.cloud_provider").RoutedChatModel
    monkeypatch.setenv("PREPPULSE_ENV", "test")
    monkeypatch.setenv("PREPPULSE_AI_ENABLED", "1")
    monkeypatch.setenv("PREPPULSE_PRIVATE_ROOT", str(tmp_path))
    monkeypatch.setenv("Main_Sarvam_AI_Credits", "synthetic-key")
    sent = []
    def post(_, url, **kw):
        payload = kw["json"]
        sent.append(payload)
        text = payload["messages"][-1]["content"]
        assert "Ananya" not in text and "PP001" not in text and "1970-04-09" not in text
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": text}}]})
    monkeypatch.setattr(httpx.Client, "post", post)
    source = json.dumps({"name": "Ananya Baruah", "dob": "1970-04-09", "citation": "PP001_Ananya_Baruah_lab.pdf", "value": 8.3})
    result = RoutedChatModel(provider="sarvam").invoke(source)
    assert json.loads(result.content) == json.loads(source)
    assert result.response_metadata["privacy"] == "pseudonymized" and len(sent) == 1


def test_registry_failure_sends_nothing(monkeypatch):
    RoutedChatModel = pytest.importorskip("preppulse_rag.cloud_provider").RoutedChatModel
    monkeypatch.setenv("PREPPULSE_ENV", "test")
    monkeypatch.setenv("PREPPULSE_AI_ENABLED", "1")
    monkeypatch.setenv("Main_Sarvam_AI_Credits", "synthetic-key")
    def fail():
        raise PrivacyUnavailable("Privacy registry unavailable")
    monkeypatch.setattr("preppulse_rag.privacy.load_identifiers", fail)
    monkeypatch.setattr(httpx.Client, "post", lambda *a, **kw: pytest.fail("Unsafe request sent"))
    with pytest.raises(PrivacyUnavailable):
        RoutedChatModel(provider="sarvam").invoke("Patient: Ananya Baruah")


def test_azure_translation_masks_identifiers_and_keeps_value_checks(registry, monkeypatch):
    azure_services = pytest.importorskip("preppulse_api.azure_services")
    monkeypatch.setenv("AZURE_TRANSLATOR_ENDPOINT", "https://api.cognitive.microsofttranslator.com")
    def request(*a, **kw):
        source = kw["json"][0]["Text"]
        assert "Ananya" not in source and "8.3" not in source
        translated = source.replace("Ask", "கேளுங்கள்")
        return httpx.Response(200, json=[{"translations": [{"text": translated}]}])
    monkeypatch.setattr(azure_services, "request", request)
    monkeypatch.setattr("preppulse_api.care_translation.usable", lambda *a: True)
    result = azure_services.translate_azure([("i", "Ask Ananya Baruah about HbA1c 8.3%", "en")], "ta")
    assert "Ananya Baruah" in result["i"] and "8.3%" in result["i"]


def test_sarvam_translation_masks_identifiers(registry, monkeypatch):
    cloud_services = pytest.importorskip("preppulse_api.cloud_services")
    def request(*a, **kw):
        source = kw["json"]["input"]
        assert "Ananya" not in source and "8.3" not in source
        return {"translated_text": source.replace("Ask", "கேளுங்கள்")}
    monkeypatch.setattr(cloud_services, "sarvam_request", request)
    monkeypatch.setattr("preppulse_api.care_translation.usable", lambda *a: True)
    result = cloud_services.translate_sarvam([("i", "Ask Ananya Baruah about HbA1c 8.3%", "en")], "ta")
    assert "Ananya Baruah" in result["i"] and "8.3%" in result["i"]


def test_local_endpoint_and_openai_client_contract(registry, monkeypatch):
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatResult, ChatGeneration
    from preppulse_rag.private_openai import PrivateChatOpenAI
    assert local_endpoint("http://127.0.0.1:1234/v1")
    assert local_endpoint("http://192.168.1.50:1234/v1")
    assert not local_endpoint("https://api.sarvam.ai/v1")
    def generate(_, messages, **kwargs):
        assert "Ananya" not in messages[-1].content
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=messages[-1].content))])
    monkeypatch.setattr(ChatOpenAI, "_generate", generate)
    result = PrivateChatOpenAI(base_url="https://api.sarvam.ai/v1", api_key="fake").invoke("Ananya Baruah HbA1c 8.3% [1]")
    assert result.content == "Ananya Baruah HbA1c 8.3% [1]"
