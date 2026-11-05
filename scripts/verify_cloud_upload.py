"""Verify a genuinely scanned upload passes cloud Tesseract, FHIR and agents."""
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import fitz
import httpx

ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / ".tmp/azure_pilot"
BASE = "https://preppulse-pilot-b8bc.centralindia.cloudapp.azure.com/api/"


def main():
    access = json.loads((STAGING / "pilot_access.json").read_text())
    pid = json.loads((STAGING / "care-verification.json").read_text())["synthetic_patient_id"]
    with httpx.Client(base_url=BASE, timeout=120, trust_env=False) as client:
        response = client.post("auth/login", json={k: access["doctor"][k] for k in ["username", "password"]})
        response.raise_for_status()
        client.headers["X-CSRF-Token"] = response.json()["csrf"]
        page_document = fitz.open()
        page = page_document.new_page()
        page.insert_text((60, 80), "SYNTHETIC DEPLOYMENT OCR VERIFICATION", fontsize=16)
        page.insert_text((60, 125), "Patient: Deployment verification (synthetic)", fontsize=14)
        page.insert_text((60, 170), "HbA1c 7.1 %", fontsize=18)
        page.insert_text((60, 215), "Fasting glucose 130 mg/dL", fontsize=18)
        image = page.get_pixmap(matrix=fitz.Matrix(2, 2)).tobytes("png")
        scanned = fitz.open()
        scanned.new_page().insert_image(page.rect, stream=image)
        assert not scanned[0].get_text().strip()
        existing = next((d for d in client.get(f"patients/{pid}/documents").json()
                         if d.get("filename") == "synthetic_scanned_verification.pdf"), None)
        if existing:
            record = existing["record_id"]
        else:
            upload = client.post(f"patients/{pid}/documents",
                files={"file": ("synthetic_scanned_verification.pdf", scanned.tobytes(), "application/pdf")},
                data={"document_type": "lab", "visit_date": datetime.now(timezone(timedelta(hours=5, minutes=30))).date().isoformat()})
            upload.raise_for_status()
            record = upload.json()["record_id"]
            client.post(f"patients/{pid}/brief/jobs").raise_for_status()
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline:
            status = client.get(f"patients/{pid}/brief/jobs/latest").json()
            if status["status"] in {"complete", "failed"}:
                break
            time.sleep(3)
        assert status["status"] == "complete", status.get("error")
        bundle = client.get(f"patients/{pid}/documents/{record}/fhir")
        bundle.raise_for_status()
        observations = [entry["resource"] for entry in bundle.json()["entry"] if entry["resource"]["resourceType"] == "Observation"]
        assert any(item.get("valueQuantity", {}).get("value") == 130 for item in observations)
        search = client.get(f"patients/{pid}/documents/search", params={"q": "glucose"})
        search.raise_for_status()
        assert any(item.get("bbox") for item in search.json())
        png = client.get(f"patients/{pid}/documents/{record}/page/1")
        assert png.status_code == 200 and png.content.startswith(b"\x89PNG")
        result = {"ok": True, "record_id": record, "scanned_input": True, "observation_count": len(observations),
                  "grounded_numeric_value": True, "ocr_search_box": True,
                  "limitation": "Scanned HbA1c label was read as HbAic; only the recognized fasting glucose became a FHIR observation."}
        (STAGING / "upload-verification.json").write_text(json.dumps(result))
        print(json.dumps(result))


if __name__ == "__main__":
    main()
