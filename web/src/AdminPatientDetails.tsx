import { useEffect, useState } from "react";
import {
  AdminPatientOverview,
  Doc,
  Patient,
  User,
  patch,
  request,
} from "./api";
import IngestionStatus from "./IngestionStatus";

export default function AdminPatientDetails({
  patient,
  doctors,
  onClose,
  onUpdated,
  onUpload,
}: {
  patient: Patient;
  doctors: User[];
  onClose: () => void;
  onUpdated: () => void;
  onUpload: (visitId?: string, day?: string) => void;
}) {
  const [data, setData] = useState<AdminPatientOverview | null>(null);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [filter, setFilter] = useState("all");
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(patient.name);
  const [dob, setDob] = useState(patient.dob || "");
  const [age, setAge] = useState(patient.age?.toString() || "");
  const [sex, setSex] = useState(patient.sex || "");
  const [doctor, setDoctor] = useState("");
  const [record, setRecord] = useState<Doc | null>(null);
  const [preview, setPreview] = useState<Doc | null>(null);
  const [title, setTitle] = useState("");
  const [kind, setKind] = useState("");
  const [recordDay, setRecordDay] = useState("");
  const [deleting, setDeleting] = useState<"patient" | "record" | null>(null);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [confirmation, setConfirmation] = useState("");
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  async function confirmDelete(kind: "patient" | "record") {
    setDeleteError(""); setConfirmation("");
    if (kind === "patient") {
      try { setCounts((await request<{ counts: Record<string, number> }>(`/admin/patients/${patient.patient_id}/deletion-preview`)).counts); }
      catch (e) { setError((e as Error).message); return; }
    }
    setDeleting(kind);
  }
  async function load() {
    try {
      const value = await request<AdminPatientOverview>(
        `/admin/patients/${patient.patient_id}/overview`,
      );
      setData(value);
      setError("");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  useEffect(() => {
    load();
    const timer = setInterval(load, 5000);
    return () => clearInterval(timer);
  }, [patient.patient_id]);
  const dates = [
    ...new Set([
      ...(data?.appointments.map((x) => x.date) || []),
      ...(data?.visits.map((x) => x.started_at.slice(0, 10)) || []),
    ]),
  ]
    .sort()
    .reverse();
  const selectedVisit = data?.visits.find(
    (x) => x.started_at.slice(0, 10) === filter,
  );
  const visible = (data?.documents || []).filter(
    (x) =>
      filter === "all" ||
      (x.visit_id && x.visit_id === selectedVisit?.visit_id) ||
      x.visit_date === filter,
  );
  return (
    <section className="panel directory-overview">
      <div className="panel-heading">
        <div>
          <div className="eyebrow teal">ADMIN PATIENT RECORD</div>
          <h3>{data?.patient.name || patient.name}</h3>
          <p>
            {patient.patient_id} · {patient.external_aliases?.join(" · ")}
          </p>
        </div>
        <button className="secondary" onClick={onClose}>
          Close patient details
        </button>
      </div>
      {error && (
        <p className="care-error" role="alert">
          {error}
        </p>
      )}
      {status && <p role="status">{status}</p>}
      {data && (
        <>
          <div className="overview-grid">
            <div>
              <span className="overview-label">Assigned doctors</span>
              <strong>
                {data.doctors.map((x) => x.name).join(", ") || "None"}
              </strong>
            </div>
            <div>
              <span className="overview-label">
                Date of birth / recorded age / sex
              </span>
              <strong>
                {data.patient.dob ||
                  (data.patient.age != null
                    ? `${data.patient.age} years`
                    : "Not recorded")}{" "}
                · {data.patient.sex || "Not recorded"}
              </strong>
            </div>
            <div>
              <span className="overview-label">Stored records</span>
              <strong>{data.documents.length}</strong>
            </div>
            <div>
              <span className="overview-label">Processing</span>
              <strong>
                {data.latest_job
                  ? `${data.latest_job.stage || data.latest_job.status} · ${data.latest_job.documents_ready || 0}/${data.latest_job.documents_total || data.documents.length}`
                  : "No pending job"}
              </strong>
            </div>
          </div>
          {data.patient.maintenance && <p className="care-error" role="status">Patient cleanup is pending. Retry Delete patient or the selected record deletion to finish cleanup.</p>}
          {data.latest_job && <IngestionStatus job={data.latest_job} patientId={patient.patient_id} admin onRetry={job => setData({ ...data, latest_job: job })} />}
          <div className="patient-maintenance-actions"><button
            className="secondary"
            onClick={() => {
              setEditing(!editing);
              setName(data.patient.name);
              setDob(data.patient.dob || "");
              setAge(data.patient.age?.toString() || "");
              setSex(data.patient.sex || "");
              setDoctor(data.doctors[0]?.user_id || doctors[0]?.user_id || "");
            }}
          >
            Edit patient details
          </button>
          <button className="danger-button" onClick={() => confirmDelete("patient")}>Delete patient</button></div>
          {editing && (
            <form
              className="admin-form directory-edit"
              onSubmit={async (e) => {
                e.preventDefault();
                try {
                  await patch(`/patients/${patient.patient_id}/demographics`, {
                    name,
                    dob: dob || null,
                    age: !dob && age ? Number(age) : null,
                    sex: sex || null,
                    doctor_id: doctor,
                  });
                  setEditing(false);
                  setStatus("Patient details saved");
                  await load();
                  onUpdated();
                } catch (e) {
                  setError((e as Error).message);
                }
              }}
            >
              <label>
                Full name
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                />
              </label>
              <div className="form-grid">
                <label>
                  Date of birth
                  <input
                    type="date"
                    value={dob}
                    onChange={(e) => setDob(e.target.value)}
                  />
                </label>
                <label>
                  Recorded age
                  <input
                    type="number"
                    min="0"
                    max="130"
                    value={age}
                    disabled={!!dob}
                    onChange={(e) => setAge(e.target.value)}
                  />
                </label>
                <label>
                  Sex
                  <select value={sex} onChange={(e) => setSex(e.target.value)}>
                    <option value="">Not provided</option>
                    <option>Female</option>
                    <option>Male</option>
                    <option>Other</option>
                  </select>
                </label>
              </div>
              <label>
                Assigned doctor
                <select
                  value={doctor}
                  onChange={(e) => setDoctor(e.target.value)}
                  required
                >
                  {doctors.map((x) => (
                    <option key={x.user_id} value={x.user_id}>
                      {x.name}
                    </option>
                  ))}
                </select>
              </label>
              <button className="primary">Save patient details</button>
            </form>
          )}
          <div className="history-tools">
            <label>
              Records by visit date
              <select
                aria-label="Directory records by visit"
                value={filter}
                onChange={(e) => {
                  setFilter(e.target.value);
                  setPreview(null);
                }}
              >
                <option value="all">All records</option>
                {dates.map((x) => (
                  <option key={x} value={x}>
                    Previous appointment / visit · {x}
                  </option>
                ))}
              </select>
            </label>
            <button
              className="secondary"
              onClick={() =>
                onUpload(
                  selectedVisit?.visit_id,
                  filter === "all" ? undefined : filter,
                )
              }
            >
              Add record
            </button>
          </div>
          {filter !== "all" && (
            <p>
              {visible.length} records associated with {filter}. Older records
              without a visit ID are matched by their document date; this does
              not prove when they were uploaded.
            </p>
          )}
          <div className="admin-scroll-list">
            {visible.map((x) => (
              <div className="record-row" key={x.record_id}>
                <div>
                  <strong>{x.display_name || x.filename}</strong>
                  <small>
                    {x.visit_date || "Undated"} · {x.document_type} · {x.status}
                    {x.visit_id ? " · linked to visit" : ""}
                  </small>
                  {x.created_at && (
                    <small>
                      Added {new Date(x.created_at).toLocaleString()}
                    </small>
                  )}
                  {x.error && <small>{x.error}</small>}
                </div>
                <button className="text-button" onClick={() => setPreview(x)}>
                  View
                </button>
                <button
                  className="text-button"
                  onClick={() => {
                    setRecord(x);
                    setTitle(x.display_name || x.filename);
                    setKind(x.document_type);
                    setRecordDay(x.visit_date || "");
                  }}
                >
                  Edit record
                </button>
              </div>
            ))}
            {!visible.length && (
              <p>No records match this visit. You can add one here.</p>
            )}
          </div>
          {record && (
            <form
              className="admin-form directory-edit"
              onSubmit={async (e) => {
                e.preventDefault();
                try {
                  await patch(
                    `/admin/patients/${patient.patient_id}/documents/${record.record_id}`,
                    {
                      display_name: title,
                      document_type: kind,
                      visit_date: recordDay || null,
                    },
                  );
                  setRecord(null);
                  setStatus("Record metadata saved. Original file retained.");
                  await load();
                } catch (e) {
                  setError((e as Error).message);
                }
              }}
            >
              <h4>Edit record metadata</h4>
              <label>
                Display title
                <input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  required
                />
              </label>
              <div className="form-grid">
                <label>
                  Document type
                  <select
                    disabled={record.document_type === "care_pathway"}
                    value={kind}
                    onChange={(e) => setKind(e.target.value)}
                  >
                    {[
                      "consult",
                      "lab",
                      "rx",
                      "discharge",
                      "history",
                      "care_pathway",
                    ].map((x) => (
                      <option key={x}>{x}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Document date
                  <input
                    disabled={record.document_type === "care_pathway"}
                    type="date"
                    value={recordDay}
                    onChange={(e) => setRecordDay(e.target.value)}
                  />
                </label>
              </div>
              <button className="primary">Save record metadata</button>
              {record.document_type !== "care_pathway" && <button type="button" className="danger-button" onClick={() => confirmDelete("record")}>Delete record</button>}
              <button
                type="button"
                className="secondary"
                onClick={() => setRecord(null)}
              >
                Cancel edit
              </button>
            </form>
          )}
          {preview && (
            <div className="records-preview">
              <div className="panel-heading">
                <h4>{preview.display_name || preview.filename}</h4>
                <button
                  className="text-button"
                  onClick={() => setPreview(null)}
                >
                  Close preview
                </button>
              </div>
              <img
                alt={preview.filename}
                src={`/api/patients/${patient.patient_id}/documents/${preview.record_id}/page/1`}
              />
            </div>
          )}
          <details>
            <summary>Previous appointments and visit log</summary>
            {data.appointments.map((x) => (
              <p key={x.appointment_id}>
                {x.date} · {x.time} · {x.status}
              </p>
            ))}
            {data.visits.map((x) => (
              <p key={x.visit_id}>
                {new Date(x.started_at).toLocaleString()} · {x.status} ·{" "}
                {x.admitted ? "Caregiver" : "Family"} pathway
              </p>
            ))}
          </details>
        </>
      )}
      {!data && !error && <p>Loading patient details…</p>}
      {deleting && <div className="modal-backdrop"><section className="panel deletion-dialog" role="dialog" aria-modal="true" aria-label={deleting === "patient" ? "Delete patient confirmation" : "Delete record confirmation"}>
        <h3>{deleting === "patient" ? "Delete all patient information?" : "Delete this source record?"}</h3>
        <p><strong>{patient.name}</strong> · {patient.patient_id}</p>
        {deleting === "patient" ? <>
          <p>{counts.workspace_documents || 0} records · {counts.workspace_files || 0} uploaded files · {counts.visits || 0} visits · {counts.appointments || 0} appointments · {counts.pathways || 0} signed pathways</p>
          <p>This permanently removes this patient's imported files, aliases, extracted data, appointments, visits, conversations and caregiver data from the active workspace. Existing backups follow their retention schedule. Original dataset folders are retained.</p>
          <label>Type {patient.patient_id} to confirm<input autoFocus value={confirmation} onChange={e => setConfirmation(e.target.value)} /></label>
        </> : <>
          <p>{record?.display_name || record?.filename} · {record?.visit_date || "Undated"} · {record?.document_type}</p>
          <p>The imported source and extracted data will be removed. Current AI briefs and saved conversations/charts will be cleared because they may quote this source. Signed plans remain historical records. Analyze records again afterwards.</p>
        </>}
        {deleteError && <p className="care-error" role="alert">{deleteError}</p>}
        <div className="form-actions">
          <button className="secondary" disabled={deleteBusy} onClick={() => setDeleting(null)}>Cancel</button>
          <button className="danger-button" disabled={deleteBusy || (deleting === "patient" && confirmation !== patient.patient_id)} onClick={async () => {
            setDeleteBusy(true); setDeleteError("");
            try {
              await request(`/admin/patients/${patient.patient_id}${deleting === "record" ? `/documents/${record!.record_id}` : ""}`, { method: "DELETE", body: JSON.stringify({ confirm_id: deleting === "patient" ? confirmation : record!.record_id }) });
              const full = deleting === "patient";
              setDeleting(null); setRecord(null); setPreview(null);
              if (full) { onClose(); onUpdated(); } else { setStatus("Record removed. Analyze records to rebuild patient insights."); await load(); onUpdated(); }
            } catch (e) { setDeleteError((e as Error).message); }
            finally { setDeleteBusy(false); }
          }}>{deleteBusy ? "Deleting…" : deleting === "patient" ? "Permanently delete patient" : "Delete record"}</button>
        </div>
      </section></div>}
    </section>
  );
}
