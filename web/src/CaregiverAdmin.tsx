import { useEffect, useState } from "react";
import { Patient, User, post, request } from "./api";

export default function CaregiverAdmin({
  patients,
  accounts,
  setAccounts,
}: {
  patients: Patient[];
  accounts: User[];
  setAccounts: (users: User[]) => void;
}) {
  const [name, setName] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [caregiver, setCaregiver] = useState("");
  const [patient, setPatient] = useState("");
  const [kind, setKind] = useState("family");
  const [links, setLinks] = useState<
    { patient_id: string; caregiver_id: string; kind: string }[]
  >([]);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  async function load() {
    try {
      setLinks(await request<typeof links>("/admin/caregiver-assignments"));
    } catch (e) {
      setError((e as Error).message);
    }
  }
  useEffect(() => {
    load();
  }, []);
  return (
    <>
      <div className="page-heading">
        <div className="eyebrow teal">CAREGIVER ACCESS</div>
        <h1>Caregivers</h1>
        <p>
          Create a family or professional caregiver account and assign access to
          signed patient pathways.
        </p>
      </div>
      <div className="admin-grid">
        <section className="panel admin-form">
          <h3>Register caregiver</h3>
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              try {
                const account = await post<User>("/admin/accounts", {
                  name,
                  username,
                  password,
                  role: "caregiver",
                });
                setAccounts([...accounts, account]);
                setCaregiver(account.user_id);
                setName("");
                setUsername("");
                setPassword("");
                setStatus("Caregiver registered. Assign a patient next.");
                setError("");
              } catch (e) {
                setError((e as Error).message);
              }
            }}
          >
            <label>
              Name
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                minLength={2}
              />
            </label>
            <label>
              Username
              <input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                minLength={3}
              />
            </label>
            <label>
              Password
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={12}
              />
            </label>
            <button className="primary">Register caregiver</button>
          </form>
        </section>
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
                setStatus("Caregiver access saved");
                setError("");
                await load();
              } catch (e) {
                setError((e as Error).message);
              }
            }}
          >
            <label>
              Caregiver
              <select
                value={caregiver}
                onChange={(e) => setCaregiver(e.target.value)}
                required
              >
                <option value="">Select caregiver</option>
                {accounts
                  .filter((x) => x.role === "caregiver" && !x.disabled)
                  .map((x) => (
                    <option key={x.user_id} value={x.user_id}>
                      {x.name}
                    </option>
                  ))}
              </select>
            </label>
            <label>
              Patient
              <select
                value={patient}
                onChange={(e) => setPatient(e.target.value)}
                required
              >
                <option value="">Select patient</option>
                {patients.map((x) => (
                  <option key={x.patient_id} value={x.patient_id}>
                    {x.name} · {x.patient_id}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Caregiver type
              <select value={kind} onChange={(e) => setKind(e.target.value)}>
                <option value="family">Family caregiver</option>
                <option value="professional">Professional caregiver</option>
              </select>
            </label>
            <button className="primary">Assign patient</button>
          </form>
          <h4>Current assignments</h4>
          {links.map((x) => (
            <div
              className="record-row"
              key={`${x.patient_id}-${x.caregiver_id}`}
            >
              <span>
                {accounts.find((a) => a.user_id === x.caregiver_id)?.name} ·{" "}
                {patients.find((p) => p.patient_id === x.patient_id)?.name ||
                  x.patient_id}{" "}
                · {x.kind}
              </span>
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
      </div>
      {error && (
        <p className="care-error" role="alert">
          {error}
        </p>
      )}
      {status && <p role="status">{status}</p>}
    </>
  );
}
