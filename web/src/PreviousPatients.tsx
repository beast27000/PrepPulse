import { useState } from "react";
import { Patient, Visit, request } from "./api";
type Row = {
  patient: Patient;
  visits: Visit[];
  appointments: {
    appointment_id: string;
    date: string;
    time: string;
    visit_id?: string;
  }[];
};
export default function PreviousPatients({
  onOpen,
}: {
  onOpen: (p: Patient, visitId?: string) => void;
}) {
  const [q, setQ] = useState("");
  const [day, setDay] = useState("");
  const [rows, setRows] = useState<Row[]>([]);
  const [searched, setSearched] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <>
      <div className="intro">
        <div>
          <div className="eyebrow teal">HISTORICAL WORKSPACE</div>
          <h1>Previous patients</h1>
          <p>
            Find an assigned patient or past visit, then open the complete
            record-review workspace.
          </p>
        </div>
      </div>
      <section className="panel admin-form">
        <form
          className="history-tools"
          onSubmit={async (e) => {
            e.preventDefault();
            if (!q.trim() && !day) return;
            setBusy(true);
            try {
              setRows(
                await request<Row[]>(
                  `/previous-patients?q=${encodeURIComponent(q)}${day ? `&on=${day}` : ""}`,
                ),
              );
              setSearched(true);
              setError("");
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <label>
            Patient name or ID
            <input
              aria-label="Previous patient name or ID"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Name, PrepPulse ID or folder ID"
            />
          </label>
          <label>
            Visit or appointment date
            <input
              aria-label="Previous patient visit date"
              type="date"
              value={day}
              onChange={(e) => setDay(e.target.value)}
            />
          </label>
          <button className="primary" disabled={busy || (!q.trim() && !day)}>
            {busy ? "Searching…" : "Find previous patients"}
          </button>
        </form>
        {error && (
          <p role="alert" className="care-error">
            {error}
          </p>
        )}
        {!searched && (
          <p>
            Enter a name, ID or date to begin. No patient is selected
            automatically.
          </p>
        )}
      </section>
      {rows.map((row) => (
        <section
          className="panel admin-form previous-patient-card"
          key={row.patient.patient_id}
        >
          <div className="panel-heading">
            <div>
              <h3>{row.patient.name}</h3>
              <p>
                {row.patient.patient_id} ·{" "}
                {row.patient.external_aliases?.join(" · ")}
              </p>
            </div>
            <button className="secondary" onClick={() => onOpen(row.patient)}>
              Open patient history
            </button>
          </div>
          {row.visits.map((v) => (
            <div className="record-row" key={v.visit_id}>
              <button
                className="text-button"
                onClick={() => onOpen(row.patient, v.visit_id)}
              >
                Patient visit · {new Date(v.started_at).toLocaleString()} ·{" "}
                {v.status}
              </button>
            </div>
          ))}
          {row.appointments.map((a) => (
            <div className="record-row" key={a.appointment_id}>
              <span>
                {a.date} · {a.time}
              </span>
              <button
                className="text-button"
                onClick={() => onOpen(row.patient, a.visit_id)}
              >
                Open appointment's patient record
              </button>
            </div>
          ))}
        </section>
      ))}
      {searched && !rows.length && (
        <section className="panel empty-page">
          No assigned patient or visit matches these filters.
        </section>
      )}
    </>
  );
}
