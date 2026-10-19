"""Build a small, reproducible, Git-ignored OCR corpus from delivery archives."""

from __future__ import annotations

import argparse
import json
import shutil
import zipfile
from pathlib import Path

from .manifest import load_manifest, select_complete_packs, write_manifest_rows

ARCHIVE_BY_FORM = {
    "digital_pdf": "preppulse_docs_text_digital_pdf.zip",
    "scanned_pdf": "preppulse_docs_OCR_scanned_pdf.zip",
    "scanned_image": "preppulse_docs_OCR_scanned_images.zip",
    "hybrid_pdf": "preppulse_docs_hybrid_pdf.zip",
    "handwritten_note": "preppulse_docs_OCR_handwritten.zip",
}


def build_pack(
    manifest_path: Path, records_dir: Path, archives_dir: Path, output_root: Path, automatic_patients: int = 75,
) -> dict[str, int]:
    """Create an active 93-patient pack without deleting the delivery archives."""
    all_documents = load_manifest(manifest_path)
    packs = select_complete_packs(all_documents)
    if len(packs) != 93:
        raise ValueError(f"Expected 93 complete packs, found {len(packs)}")

    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)
    selected_manifest = output_root / "selected_manifest.jsonl"
    selected_patient_ids = list(packs)
    automatic_ids = set(selected_patient_ids[:automatic_patients])

    archive_members: dict[str, set[str]] = {}
    archive_handles: dict[str, zipfile.ZipFile] = {}
    try:
        for form, filename in ARCHIVE_BY_FORM.items():
            archive_path = archives_dir / filename
            archive = zipfile.ZipFile(archive_path)
            archive_handles[form] = archive
            archive_members[form] = set(archive.namelist())

        for patient_id, documents in packs.items():
            cohort = "automatic" if patient_id in automatic_ids else "manual"
            write_manifest_rows(selected_manifest, documents, cohort)
            record_source = records_dir / f"{patient_id}.json"
            if record_source.is_file():
                record_target = output_root / "records" / record_source.name
                record_target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(record_source, record_target)
            for document in documents:
                archive = archive_handles[document.form]
                if document.file not in archive_members[document.form]:
                    raise FileNotFoundError(f"{document.file} missing from {ARCHIVE_BY_FORM[document.form]}")
                target = output_root / document.file
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(document.file) as source, target.open("wb") as destination:
                    shutil.copyfileobj(source, destination)
    finally:
        for archive in archive_handles.values():
            archive.close()

    summary = {
        "complete_patients": len(packs),
        "documents": len(packs) * 4,
        "automatic_patients": len(automatic_ids),
        "manual_patients": len(packs) - len(automatic_ids),
    }
    (output_root / "selection_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the clean 93-patient PrepPulse OCR pack.")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--records-dir", type=Path, required=True)
    parser.add_argument("--archives-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--automatic-patients", type=int, default=75)
    args = parser.parse_args()
    print(json.dumps(
        build_pack(
            manifest_path=args.manifest,
            records_dir=args.records_dir,
            archives_dir=args.archives_dir,
            output_root=args.output,
            automatic_patients=args.automatic_patients,
        ),
        indent=2,
    ))


if __name__ == "__main__":
    main()
