"""Offline IndicTrans2 inference worker. Its stdout is reserved for JSON lines."""

import argparse
import gc
import json
import os
import re
import sys
from contextlib import redirect_stdout
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

CODES = {
    "en": "eng_Latn",
    "hi": "hin_Deva",
    "ta": "tam_Taml",
    "bn": "ben_Beng",
    "or": "ory_Orya",
    "te": "tel_Telu",
}
# IndicProcessor protects URLs as entities. Temporarily represent exact clinical
# tokens as URLs, then restore them only when every entity survives exactly once.
UNITS = r"(?:mg/kg/day|mg/kg|mg/dL|mg/g|mmol/mol|mmol/L|mL/min(?:/1\.73m[²2])?|mmHg|mcg|µg|mg|mL|kg|IU|g|L|U)"
PROTECTED = re.compile(
    r"https?://\S+|(?<![A-Za-z])(?:HbA1c|eGFR|LDL|HDL|ACR)(?![A-Za-z])"
    r"|(?<!\w)\d+(?:[.,:/-]\d+)*(?:\s*" + UNITS + r"(?![A-Za-z]))?(?:%|[²³])?"
    r"|(?<![A-Za-z])" + UNITS + r"(?![A-Za-z])",
    re.IGNORECASE,
)


def protect(text):
    entities = {}

    def replace(match):
        # Alphabetic suffixes avoid introducing spurious clinical numbers.
        n = len(entities)
        suffix = ""
        while True:
            suffix = chr(97 + n % 26) + suffix
            n = n // 26 - 1
            if n < 0:
                break
        key = f"https://{suffix}.keep.preppulse.invalid"
        entities[key] = match.group()
        return key

    return PROTECTED.sub(replace, text), entities


def restore(text, entities):
    for key, original in entities.items():
        if text.count(key) != 1:
            raise ValueError("Translation did not preserve a protected value")
        text = text.replace(key, original)
    return text


class Translator:
    def __init__(self, model_root, device="auto"):
        import torch

        self.torch = torch
        torch.set_num_threads(min(4, os.cpu_count() or 1))
        self.root = Path(model_root)
        self.device = device
        self.direction = None
        self.model = self.tokenizer = self.processor = None

    def load(self, direction):
        if self.direction == direction:
            return
        import torch
        from IndicTransToolkit import IndicProcessor
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

        self.model = self.tokenizer = self.processor = None
        self.direction = None
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        device = self.device
        if device == "auto":
            device = (
                "cuda"
                if torch.cuda.is_available() and torch.cuda.mem_get_info()[0] >= 3_500_000_000
                else "cpu"
            )
        if device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError(
                "CUDA is unavailable. Select auto or cpu in local translation setup."
            )
        folder = self.root / direction
        if not (folder / "model.safetensors").is_file():
            raise RuntimeError(
                "IndicTrans2 weights are missing. Run scripts/download_translation_models.py."
            )
        self.tokenizer = AutoTokenizer.from_pretrained(
            folder, trust_remote_code=True, local_files_only=True
        )
        self.model = (
            AutoModelForSeq2SeqLM.from_pretrained(
                folder,
                trust_remote_code=True,
                local_files_only=True,
                use_safetensors=True,
                torch_dtype=torch.float16 if device == "cuda" else torch.float32,
                attn_implementation="eager",
            )
            .to(device)
            .eval()
        )
        self.processor = IndicProcessor(inference=True)
        self.direction = direction

    def translate(self, text, source, target):
        if source not in CODES or target not in CODES:
            raise ValueError("Unsupported translation language")
        if source == target or not text.strip():
            return text
        if "\n" in text:
            return "\n".join(self.translate(line, source, target) for line in text.split("\n"))
        if source != "en" and target != "en":
            return self.translate(self.translate(text, source, "en"), "en", target)
        self.load("en-indic" if source == "en" else "indic-en")
        protected, entities = protect(text)
        output = []
        # Sentence boundaries first; long sentences are divided by word count
        # until tokenization fits. No truncation of a clinician instruction.
        pending = re.split(r"(?<=[.!?।])\s+|\n+", protected)
        while pending:
            sentence = pending.pop(0)
            if not sentence.strip():
                continue
            batch = self.processor.preprocess_batch(
                [sentence], src_lang=CODES[source], tgt_lang=CODES[target]
            )
            encoded = self.tokenizer(batch, return_tensors="pt", padding=True, truncation=False)
            if encoded["input_ids"].shape[1] > 240:
                words = sentence.split()
                if len(words) < 2:
                    raise ValueError("An instruction exceeds the translation model input limit")
                middle = len(words) // 2
                pending[0:0] = [" ".join(words[:middle]), " ".join(words[middle:])]
                continue
            encoded = encoded.to(self.model.device)
            with self.torch.inference_mode():
                generated = self.model.generate(
                    **encoded, max_new_tokens=256, num_beams=5, do_sample=False
                )
            if generated.shape[1] >= 256 and int(generated[0, -1]) != self.tokenizer.eos_token_id:
                raise ValueError("Translation reached its output limit")
            decoded = self.tokenizer.batch_decode(
                generated, skip_special_tokens=True, clean_up_tokenization_spaces=True
            )
            output.extend(self.processor.postprocess_batch(decoded, lang=CODES[target]))
        return restore(" ".join(output), entities)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", required=True)
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    args = parser.parse_args()
    translator = Translator(args.models, args.device)
    protocol = sys.stdout
    for line in sys.stdin:
        try:
            request = json.loads(line)
            result, errors = {}, {}
            with redirect_stdout(sys.stderr):
                for row in request["segments"]:
                    try:
                        result[row["id"]] = translator.translate(
                            row["text"], row["source_language"], request["target_language"]
                        )
                    except Exception as exc:  # noqa: BLE001 - retain other valid segments
                        errors[row["id"]] = safe_error(exc)
            response = {"translations": result, "errors": errors}
            if errors and not result:
                response["error"] = next(iter(errors.values()))
        except Exception as exc:  # noqa: BLE001 - no input text or stack trace is exposed
            response = {"error": safe_error(exc)}
        protocol.write(json.dumps(response, ensure_ascii=False) + "\n")
        protocol.flush()


def safe_error(exc):
    if isinstance(exc, (ImportError, ModuleNotFoundError)):
        return "Local translation dependencies are missing. Run setup_translation.ps1."
    if isinstance(exc, OSError):
        return "Local model could not be loaded. Check the downloaded weights and environment."
    allowed = {
        "Unsupported translation language",
        "Translation did not preserve a protected value",
        "An instruction exceeds the translation model input limit",
        "Translation reached its output limit",
        "IndicTrans2 weights are missing. Run scripts/download_translation_models.py.",
        "CUDA is unavailable. Select auto or cpu in local translation setup.",
    }
    return str(exc) if str(exc) in allowed else "Local translation failed. Retry or check setup."


if __name__ == "__main__":
    main()
