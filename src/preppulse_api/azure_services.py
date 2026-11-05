"""Azure translation and voice, with bounded requests and explicit Sarvam fallback."""
from __future__ import annotations

import html
import io
import json
import os
import re
import wave
from urllib.parse import quote, urlparse

import httpx

from preppulse_rag.runtime import finish, reserve

LOCALES = {"en": "en-IN", "hi": "hi-IN", "ta": "ta-IN", "bn": "bn-IN", "or": "or-IN", "te": "te-IN"}
VOICES = {"en": "en-IN-NeerjaNeural", "hi": "hi-IN-SwaraNeural", "ta": "ta-IN-PallaviNeural",
          "bn": "bn-IN-TanishaaNeural", "or": "or-IN-SubhasiniNeural", "te": "te-IN-ShrutiNeural"}


def endpoint(name):
    value = os.environ.get(name, "").rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query:
        raise RuntimeError("Configure a valid Azure HTTPS endpoint")
    return value


def chat_url():
    deployment = quote(os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4.1-mini"), safe="")
    return (endpoint("AZURE_OPENAI_ENDPOINT") + "/openai/deployments/" + deployment
            + "/chat/completions?api-version=2024-10-21")


def request(url, *, service, cost, key_name, region=None, **kwargs):
    key = os.environ.get(key_name)
    if not key:
        raise RuntimeError("Azure service credentials are not configured")
    call = reserve("azure", "AZURE", service, cost)
    headers = {"Ocp-Apim-Subscription-Key": key, **kwargs.pop("headers", {})}
    if region:
        headers["Ocp-Apim-Subscription-Region"] = region
    try:
        with httpx.Client(timeout=90, trust_env=False) as client:
            response = client.post(url, headers=headers, **kwargs)
        if response.status_code != 200:
            finish(call, "http_" + str(response.status_code))
            raise RuntimeError(f"Azure {service}: HTTP {response.status_code}")
        finish(call, "ok")
        return response
    except httpx.HTTPError:
        finish(call, "transport_error")
        raise RuntimeError("Azure service connection failed") from None


def translate_azure(batch, language):
    from preppulse_api.care_translation import usable
    from preppulse_api.cloud_services import PROTECTED
    result = {}
    for identity, text, source in batch:
        if source == language:
            result[identity] = text
            continue
        entities = {}

        def protect(match, entities=entities, text=text):
            marker = f"PPKEEP{len(entities)}END"
            if marker in text:
                raise ValueError("Reserved translation marker in text")
            entities[marker] = match[0]
            return '<span class="notranslate">' + marker + '</span>'

        encoded = PROTECTED.sub(protect, html.escape(text))
        # All-or-nothing complete segments; no truncation of medical instructions.
        if len(encoded) > 40000:
            raise ValueError("Translation instruction exceeds the supported size")
        response = request(endpoint("AZURE_TRANSLATOR_ENDPOINT") + "/translate",
            service="translation", cost=max(0.001, len(encoded) * 20 / 1_000_000),
            key_name="AZURE_TRANSLATOR_KEY", region=os.getenv("AZURE_TRANSLATOR_REGION"),
            params={"api-version": "3.0", "from": source, "to": language, "textType": "html"},
            json=[{"Text": encoded}]).json()
        translated = response[0]["translations"][0]["text"]
        output = html.unescape(re.sub(r"<[^>]*>", "", translated))
        if not all(output.count(marker) == 1 for marker in entities):
            raise ValueError("Translation lost a protected value")
        for marker, value in entities.items():
            output = output.replace(marker, value)
        if not usable(output, text, language, source):
            raise ValueError("Translation changed a measurement or target language")
        result[identity] = output
    return result


def speak_azure(text, language="en"):
    if language not in LOCALES or len(text) > 2400:
        raise ValueError("Unsupported read-aloud language or length")
    region = os.environ["AZURE_SPEECH_REGION"]
    ssml = (f'<speak version="1.0" xml:lang="{LOCALES[language]}">'
            f'<voice name="{VOICES[language]}">{html.escape(text)}</voice></speak>')
    response = request(f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1",
        service="tts", cost=max(.001, len(text) * 30 / 1_000_000), key_name="AZURE_SPEECH_KEY",
        headers={"Content-Type": "application/ssml+xml", "X-Microsoft-OutputFormat": "riff-24khz-16bit-mono-pcm"},
        content=ssml.encode("utf-8"))
    audio = response.content
    if len(audio) > 20 * 1024 * 1024 or audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
        raise ValueError("Azure did not return valid WAV audio")
    return audio


def transcribe_azure(audio, language="en"):
    import av
    detect_language = not language
    language = language or "en"
    if language not in LOCALES:
        raise ValueError("Unsupported dictation language")
    resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
    frames, size = [], 0
    maximum = int(os.getenv("PREPPULSE_DICTATION_MAX_SECONDS", "300")) * 32000
    with av.open(io.BytesIO(audio)) as container:
        for frame in container.decode(audio=0):
            for converted in resampler.resample(frame):
                data = converted.to_ndarray().astype("<i2", copy=False).tobytes()
                size += len(data)
                if size > maximum:
                    raise ValueError("Dictation is too long")
                frames.append(data)
    for converted in resampler.resample(None):
        frames.append(converted.to_ndarray().astype("<i2", copy=False).tobytes())
    pcm = b"".join(frames)
    if not pcm or len(pcm) > maximum:
        raise ValueError("Empty or overlong dictation")
    region = os.environ["AZURE_SPEECH_REGION"]
    parts = []
    for start in range(0, len(pcm), 25 * 32000):
        chunk = pcm[start:start + 25 * 32000]
        target = io.BytesIO()
        with wave.open(target, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            wav.writeframes(chunk)
        if detect_language:
            response = request(f"https://{region}.api.cognitive.microsoft.com/speechtotext/transcriptions:transcribe",
                service="stt", cost=len(chunk) / 32000 / 3600 * 2, key_name="AZURE_SPEECH_KEY",
                params={"api-version": "2025-10-15"},
                files={"audio": ("dictation.wav", target.getvalue(), "audio/wav")},
                data={"definition": json.dumps({"profanityFilterMode": "None"})}).json()
            text = " ".join(phrase.get("text", "") for phrase in response.get("combinedPhrases", []))
            if not text.strip():
                raise RuntimeError("No speech recognized; select a dictation language and retry")
            parts.append(text)
            continue
        response = request(f"https://{region}.stt.speech.microsoft.com/speech/recognition/conversation/cognitiveservices/v1",
            service="stt", cost=len(chunk) / 32000 / 3600 * 2, key_name="AZURE_SPEECH_KEY",
            params={"language": LOCALES[language], "format": "simple"},
            headers={"Content-Type": "audio/wav; codecs=audio/pcm; samplerate=16000"},
            content=target.getvalue()).json()
        if response.get("RecognitionStatus") not in {"Success", "NoMatch", "InitialSilenceTimeout"}:
            raise RuntimeError("Azure transcription was incomplete")
        parts.append(response.get("DisplayText", ""))
    return " ".join(parts).strip()


def with_fallback(function, *args):
    from preppulse_api.provider_settings import routing
    mode = routing()
    if mode == "disabled":
        raise RuntimeError("AI processing is disabled by the administrator")
    try:
        return globals()[function + "_azure"](*args)
    except (RuntimeError, ValueError, KeyError):
        if mode == "azure" or os.getenv("PREPPULSE_AZURE_FALLBACK", "sarvam") != "sarvam":
            raise
        from preppulse_api import cloud_services
        return getattr(cloud_services, function + "_sarvam")(*args)
