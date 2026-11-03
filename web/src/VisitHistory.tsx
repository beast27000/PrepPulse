import { useEffect, useState } from "react";
import { Appointment, Brief, Citation, Patient, Visit, request } from "./api";
import CareWorkspace from "./CareWorkspace";
import BriefHistory from "./BriefHistory";

export function AppointmentHistory({
  onOpen,
}: {
  onOpen?: (a: Appointment) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [scope, setScope] = useState("past");
  const [q, setQ] = useState("");
  const [on, setOn] = useState("");
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<{
    appointments: Appointment[];
    total: number;
  }>({ appointments: [], total: 0 });
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    const timer = setTimeout(() => {
      request<typeof data>(
        `/appointment-history?scope=${scope}&q=${encodeURIComponent(q)}${on ? `&on=${on}` : ""}&offset=${offset}`,
      )
        .then((x) => {
          if (active) {
            setData(x);
            setError("");
          }
        })
        .catch((e) => {
          if (active) setError(e.message);
        });
    }, 180);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [scope, q, on, offset]);
  return (
    <section
      className={
        "panel admin-form appointment-history " +
        (expanded ? "history-expanded" : "")
      }
    >
      <div className="panel-heading">
        <h3>Previous appointments</h3>
        <button className="secondary" onClick={() => setExpanded(!expanded)}>
          {expanded ? "Close expanded view" : "Expand appointments"}
        </button>
      </div>
      <div className="history-tools">
        <input
          aria-label="Search appointment history"
          placeholder="Patient name or either ID"
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setScope(e.target.value ? "all" : "past");
            setOffset(0);
          }}
        />
        <input
          aria-label="Appointment history date"
          type="date"
          value={on}
          onChange={(e) => {
            setOn(e.target.value);
            setOffset(0);
          }}
        />
        <select
          aria-label="Appointment period"
          value={scope}
          onChange={(e) => {
            setScope(e.target.value);
            setOffset(0);
          }}
        >
          <option value="past">Previous appointments</option>
          <option value="today">Today's appointments</option>
          <option value="all">All dates</option>
        </select>
        <button
          className="text-button"
          onClick={() => {
            setQ("");
            setOn("");
            setScope("past");
            setOffset(0);
          }}
        >
          Clear filters
        </button>
      </div>
      {error && <p role="alert">{error}</p>}
      {data.appointments.map((a) => (
        <div className="appointment-row" key={a.appointment_id}>
          <time>
            {a.date}
            <br />
            {a.time}
          </time>
          <div>
            <strong>{a.patient_name}</strong>
            <small>
              {a.patient_id} · {a.status}
            </small>
            <small>{a.reason}</small>
          </div>
          {onOpen && (
            <button className="text-button" onClick={() => onOpen(a)}>
              Open visit / patient
            </button>
          )}
        </div>
      ))}
      {!data.appointments.length && <p>No appointments match these filters.</p>}
      <div className="form-actions">
        <button
          className="secondary"
          disabled={!offset}
          onClick={() => setOffset(Math.max(0, offset - 50))}
        >
          Previous
        </button>
        <span>
          {Math.min(offset + 1, data.total)}–{Math.min(offset + 50, data.total)}{" "}
          of {data.total}
        </span>
        <button
          className="secondary"
          disabled={offset + 50 >= data.total}
          onClick={() => setOffset(offset + 50)}
        >
          Next
        </button>
      </div>
    </section>
  );
}

