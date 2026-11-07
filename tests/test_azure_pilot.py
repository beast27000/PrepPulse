import importlib
import json
import threading
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import mongomock
import pytest

from preppulse_api import azure_services, jobs
from preppulse_rag.cloud_provider import ProviderUnavailable, RoutedChatModel
from preppulse_rag.runtime import BudgetExceeded, reserve


@pytest.fixture
def config(monkeypatch, tmp_path):
    monkeypatch.setattr("preppulse_rag.privacy.load_identifiers", lambda: [])
    monkeypatch.delenv("Main_Sarvam_AI_Credits", raising=False)
    monkeypatch.setenv("PREPPULSE_PRIVATE_ROOT", str(tmp_path))
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "test-chat")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "private-test-key")
    monkeypatch.setenv("PREPPULSE_ALLOW_LOCAL_AI", "0")
    return tmp_path


def test_azure_chat_endpoint_and_usage(config, monkeypatch):
    def post(_, url, **kw):
        assert url.endswith("/deployments/test-chat/chat/completions?api-version=2024-10-21")
        assert kw["headers"]["api-key"] == "private-test-key"
        assert kw["json"]["response_format"] == {"type": "json_object"}
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"ok":true}'},
            "finish_reason": "stop"}], "usage": {"prompt_tokens": 20, "completion_tokens": 10}})
    monkeypatch.setattr(httpx.Client, "post", post)
    reply = RoutedChatModel(provider="azure").invoke("Synthetic source", json_mode=True)
    assert reply.response_metadata["provider"] == "azure"
    assert json.loads(reply.content)["ok"]


def test_azure_budget_and_disabled_never_send(config, monkeypatch):
    monkeypatch.setenv("PREPPULSE_AZURE_AI_BUDGET_USD", "0")
    with pytest.raises(BudgetExceeded):
        reserve("azure", "AZURE", "chat", .1)
    monkeypatch.setenv("PREPPULSE_AI_ENABLED", "0")
    monkeypatch.setattr(httpx.Client, "post", lambda *a, **kw: pytest.fail("Network called"))
    with pytest.raises(ProviderUnavailable, match="disabled"):
        RoutedChatModel(provider="azure").invoke("test")


def test_azure_sarvam_fallback_never_calls_local(config, monkeypatch):
    monkeypatch.setenv("PREPPULSE_AI_PROVIDER_ORDER", "azure,sarvam")
    monkeypatch.setenv("SARVAM_AI_CREDITS_ACC_1", "synthetic-key")
    monkeypatch.setenv("SARVAM_AI_CREDITS_ACC_2", "")
    monkeypatch.setenv("SARVAM_AI_CREDITS_ACC_3", "")
    calls = []
    def post(_, url, **kw):
        calls.append(url)
        if "azure.com" in url:
            return httpx.Response(404)
        assert "sarvam.ai" in url
        return httpx.Response(200, json={"choices": [{"message": {"content": "Cited answer"}, "finish_reason": "stop"}]})
    monkeypatch.setattr(httpx.Client, "post", post)
    assert RoutedChatModel(provider="auto").invoke("test").response_metadata["provider"] == "sarvam"
    assert len(calls) == 2


def test_translation_preserves_values_and_does_not_publish_partial(config, monkeypatch):
    monkeypatch.setenv("AZURE_TRANSLATOR_ENDPOINT", "https://api.cognitive.microsofttranslator.com")
    def fake(*a, **kw):
        assert 'class="notranslate"' in kw["json"][0]["Text"]
        return SimpleNamespace(json=lambda: [{"translations": [{"text": "மருத்துவரிடம் HbA1c PPKEEP1END பற்றி பேசுங்கள்"}]}])
    monkeypatch.setattr(azure_services, "request", fake)
    with pytest.raises(ValueError, match="protected"):
        azure_services.translate_azure([("a", "Ask about HbA1c 8.3%", "en")], "ta")


def test_durable_queue_deduplicates_and_survives_executor_restart(config, monkeypatch):
    from preppulse_api import store as module
    db = mongomock.MongoClient().test
    monkeypatch.setattr(module, "WorkspaceStore", lambda: SimpleNamespace(db=db, client=SimpleNamespace(close=lambda: None)))
    def operation(identity):
        pass
    first = jobs.DurableExecutor().submit(operation, "TEST")
    second = jobs.DurableExecutor().submit(operation, "TEST")
    assert first == second and db.worker_tasks.count_documents({}) == 1
    assert jobs.is_pending(SimpleNamespace(db=db), "operation", ["TEST"])
    db.worker_tasks.update_one({"_id": first}, {"$set": {"status": "failed"}})
    assert jobs.DurableExecutor().submit(operation, "TEST") == first
    assert db.worker_tasks.find_one()["status"] == "queued"


def test_admin_preference_shared_on_disk(config, monkeypatch):
    from preppulse_api import provider_settings
    monkeypatch.setenv("PREPPULSE_ENV", "production")
    provider_settings.save("disabled")
    assert importlib.reload(provider_settings).routing() == "disabled"
    with pytest.raises(ProviderUnavailable, match="administrator"):
        RoutedChatModel(provider="auto").invoke("test")


def test_hackathon_account_is_primary_and_old_accounts_are_unused(config, monkeypatch):
    from preppulse_rag.runtime import sarvam_accounts
    monkeypatch.setenv("Main_Sarvam_AI_Credits", "new-private-key")
    monkeypatch.setenv("SARVAM_AI_CREDITS_ACC_1", "old-private-key")
    assert sarvam_accounts() == [("HACKATHON_MAIN", "new-private-key")]


def test_azure_chat_failure_does_not_disable_translation(config, monkeypatch):
    monkeypatch.setattr(httpx.Client, "post", lambda *a, **kw: httpx.Response(404))
    with pytest.raises(ProviderUnavailable):
        RoutedChatModel(provider="azure").invoke("Synthetic check")
    reserve("azure", "AZURE", "translation", .001)
    with pytest.raises(BudgetExceeded, match="cooldown"):
        reserve("azure", "AZURE_CHAT", "chat", .001)


def test_exhausted_worker_lease_becomes_retryable(config, monkeypatch):
    from preppulse_api import store as module
    db = mongomock.MongoClient().test
    db.worker_tasks.insert_one({"_id": "expired", "status": "running", "attempts": 3,
                               "lease_until": datetime.now(UTC) - timedelta(minutes=5)})
    monkeypatch.setattr(module, "WorkspaceStore", lambda: SimpleNamespace(
        db=db, indexes=lambda: None, client=SimpleNamespace(close=lambda: None)))
    class StopWhenIdle(threading.Event):
        def wait(self, timeout=None):
            self.set()
            return True
    jobs.run_worker(StopWhenIdle())
    assert db.worker_tasks.find_one()["status"] == "failed"
