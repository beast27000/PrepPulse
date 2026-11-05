"""Bounded, synthetic-only live checks. Does not print keys or patient text."""
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / ".tmp/azure_pilot"


def main():
    load_dotenv(STAGING / "server.env", override=True)
    os.environ["PREPPULSE_PRIVATE_ROOT"] = str(STAGING / "service_check_main")
    os.environ["PREPPULSE_ENV"] = "test"
    from preppulse_api.azure_services import speak_azure, transcribe_azure, translate_azure
    from preppulse_rag.cloud_provider import RoutedChatModel
    results = {}

    def check(name, operation):
        start = time.monotonic()
        try:
            value = operation()
            results[name] = {"ok": True, "seconds": round(time.monotonic() - start, 2), **value}
        except Exception as exc:  # noqa: BLE001 - independent synthetic service diagnostics
            # All service adapters return sanitized exceptions. Limit surface.
            results[name] = {"ok": False, "error": type(exc).__name__ + ": " + str(exc)[:180]}
        print(json.dumps({name: results[name]}), flush=True)
        (STAGING / "services-verification.json").write_text(json.dumps(results, indent=2))

    for provider in ["azure", "sarvam"]:
        check(provider + "_chat", lambda provider=provider: {
            "provider": RoutedChatModel(provider=provider, max_tokens=2048).invoke(
                'For a synthetic connectivity test, return JSON {"status":"ok"}.', json_mode=True
            ).response_metadata["provider"]})
    for language in ["hi", "ta", "bn", "or", "te"]:
        def translate(language=language):
            result = translate_azure([
                ("a", "Bring earlier test reports to the visit.", "en"),
                ("b", "Record the blood pressure reading requested by the doctor: 120/80 mmHg.", "en")], language)
            assert len(result) == 2 and "120/80" in result["b"] and "mmHg" in result["b"]
            return {"segments": len(result), "values_preserved": True}
        check("translation_" + language, translate)
    def speech():
        audio = speak_azure("This is a synthetic PrepPulse voice check. Bring earlier reports to your next visit.")
        transcript = transcribe_azure(audio, "en")
        assert len(transcript.strip()) > 10
        return {"wav_bytes": len(audio), "transcript_characters": len(transcript)}
    check("speech_roundtrip", speech)


if __name__ == "__main__":
    main()
