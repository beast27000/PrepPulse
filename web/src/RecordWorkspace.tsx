import { useEffect, useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, FileText, Search, X } from "lucide-react";
import { Citation, Doc, Patient, request } from "./api";
import "./record-workspace.css";

type PageHit = {
  document_id: string;
  document_title: string;
  page_number: number;
  snippet: string;
  bbox: number[] | null;
};

export default function RecordWorkspace({
  patient,
  documents,
  citation,
  onClose,
}: {
  patient: Patient;
  documents: Doc[];
  citation: Citation | null;
  onClose: () => void;
}) {
  const [recordId, setRecordId] = useState(
    citation?.document_id || documents[0]?.record_id || "",
  );
  const [page, setPage] = useState(citation?.page_number || 1);
  const [box, setBox] = useState<number[] | null>(
    citation?.source_verified ? citation.bbox : null,
  );
  const [term, setTerm] = useState("");
  const [results, setResults] = useState<PageHit[]>([]);
  const [searching, setSearching] = useState(false);
  const [imageError, setImageError] = useState(false);
  const record = documents.find((item) => item.record_id === recordId);
  const visibleDocuments = useMemo(
    () =>
      documents.filter((item) =>
        item.filename.toLowerCase().includes(term.toLowerCase()),
      ),
    [documents, term],
  );
  useEffect(() => {
    if (citation?.document_id) {
      setRecordId(citation.document_id);
      setPage(citation.page_number || 1);
      setBox(citation.source_verified ? citation.bbox : null);
    }
  }, [citation?.document_id, citation?.page_number, citation?.bbox]);
  useEffect(() => setImageError(false), [recordId, page]);
  useEffect(() => {
    if (term.trim().length < 2) {
      setResults([]);
      return;
    }
    let active = true;
    const timer = setTimeout(async () => {
      setSearching(true);
      try {
        const found = await request<PageHit[]>(
          `/patients/${patient.patient_id}/documents/search?q=${encodeURIComponent(term.trim())}`,
        );
        if (active) setResults(found);
      } catch {
        if (active) setResults([]);
      } finally {
        if (active) setSearching(false);
      }
    }, 250);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [patient.patient_id, term]);

  function selectRecord(
    id: string,
    nextPage = 1,
    nextBox: number[] | null = null,
  ) {
    setRecordId(id);
    setPage(nextPage);
    setBox(nextBox);
  }
  const precise =
    box && box.length === 4 && (box[2] - box[0]) * (box[3] - box[1]) <= 100_000;
  return (
    <div className="record-workspace-page">
      <div className="page-intro">
        <div>
          <div className="eyebrow teal">SOURCE RECORDS</div>
          <h1>Record workspace</h1>
          <p>{patient.name} · Search documents and inspect original pages.</p>
        </div>
        <button className="secondary" onClick={onClose}>
          <X size={16} /> Back to workspace
        </button>
      </div>
      <div className="record-workspace-grid">
        <section className="panel record-viewer">
          <div className="record-viewer-toolbar">
            <div>
              <span className="eyebrow teal">ORIGINAL DOCUMENT</span>
              <h3>{record?.filename || "Choose a record"}</h3>
              <p>{record?.status || ""}</p>
            </div>
            <div className="record-page-controls">
              <button
                aria-label="Previous page"
                disabled={page <= 1}
                onClick={() => {
                  setPage(page - 1);
                  setBox(null);
                }}
              >
                <ChevronLeft size={18} />
              </button>
              <span>
                Page {page} of {record?.page_count || 1}
              </span>
              <button
                aria-label="Next page"
                disabled={!record || page >= (record.page_count || 1)}
                onClick={() => {
                  setPage(page + 1);
                  setBox(null);
                }}
              >
                <ChevronRight size={18} />
              </button>
            </div>
          </div>
          {record && !imageError ? (
            <div className="record-page-wrap">
              <div className="record-page-image">
                <img
                  key={`${record.record_id}-${page}`}
                  alt={`Page ${page} of ${record.filename}`}
                  src={`/api/patients/${patient.patient_id}/documents/${record.record_id}/page/${page}`}
                  onError={() => setImageError(true)}
                />
                {precise && (
                  <span
                    className="proof-highlight"
                    style={{
                      left: `${box[0] / 10}%`,
                      top: `${box[1] / 10}%`,
                      width: `${(box[2] - box[0]) / 10}%`,
                      height: `${(box[3] - box[1]) / 10}%`,
                    }}
                  />
                )}
              </div>
            </div>
          ) : (
            <p className="record-viewer-empty">
              {imageError
                ? "This page is unavailable."
                : "Select a document on the right."}
            </p>
          )}
          {citation?.document_id === recordId && !precise && (
            <p className="record-evidence-note">
              This citation needs a new analysis for a precise highlight. You
              can still inspect the original page.
            </p>
          )}
        </section>
        <aside className="panel record-file-rail">
          <label className="record-search-label">
            <Search size={17} />
            <input
              aria-label="Search patient records"
              placeholder="Search files and record text"
              value={term}
              onChange={(event) => setTerm(event.target.value)}
            />
          </label>
          {term.trim().length >= 2 && (
            <div className="record-search-results">
              <h3>
                {searching ? "Searching…" : `${results.length} text matches`}
              </h3>
              {results.map((hit, index) => (
                <button
                  key={`${hit.document_id}-${hit.page_number}-${index}`}
                  onClick={() =>
                    selectRecord(hit.document_id, hit.page_number, hit.bbox)
                  }
                >
                  <strong>
                    {hit.document_title} · page {hit.page_number}
                  </strong>
                  <span>{hit.snippet || "Filename match"}</span>
                </button>
              ))}
              {!searching && !results.length && (
                <p>No text matches in processed records.</p>
              )}
            </div>
          )}
          <h3>Patient files · {documents.length}</h3>
          <div className="record-file-list">
            {(visibleDocuments.length ? visibleDocuments : documents).map(
              (item) => (
                <button
                  key={item.record_id}
                  className={item.record_id === recordId ? "active" : ""}
                  onClick={() => selectRecord(item.record_id)}
                >
                  <FileText size={17} />
                  <span>
                    <strong>{item.filename}</strong>
                    <small>
                      {item.visit_date || "Date unavailable"} ·{" "}
                      {item.page_count || 1} pages · {item.status}
                    </small>
                  </span>
                </button>
              ),
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}
