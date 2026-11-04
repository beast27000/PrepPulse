"""Sarvam translation and voice adapters using the shared credit reservations."""
import base64
import io
import json as json_module
import os
import re
import wave

import httpx

from preppulse_rag.runtime import BudgetExceeded, cooldown, finish, reserve, sarvam_accounts

LANGUAGES = {"en": "en-IN", "hi": "hi-IN", "ta": "ta-IN", "bn": "bn-IN",
             "or": "od-IN", "te": "te-IN"}


def sarvam_request(path, *, cost, json=None, files=None, data=None):
    for alias, key in sarvam_accounts():
        try:
            call_id = reserve("sarvam", alias, path, cost)
        except BudgetExceeded:
            continue
        try:
            with httpx.Client(timeout=90, trust_env=False) as client:
                response = client.post("https://api.sarvam.ai/" + path,
                                       headers={"api-subscription-key": key}, json=json,
                                       files=files, data=data)
            if response.status_code == 402:
                finish(call_id, "http_402")
                cooldown(alias, 3600)
                continue
            if response.status_code != 200:
                finish(call_id, f"http_{response.status_code}")
                if response.status_code == 429:
                    cooldown("sarvam", 60)
                raise RuntimeError(f"Sarvam {path}: HTTP {response.status_code}")
            result = response.json()
            finish(call_id, "ok")  # Keep the conservative reservation when no charge is returned.
            return result
        except (httpx.HTTPError, ValueError):
            finish(call_id, "transport_or_json_error")
            raise RuntimeError("Sarvam service transport or decoding failed") from None
    raise RuntimeError("No eligible Sarvam account for this service")


PROTECTED = re.compile(
    r"https?://\S+|(?<![A-Za-z])(?:HbA1c|eGFR|LDL|HDL|ACR)(?![A-Za-z])"
    r"|\d+(?:[.,:/-]\d+)*(?:\s*(?:mg/dL|mg/g|mmol/L|mL/min|mmHg|mcg|mg|mL|kg|IU|U))?%?",
    re.IGNORECASE,
)


def translate_sarvam(batch, language):
    from preppulse_api.care_translation import usable
    result = {}
    for identity, text, source in batch:
        if source == language:
            result[identity] = text
            continue
        entities = {}

        def protect(match, entities=entities, text=text):
            # The service transliterates alphabetic markers and can drop URLs.
            # Its international-numeral mode preserves numeric markers; require
            # exact one-to-one survival before restoring any clinical value.
            key = str(918273645000 + len(entities))
            if key in text:
                raise ValueError("Reserved translation marker occurs in source text")
            entities[key] = match[0]
            return key

        encoded = PROTECTED.sub(protect, text)
        # Translate short, complete segments; never truncate a long clinical instruction.
        parts = re.split(r"(?<=[.!?])\s+|\n", encoded) if len(encoded) > 1800 else [encoded]
        translated = []
        for part in parts:
            if len(part) > 2000:
                raise ValueError("Instruction needs smaller complete translation segments")
            response = sarvam_request("translate", cost=len(part) * 2 / 1000, json={
                "input": part, "source_language_code": LANGUAGES[source],
                "target_language_code": LANGUAGES[language], "model": "sarvam-translate:v1",
                "mode": "formal", "numerals_format": "international"})
            translated.append(response.get("translated_text", ""))
        output = " ".join(translated)
        intact = all(output.count(key) == 1 for key in entities)
        for key, original in entities.items():
            output = output.replace(key, original)
        if not intact or not usable(output, text, language, source):
            # Dedicated translation can drop a marker in complex clinical units.
            # One source-only repair attempt stays with the same approved provider;
            # the caller can still fall back to local IndicTrans2 if validation fails.
            from preppulse_rag.cloud_provider import RoutedChatModel
            repaired = RoutedChatModel(provider="sarvam", max_tokens=2048).invoke([
                {"role": "system", "content": (
                    'Translate only. Return JSON {"translation":"..."}. Preserve every number, '
                    'unit, HbA1c/eGFR/LDL/ACR abbreviation, dose, negation and instruction exactly. '
                    'Keep unit symbols such as mg, U, mg/dL and mmHg in their original Latin spelling. '
                    'Translate all other text into the target language in its native script. '
                    'Add no advice, interpretation, explanation or extra content.')},
                {"role": "user", "content": json_module.dumps({"source_language": source,
                    "target_language": language, "source_text": text}, ensure_ascii=False)}], json_mode=True)
            output = json_module.loads(repaired.content).get("translation", "")
            if not usable(output, text, language, source):
                raise ValueError("Translation changed a protected measurement or language")
        result[identity] = output
    return result


def speak_sarvam(text, language="en"):
    if len(text) > 2400:
        raise ValueError("Read-aloud text exceeds the service segment limit")
    result = sarvam_request("text-to-speech", cost=len(text) * 3 / 1000, json={
        "text": text, "target_language_code": LANGUAGES[language], "speaker": "shubh",
        "model": "bulbul:v3", "speech_sample_rate": 24000})
    audios = result.get("audios") or []
    if len(audios) != 1:
        raise ValueError("Expected one audio response")
    audio = base64.b64decode(audios[0], validate=True)
    if not (audio[:4] == b"RIFF" and audio[8:12] == b"WAVE"):
        raise ValueError("Speech service did not return WAV")
    return audio


def transcribe_sarvam(audio, language="", filename="dictation.webm"):
    # The synchronous API accepts at most 30 seconds. Decode in memory and use
    # bounded 25-second mono WAV chunks so normal longer dictation still works.
    import av
    resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
    pieces, size = [], 0
    maximum = int(os.getenv("PREPPULSE_DICTATION_MAX_SECONDS", "300")) * 32000
    with av.open(io.BytesIO(audio)) as container:
        for frame in container.decode(audio=0):
            for converted in resampler.resample(frame):
                pcm = converted.to_ndarray().astype("<i2", copy=False).tobytes()
                size += len(pcm)
                if size > maximum:
                    raise ValueError("Dictation exceeds the configured duration limit")
                pieces.append(pcm)
    for converted in resampler.resample(None):
        pieces.append(converted.to_ndarray().astype("<i2", copy=False).tobytes())
    pcm = b"".join(pieces)
    if not pcm or len(pcm) > maximum:
        raise ValueError("Empty or overlong audio")
    transcripts = []
    for start in range(0, len(pcm), 25 * 32000):
        chunk = pcm[start:start + 25 * 32000]
        target = io.BytesIO()
        with wave.open(target, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            wav.writeframes(chunk)
        cost = len(chunk) / 32000 / 60 * float(os.getenv("SARVAM_STT_INR_PER_MINUTE", "1"))
        result = sarvam_request("speech-to-text", cost=cost,
                               files={"file": ("dictation.wav", target.getvalue(), "audio/wav")},
                               data={"model": "saaras:v3", "mode": "transcribe",
                                     "language_code": LANGUAGES.get(language, "unknown")})
        transcript = result.get("transcript")
        if not isinstance(transcript, str):
            raise TypeError("Transcription response missing text")
        transcripts.append(transcript.strip())
    return " ".join(transcripts)
