"""Opt-in live model check using synthetic text only; never opens MongoDB."""

import argparse
import copy
import json
import time
from pathlib import Path

import fitz

from preppulse_api.care import pdf_bytes
from preppulse_api.care_translation import translate_batch, usable
from preppulse_api.local_translation import stop_worker


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--languages", default="hi,ta,bn,or,te")
    parser.add_argument("--reverse", action="store_true")
    parser.add_argument("--output", default=".tmp/translation-smoke")
    args = parser.parse_args()
    output = Path(__file__).resolve().parents[1] / args.output
    output.mkdir(parents=True, exist_ok=True)
    batch = [
        (
            "item:records",
            "Bring earlier test reports and current prescriptions to the visit.",
            "en",
        ),
        (
            "item:metric",
            "The last recorded HbA1c was 8.2%. Bring the home readings already requested by the doctor.",
            "en",
        ),
        (
            "notes",
            "Review the recent blood sugar and blood pressure readings with the care team in 7 days.\nDo not change treatment without consulting the clinician.",
            "en",
        ),
        ("dose:one", "1 tablet after food.", "en"),
        (
            "item:units",
            "Bring the source record showing 10U, 8mg, glucose 183 mg/dL and blood pressure 140/90 mmHg.",
            "en",
        ),
    ]
    results = {}
    try:
        for language in args.languages.split(","):
            started = time.monotonic()
            values = translate_batch(batch, language)
            assert all(
                usable(values.get(key), text, language, source) for key, text, source in batch
            ), f"Invalid translation: {language}"
            plan = {
                "visit_id": "SYNTHETIC-VISIT",
                "approved_at": "2026-11-04T10:00:00+05:30",
                "approved_by": "Synthetic reviewer",
                "mode": "family",
                "items": [
                    {
                        "item_id": key[5:],
                        "text": text,
                        "source_language": "en",
                        "texts": {language: values[key]},
                        "frequency": "once",
                    }
                    for key, text, _ in batch
                    if key.startswith("item:")
                ],
                "doctor_notes": batch[2][1],
                "notes_language": "en",
                "notes_texts": {language: values["notes"]},
                "medications": [
                    {
                        "name": "Test medicine",
                        "dose": batch[3][1],
                        "dose_texts": {language: values["dose:one"]},
                        "start_date": "2026-11-04",
                        "duration": 7,
                        "duration_unit": "days",
                        "times": ["morning"],
                        "food": "after food",
                    }
                ],
            }
            original = copy.deepcopy(plan)
            data = pdf_bytes(
                plan, {"name": "Synthetic patient", "patient_id": "SYNTHETIC"}, language
            )
            (output / f"{language}.pdf").write_bytes(data)
            with fitz.open(stream=data, filetype="pdf") as document:
                extracted = "".join(page.get_text() for page in document)
                assert "8.2" in extracted and "Test medicine" in extracted
                assert not any(
                    marker in extracted
                    for marker in (
                        "keep.preppulse.invalid",
                        "Bring earlier test",
                        "1 tablet after food",
                    )
                )
            assert plan == original
            results[language] = {"seconds": round(time.monotonic() - started, 1), "texts": values}
            (output / "results.json").write_text(
                json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(
                f"PASS {language}: text, numbers/units and PDF ({results[language]['seconds']}s)",
                flush=True,
            )
        if args.reverse and "ta" in results:
            reverse = [(key, value, "ta") for key, value in results["ta"]["texts"].items()]
            values = translate_batch(reverse, "en")
            assert all(usable(values.get(key), text, "en", source) for key, text, source in reverse)
            results["ta-en"] = values
            print("PASS ta->en: reverse translation and protected values", flush=True)
        (output / "results.json").write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Synthetic output saved in {output}", flush=True)
    finally:
        stop_worker()


if __name__ == "__main__":
    main()
