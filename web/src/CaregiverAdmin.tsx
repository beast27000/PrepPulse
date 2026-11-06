import { useEffect, useState } from "react";
import { Patient, User, patch, post, request } from "./api";
import SearchSuggestions from "./SearchSuggestions";

export default function CaregiverAdmin({
  patients,
  accounts,
  setAccounts,
}: {
  patients: Patient[];
  accounts: User[];
  setAccounts: (rows: User[]) => void;
}) {
  const [caregiver, setCaregiver] = useState("");
  const [patient, setPatient] = useState("");
  const [kind, setKind] = useState("");
  const [query, setQuery] = useState("");
  const [patientQuery, setPatientQuery] = useState("");
  const [rosterQuery, setRosterQuery] = useState("");
  const [rows, setRows] = useState(patients);
  const [links, setLinks] = useState<
    { patient_id: string; caregiver_id: string; kind: string }[]
  >([]);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const caregivers = accounts.filter((x) => x.role === "caregiver");
  const matches = (x: User) =>
    [
      x.name,
      x.username,
      x.account_id,
      x.user_id,
      ...(x.account_aliases || []),
    ].some((v) => v?.toLowerCase().includes(query.trim().toLowerCase()));
  const choices = caregivers.filter(
    (x) => !x.disabled && x.caregiver_type === kind && matches(x),
  );
  useEffect(() => {
    const queryText = query.trim().toLowerCase();
    const exact = choices.filter((x) =>
      [
        x.name,
        x.username,
        x.account_id,
        x.user_id,
        ...(x.account_aliases || []),
      ].some((v) => v?.toLowerCase() === queryText),
    );
    setCaregiver(
      queryText
        ? exact.length === 1
          ? exact[0].user_id
          : choices.length === 1
            ? choices[0].user_id
            : ""
        : "",
    );
  }, [query, kind, accounts]);
  async function load() {
    try {
      setLinks(await request<typeof links>("/admin/caregiver-assignments"));
      setError("");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  useEffect(() => {
    load();
    const timer = setInterval(load, 10000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    let active = true;
    const timer = setTimeout(() => {
      request<Patient[]>(`/patients?q=${encodeURIComponent(patientQuery)}`)
        .then((x) => {
          if (active) {
            setRows(x);
            const q = patientQuery.trim().toLowerCase();
            const exact = x.filter((p) =>
              [p.name, p.patient_id, ...(p.external_aliases || [])].some(
                (v) => v.toLowerCase() === q,
              ),
            );
            setPatient(
              q
                ? exact.length === 1
                  ? exact[0].patient_id
                  : x.length === 1
                    ? x[0].patient_id
                    : ""
                : "",
            );
          }
        })
        .catch((e) => {
          if (active) setError(e.message);
        });
    }, 200);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [patientQuery]);
  return (
    <>
      <div className="intro">
        <div>
          <div className="eyebrow teal">CAREGIVER ACCESS</div>
          <h1>Caregivers</h1>
          <p>
            Assign registered caregivers. Create family and professional
            caregiver accounts in Accounts.
          </p>
        </div>
      </div>
      <div className="admin-grid">
        <section className="panel admin-form">
          <h3>Patient access</h3>
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              try {
                await post("/admin/caregiver-assignments", {
                  patient_id: patient,
                  caregiver_id: caregiver,
                  kind,
                });
                setStatus("Patient assignment saved");
                await load();
              } catch (e) {
                setError((e as Error).message);
              }
            }}
          >
            <label>
              Caregiver type
              <select
                required
                value={kind}
                onChange={(e) => {
                  setKind(e.target.value);
                  setCaregiver("");
                  setQuery("");
                }}
              >
                <option value="">Choose caregiver type</option>
                <option value="family">Family caregiver</option>
                <option value="professional">In-hospital caregiver</option>
              </select>
            </label>
            <label>
              Find caregiver
              <SearchSuggestions
                label="Find caregiver"
                placeholder="Name, username or caregiver ID"
                value={query}
                options={choices.map(x => ({ id: x.user_id, name: x.name, detail: `${x.username} · ${x.account_id || x.user_id}` }))}
                onSelect={setCaregiver} onChange={setQuery}
              />
            </label>
            <label>
              {kind === "family"
                ? "Registered family member"
                : "Registered professional caregiver"}
              <select
                value={caregiver}
                onChange={(e) => {
                  setCaregiver(e.target.value);
                  const selected = caregivers.find(
                    (x) => x.user_id === e.target.value,
                  );
                  setQuery(selected?.account_id || selected?.user_id || "");
                }}
                required
              >
                <option value="">Select caregiver</option>
                {choices.map((x) => (
                  <option key={x.user_id} value={x.user_id}>
                    {x.name} · {x.username} · {x.account_id || x.user_id}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Find patient
              <SearchSuggestions
                label="Find patient"
                placeholder="Patient name or ID"
                value={patientQuery}
                options={rows.map(x => ({ id: x.patient_id, name: x.name, detail: `${x.patient_id} · ${(x.external_aliases || []).join(" · ")}` }))}
                onSelect={setPatient} onChange={setPatientQuery}
              />
            </label>
            <label>
              Patient
              <select
                value={patient}
                onChange={(e) => {
                  setPatient(e.target.value);
                  setPatientQuery(e.target.value);
                }}
                required
              >
                <option value="">Select patient</option>
                {rows.map((x) => (
                  <option key={x.patient_id} value={x.patient_id}>
                    {x.name} · {x.patient_id}
                  </option>
                ))}
              </select>
            </label>
            {query && !caregiver && (
              <small>
                Choose a matching caregiver when the name is ambiguous.
              </small>
            )}
            {patientQuery && !patient && (
              <small>
                Choose a matching patient when the name is ambiguous.
              </small>
            )}
            <button
              className="primary"
              disabled={!caregiver || !patient || !kind}
            >
              Assign patient
            </button>
          </form>
          <h4>Current assignments</h4>
          {links.map((x) => (
            <div
              className="record-row"
              key={`${x.patient_id}-${x.caregiver_id}`}
            >
              <div>
                <strong>
                  {accounts.find((a) => a.user_id === x.caregiver_id)?.name ||
                    x.caregiver_id}
                </strong>
                <small>
                  {patients.find((p) => p.patient_id === x.patient_id)?.name ||
                    x.patient_id}{" "}
                  · {x.kind}
                </small>
              </div>
              <button
                className="text-button"
                onClick={async () => {
                  try {
                    await request(
                      `/admin/caregiver-assignments/${x.caregiver_id}/${x.patient_id}`,
                      { method: "DELETE" },
                    );
                    await load();
                  } catch (e) {
                    setError((e as Error).message);
                  }
                }}
              >
                Revoke access
              </button>
            </div>
          ))}
        </section>
        <section className="panel admin-form">
          <h3>Caregiver directory</h3>
          <p>
            Availability is an administrator-maintained work status, separate
            from account access and patient assignment.
          </p>
          <label>
            Search caregivers
            <input
              aria-label="Search caregivers"
              placeholder="Name, username or ID"
              value={rosterQuery}
              onChange={(e) => setRosterQuery(e.target.value)}
            />
          </label>
          <div className="admin-scroll-list caregiver-roster">
            {caregivers
              .filter((x) =>
                [
                  x.name,
                  x.username,
                  x.account_id,
                  x.user_id,
                  ...(x.account_aliases || []),
                ].some((v) =>
                  v?.toLowerCase().includes(rosterQuery.toLowerCase()),
                ),
              )
              .map((x) => (
                <div className="appointment-row" key={x.user_id}>
                  <div>
                    <strong>{x.name}</strong>
                    <small>
                      {x.username} · {x.caregiver_type || "family"}
                    </small>
                    <code>{x.account_id || x.user_id}</code>
                  </div>
                  <select
                    aria-label={`Availability for ${x.username}`}
                    disabled={x.disabled}
                    value={x.availability || "free"}
                    onChange={async (e) => {
                      try {
                        const updated = await patch<User>(
                          `/admin/caregivers/${x.user_id}/availability`,
                          { availability: e.target.value },
                        );
                        setAccounts(
                          accounts.map((a) =>
                            a.user_id === x.user_id ? updated : a,
                          ),
                        );
                      } catch (e) {
                        setError((e as Error).message);
                      }
                    }}
                  >
                    <option value="free">Free</option>
                    <option value="active">Active</option>
                  </select>
                </div>
              ))}
            {!caregivers.length && (
              <p>No caregivers yet. Create an account in Accounts first.</p>
            )}
          </div>
        </section>
      </div>
      {status && <p role="status">{status}</p>}
      {error && (
        <p role="alert" className="care-error">
          {error}
        </p>
      )}
    </>
  );
}
