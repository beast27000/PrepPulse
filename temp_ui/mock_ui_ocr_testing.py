from __future__ import annotations

import argparse
import json
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

import fitz
from PIL import Image, ImageTk

from preppulse_ocr.database import (
    ManifestDocument,
    SqliteStore,
    ingest_document,
    selected_documents,
)

# ---------- local Tkinter review application ----------

class ReviewApplication(tk.Tk):
    """Visual desktop UI to inspect OCR documents, evidence anchors, and bounding boxes."""

    def __init__(self, selection_path: Path, corpus_root: Path, output_root: Path, database_path: Path) -> None:
        super().__init__()
        self.title("PrepPulse OCR Review & Testing UI")
        self.geometry("1460x900")
        self.selection_path = selection_path
        self.corpus_root = corpus_root
        self.output_root = output_root
        self.store = SqliteStore(database_path)
        self.documents = selected_documents(selection_path)
        self.by_patient: dict[str, list[ManifestDocument]] = {}
        for doc in self.documents:
            self.by_patient.setdefault(doc.patient_id, []).append(doc)
        self.current_document: ManifestDocument | None = None
        self.current_rows = []
        self.preview_image: ImageTk.PhotoImage | None = None
        self._build_widgets()
        self._load_patients()

    def _build_widgets(self) -> None:
        # /3 build three-pane horizontal layout: patients, source document, and OCR evidence
        root = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        root.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        left = ttk.Frame(root, width=340)
        middle = ttk.Frame(root, width=690)
        right = ttk.Frame(root, width=390)
        root.add(left, weight=1)
        root.add(middle, weight=3)
        root.add(right, weight=2)

        # /3 left pane: patient selection and batch process trigger
        ttk.Label(left, text="Patients (75 automatic + 18 manual)", font=("Segoe UI", 11, "bold")).pack(anchor=tk.W)
        self.patient_list = tk.Listbox(left, exportselection=False)
        self.patient_list.pack(fill=tk.BOTH, expand=True, pady=(4, 8))
        self.patient_list.bind("<<ListboxSelect>>", self._on_patient)
        ttk.Button(left, text="Process selected patient", command=self._process_patient).pack(fill=tk.X)

        # /3 middle pane: document list and source image preview canvas
        ttk.Label(middle, text="Source document", font=("Segoe UI", 11, "bold")).pack(anchor=tk.W)
        self.document_list = tk.Listbox(middle, height=7, exportselection=False)
        self.document_list.pack(fill=tk.X, pady=(4, 8))
        self.document_list.bind("<<ListboxSelect>>", self._on_document)
        self.canvas = tk.Canvas(middle, background="#eef2f7", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # /3 right pane: evidence anchor list and status
        ttk.Label(right, text="OCR source evidence", font=("Segoe UI", 11, "bold")).pack(anchor=tk.W)
        ttk.Label(right, text="Select a line or table cell to highlight it on the source page.", wraplength=360).pack(anchor=tk.W, pady=(2, 6))
        self.anchor_list = tk.Listbox(right, exportselection=False)
        self.anchor_list.pack(fill=tk.BOTH, expand=True)
        self.anchor_list.bind("<<ListboxSelect>>", self._highlight_anchor)
        self.status = tk.StringVar(value="Select a patient. Manual patients can be processed from this window.")
        ttk.Label(right, textvariable=self.status, wraplength=360).pack(anchor=tk.W, pady=(8, 0))

    def _load_patients(self) -> None:
        # /3 populate patient listbox with cohort indicator tags
        for patient_id in self.by_patient:
            cohort = self.by_patient[patient_id][0].row.get("cohort", "manual")
            marker = "AUTO" if cohort == "automatic" else "MANUAL"
            self.patient_list.insert(tk.END, f"[{marker}] {patient_id}")

    def _selected_patient_id(self) -> str | None:
        selection = self.patient_list.curselection()
        return list(self.by_patient)[selection[0]] if selection else None

    def _on_patient(self, _event: object = None) -> None:
        # /3 update document list with status icons when patient is selected
        patient_id = self._selected_patient_id()
        if not patient_id:
            return
        self.document_list.delete(0, tk.END)
        for doc in self.by_patient[patient_id]:
            marker = "✓" if self.store.is_ingested(doc.doc_id) else "○"
            self.document_list.insert(tk.END, f"{marker} {doc.kind}: {doc.doc_id}")
        self.anchor_list.delete(0, tk.END)
        self.canvas.delete("all")
        self.status.set("Choose a document. ○ documents can be processed with the patient button.")

    def _on_document(self, _event: object = None) -> None:
        # /3 render selected document page and load evidence anchors
        patient_id = self._selected_patient_id()
        selection = self.document_list.curselection()
        if not patient_id or not selection:
            return
        self.current_document = self.by_patient[patient_id][selection[0]]
        self._render_current_document()

    def _process_patient(self) -> None:
        # /3 run OCR pipeline on all unparsed documents for current patient
        patient_id = self._selected_patient_id()
        if not patient_id:
            messagebox.showinfo("PrepPulse", "Choose a patient first.")
            return
        processed = 0
        errors: list[str] = []
        for doc in self.by_patient[patient_id]:
            if self.store.is_ingested(doc.doc_id):
                continue
            try:
                ingest_document(doc, self.corpus_root, self.output_root, self.store)
                processed += 1
            except Exception as error:  # noqa: BLE001 - report per-document OCR error
                errors.append(f"{doc.doc_id}: {error}")
        self._on_patient()
        if errors:
            messagebox.showerror("OCR could not finish", "\n".join(errors))
        else:
            self.status.set(f"Processed {processed} document(s) for {patient_id}.")

    def _render_current_document(self) -> None:
        # /3 render page 1 of source PDF or image to canvas with scaled preview
        assert self.current_document is not None
        doc = self.current_document
        if not self.store.is_ingested(doc.doc_id):
            self.canvas.delete("all")
            self.canvas.create_text(340, 180, text="Not processed yet.\nClick 'Process selected patient'.", font=("Segoe UI", 14), fill="#4b5563")
            self.anchor_list.delete(0, tk.END)
            return
        source = self.corpus_root / doc.file
        try:
            if source.suffix.lower() == ".pdf":
                pdf = fitz.open(source)
                page = pdf[0]
                pixmap = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
                image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
                pdf.close()
            else:
                with Image.open(source) as raw:
                    image = raw.convert("RGB")
            image.thumbnail((680, 690))
            self.preview_image = ImageTk.PhotoImage(image)
            self.canvas.delete("all")
            self.canvas.create_image(0, 0, image=self.preview_image, anchor=tk.NW, tags="page")
            self.canvas.configure(scrollregion=(0, 0, image.width, image.height))
        except Exception as error:  # noqa: BLE001 - keep UI usable on unreadable source
            self.status.set(f"Could not render source: {error}")
            return
        self.current_rows = self.store.anchors_for_page(doc.doc_id, 1)
        self.anchor_list.delete(0, tk.END)
        for row in self.current_rows:
            text = row["text"].replace("\n", " ")
            self.anchor_list.insert(tk.END, f"{row['anchor_type']}: {text[:90]}")
        self.status.set(f"{len(self.current_rows)} evidence anchors on page 1. Click one to highlight it.")

    def _highlight_anchor(self, _event: object = None) -> None:
        # /3 draw red bounding box rectangle on canvas using normalized coordinates
        selection = self.anchor_list.curselection()
        if not selection or self.preview_image is None:
            return
        bbox = json.loads(self.current_rows[selection[0]]["bbox_json"])
        width, height = self.preview_image.width(), self.preview_image.height()
        self.canvas.delete("highlight")
        self.canvas.create_rectangle(
            bbox["x0"] * width / 1000, bbox["y0"] * height / 1000,
            bbox["x1"] * width / 1000, bbox["y1"] * height / 1000,
            outline="#e53935", width=3, tags="highlight",
        )

    def destroy(self) -> None:
        # /3 close database connection upon window destruction
        self.store.close()
        super().destroy()


# ---------- CLI runner ----------

def main() -> None:
    # /3 parse CLI paths with fallback defaults pointing to standard pack93 locations
    repo_root = Path(__file__).resolve().parent.parent
    default_selection = repo_root / "data" / "active" / "pack93" / "selected_manifest.jsonl"
    default_corpus = repo_root / "data" / "active" / "pack93"
    default_output = repo_root / "data" / "outputs" / "ocr_json"
    default_database = repo_root / "data" / "outputs" / "preppulse_ocr.sqlite"

    parser = argparse.ArgumentParser(description="PrepPulse OCR testing & review UI.")
    parser.add_argument("--selection", type=Path, default=default_selection)
    parser.add_argument("--corpus-root", type=Path, default=default_corpus)
    parser.add_argument("--output-root", type=Path, default=default_output)
    parser.add_argument("--database", type=Path, default=default_database)
    args = parser.parse_args()

    ReviewApplication(
        selection_path=args.selection,
        corpus_root=args.corpus_root,
        output_root=args.output_root,
        database_path=args.database,
    ).mainloop()


if __name__ == "__main__":
    main()
