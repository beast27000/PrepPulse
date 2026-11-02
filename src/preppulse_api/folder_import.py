"""Import one browser-selected patient folder into private PrepPulse storage."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import date
from pathlib import Path, PurePosixPath

from fastapi import HTTPException, UploadFile
from pymongo.errors import DuplicateKeyError

from preppulse_api.config import PRIVATE_ROOT
from preppulse_api.store import WorkspaceStore, new_id, now

CLINICAL_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}
FOLDER_NAME = re.compile(r"^([A-Za-z0-9][A-Za-z0-9-]{1,31})_([A-Za-z0-9][A-Za-z0-9_ -]{1,127})$")
MAX_FILES = 1000
MAX_FILE_BYTES = 30 * 1024 * 1024
MAX_FOLDER_BYTES = 250 * 1024 * 1024


def checked_paths(paths: list[str]) -> tuple[str, str, str, list[PurePosixPath]]:
    if not paths or len(paths) > MAX_FILES:
        raise HTTPException(400, "Choose one patient folder containing 1–1000 files")
    parsed: list[PurePosixPath] = []
    roots: set[str] = set()
    seen: set[str] = set()
    for raw in paths:
        if not raw or "\\" in raw or ":" in raw or raw.startswith("/"):
            raise HTTPException(400, "Invalid folder path")
        path = PurePosixPath(raw)
        if len(path.parts) < 2 or any(part in {"", ".", ".."} for part in path.parts):
            raise HTTPException(400, "Each file must be inside one patient folder")
        if str(path).casefold() in seen:
            raise HTTPException(400, "Duplicate file path in selection")
        seen.add(str(path).casefold())
        roots.add(path.parts[0])
        parsed.append(path)
    if len(roots) != 1:
        raise HTTPException(400, "Select exactly one patient folder")
    folder = roots.pop()
    match = FOLDER_NAME.fullmatch(folder)
    if not match:
        raise HTTPException(
            400, "Folder name must be ID_Patient_Name, for example PP001_Ananya_Baruah"
        )
    return folder, match[1], match[2].replace("_", " ").strip(), parsed


def _manifest(stage: Path) -> dict:
    path = stage / "manifest.json"
    if not path.is_file():
        return {}
    if path.stat().st_size > 1024 * 1024:
        raise HTTPException(400, "Manifest exceeds 1 MB")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, ValueError):
        raise HTTPException(400, "Invalid manifest.json") from None
    if not isinstance(value, dict):
        raise HTTPException(400, "Manifest must be a JSON object")
    return value


def _document_details(relative: str, manifest: dict) -> tuple[str, str | None]:
    filename = PurePosixPath(relative).name
    records = manifest.get("records")
    if not isinstance(records, list):
        records = []
    record = next(
        (
            row
            for row in records
            if isinstance(row, dict) and (row.get("file") or row.get("filename")) == relative
        ),
        {},
    )
    kind = record.get("type") or "consult"
    visit_date = record.get("date")
    if not visit_date:
        found = re.search(r"(?:19|20)\d{2}-\d{2}-\d{2}", filename)
        visit_date = found.group() if found else None
    if visit_date:
        try:
            date.fromisoformat(visit_date)
        except ValueError:
            visit_date = None
    return kind, visit_date


async def save_patient_folder(
    store: WorkspaceStore, doctor_id: str, files: list[UploadFile], paths: list[str]
) -> dict:
    if len(files) != len(paths):
        raise HTTPException(400, "File list and relative paths do not match")
    folder, external_id, patient_name, relative_paths = checked_paths(paths)
    existing_folder = store.db.patient_aliases.find_one({"alias": folder})
    existing_short = store.db.patient_aliases.find_one({"alias": external_id})
    if (
        existing_folder
        and existing_short
        and existing_folder["patient_id"] != existing_short["patient_id"]
    ):
        raise HTTPException(409, "Folder ID is assigned to a different patient")
    if not existing_folder and existing_short:
        raise HTTPException(409, "Folder ID already belongs to a different patient")

    import_id = new_id("IMP")
    root = PRIVATE_ROOT.resolve()
    stage = root / "_staging" / import_id
    stage.mkdir(parents=True, exist_ok=False)
    staged: list[tuple[PurePosixPath, Path, str, int]] = []
    total = 0
    try:
        for upload, relative in zip(files, relative_paths, strict=True):
            destination = stage.joinpath(*relative.parts[1:]).resolve()
            if not destination.is_relative_to(stage):
                raise HTTPException(400, "Invalid folder path")
            destination.parent.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256()
            size = 0
            with destination.open("xb") as output:
                while chunk := await upload.read(1024 * 1024):
                    size += len(chunk)
                    total += len(chunk)
                    if size > MAX_FILE_BYTES or total > MAX_FOLDER_BYTES:
                        raise HTTPException(
                            413, "Folder exceeds the 30 MB per-file or 250 MB total limit"
                        )
                    digest.update(chunk)
                    output.write(chunk)
            staged.append((relative, destination, digest.hexdigest(), size))

        manifest = _manifest(stage)
        patient = store.patient(existing_folder["patient_id"]) if existing_folder else None
        created = False
        if not patient:
            patient_id = new_id("PRP")
            dob = manifest.get("dob")
            try:
                if dob:
                    date.fromisoformat(dob)
            except (TypeError, ValueError):
                dob = None
            patient = {
                "patient_id": patient_id,
                "name": patient_name,
                "name_search": patient_name.lower(),
                "dob": dob,
                "sex": manifest.get("sex"),
                "external_aliases": [external_id, folder],
                "created_at": now(),
            }
            try:
                store.db.patients.insert_one(patient)
                store.db.patient_aliases.insert_many(
                    [{"alias": alias, "patient_id": patient_id} for alias in (external_id, folder)]
                )
            except DuplicateKeyError:
                raise HTTPException(
                    409, "Patient alias was registered during upload; retry"
                ) from None
            created = True
        patient_id = patient["patient_id"]
        store.db.patient_access.update_one(
            {"patient_id": patient_id, "doctor_id": doctor_id},
            {"$setOnInsert": {"patient_id": patient_id, "doctor_id": doctor_id}},
            upsert=True,
        )
        saved = 0
        clinical = 0
        for relative, staged_path, digest, size in staged:
            rel = str(PurePosixPath(*relative.parts[1:]))
            if store.db.workspace_files.find_one(
                {"patient_id": patient_id, "relative_path": rel, "sha256": digest}
            ):
                continue
            file_id = new_id("FIL")
            destination = root / patient_id / "folder_uploads" / import_id / Path(rel)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(staged_path), str(destination))
            store.db.workspace_files.insert_one(
                {
                    "file_id": file_id,
                    "patient_id": patient_id,
                    "folder_alias": folder,
                    "relative_path": rel,
                    "source_path": str(destination),
                    "sha256": digest,
                    "size": size,
                    "created_at": now(),
                }
            )
            saved += 1
            if destination.suffix.lower() in CLINICAL_EXTENSIONS:
                kind, visit_date = _document_details(rel, manifest)
                store.db.workspace_documents.insert_one(
                    {
                        "record_id": new_id("DOC"),
                        "file_id": file_id,
                        "patient_id": patient_id,
                        "filename": destination.name,
                        "source_path": str(destination),
                        "relative_path": rel,
                        "document_type": kind,
                        "visit_date": visit_date,
                        "status": "pending",
                        "created_at": now(),
                        "size": size,
                    }
                )
                clinical += 1
        return {
            "patient_id": patient_id,
            "patient_name": patient["name"],
            "external_id": external_id,
            "folder_alias": folder,
            "patient_created": created,
            "files_selected": len(files),
            "files_saved": saved,
            "documents_queued": clinical,
            "files_unchanged": len(files) - saved,
        }
    finally:
        shutil.rmtree(stage, ignore_errors=True)