type Snapshot = {
  visit: Visit;
  plan: {
    pathway_id: string;
    approved_at: string;
    approved_name?: string;
    doctor_notes: string;
    mode: string;
    items: { text: string }[];
  } | null;
  snapshot_available: boolean;
  patient_snapshot: Patient | null;
  brief_snapshot: Brief | null;
};
export default function VisitHistory({
  patient,
  visits,
  onRecords,
  onEvidence,
  initialVisit,
}: {
  patient: Patient;
  visits: Visit[];
  onRecords: () => void;
  onEvidence: (source: Citation) => void;
  initialVisit?: string;
}) {
  const [visitId, setVisitId] = useState(initialVisit || "");
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    setVisitId(initialVisit || "");
    setSnapshot(null);
    setError("");
  }, [patient.patient_id, initialVisit]);
  useEffect(() => {
    if (!visitId) {
      setSnapshot(null);
      return;
    }
    let active = true;
    setSnapshot(null);
    request<Snapshot>(
      `/patients/${patient.patient_id}/visit-records/${visitId}`,
    )
      .then((x) => {
        if (active) {
          setSnapshot(x);
          setError("");
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [patient.patient_id, visitId]);
  return (
    <section className="panel pathway-panel">
      <div className="panel-heading">
        <div>
          <div className="eyebrow teal">VISITS AND RECORDS</div>
          <h3>{patient.name}</h3>
        </div>
        <button className="secondary" onClick={onRecords}>
          Browse patient records
        </button>
      </div>
      <details>
        <summary>Patient records</summary>
        <p>
          Browse every uploaded source and previous caregiver pathway in the
          full record workspace.
        </p>
        <button className="secondary" onClick={onRecords}>
          Open records workspace
        </button>
      </details>
      <h4>Previous visits</h4>
      {visits.map((visit, i) => (
        <div className="record-row" key={visit.visit_id}>
          <button
            className="text-button"
            onClick={() => setVisitId(visit.visit_id)}
          >
            Patient visit {visits.length - i} ·{" "}
            {new Date(visit.started_at).toLocaleString()} · {visit.status}
          </button>
        </div>
      ))}
      {!visits.length && <p>No visits have been recorded.</p>}
      {error && (
        <p className="care-error" role="alert">
          {error}
        </p>
      )}
      {snapshot && (
        <div className="visit-snapshot">
          <h3>
            Visit record ·{" "}
            {new Date(snapshot.visit.started_at).toLocaleDateString()}
          </h3>
          <p>
            {snapshot.patient_snapshot?.name || patient.name} ·{" "}
            {snapshot.patient_snapshot?.sex || "Sex not recorded"} ·{" "}
            {snapshot.visit.admitted ? "Admitted" : "Family pathway"}
          </p>
          {!snapshot.snapshot_available && (
            <p>
              Historical snapshot was not captured for this older visit. Only
              saved visit information is shown.
            </p>
          )}
          <h4>Clinician notes at sign-off</h4>
          <p>
            {snapshot.plan?.doctor_notes ||
              snapshot.visit.doctor_notes ||
              "No saved notes"}
          </p>
          {snapshot.brief_snapshot && (
            <>
              <h4>Consultation brief saved at this visit</h4>
              <p>
                {snapshot.brief_snapshot.classification?.stage} ·{" "}
                {snapshot.brief_snapshot.classification?.diagnostic_basis}
              </p>
              <div className="care-table">
                <table>
                  <thead>
                    <tr>
                      <th>Measure</th>
                      <th>Recorded value</th>
                      <th>Source</th>
                    </tr>
                  </thead>
                  <tbody>
                    {snapshot.brief_snapshot.trajectory.kpis.map((x, i) => (
                      <tr key={i}>
                        <td>{x.name}</td>
                        <td>
                          {x.value} {x.unit}
                        </td>
                        <td>
                          {x.citation && (
                            <button
                              className="text-button"
                              onClick={() => onEvidence(x.citation!)}
                            >
                              View source
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <BriefHistory
                brief={snapshot.brief_snapshot}
                onCitation={onEvidence}
              />
            </>
          )}
          {snapshot.plan && (
            <p>
              Signed pathway · {snapshot.plan.approved_at.slice(0, 10)} ·{" "}
              {snapshot.plan.approved_name || "Clinician"}. Choose this version
              below to review its instructions and caregiver follow-up.
            </p>
          )}
        </div>
      )}
      <details open={!!snapshot?.plan}>
        <summary>Previous caregiver pathways and follow-up</summary>
        <CareWorkspace
          key={`${patient.patient_id}-${snapshot?.plan?.pathway_id || "history"}`}
          patient={patient}
          role="doctor"
          historyOnly
          initialPlanId={snapshot?.plan?.pathway_id}
        />
      </details>
    </section>
  );
}
