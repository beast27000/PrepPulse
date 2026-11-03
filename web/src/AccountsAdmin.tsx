import { useState } from "react";
import { User, patch, post } from "./api";

export default function AccountsAdmin({
  user,
  accounts,
  setAccounts,
}: {
  user: User;
  accounts: User[];
  setAccounts: (rows: User[]) => void;
}) {
  const [name, setName] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<User["role"]>("doctor");
  const [kind, setKind] = useState("");
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const visible = accounts.filter((a) =>
    [
      a.name,
      a.username,
      a.account_id,
      a.user_id,
      ...(a.account_aliases || []),
    ].some((x) => x?.toLowerCase().includes(q.toLowerCase())),
  );
  return (
    <>
      <div className="intro">
        <div>
          <div className="eyebrow teal">ACCESS CONTROL</div>
          <h1>Accounts</h1>
          <p>
            Create every account here. Assign caregivers to patients in
            Caregivers.
          </p>
        </div>
      </div>
      <div className="admin-grid accounts-grid">
        <section className="panel admin-form">
          <h3>Create account</h3>
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              setError("");
              try {
                const row = await post<User>("/admin/accounts", {
                  name,
                  username,
                  password,
                  role,
                  ...(role === "caregiver" ? { caregiver_type: kind } : {}),
                });
                setAccounts([...accounts, row]);
                setStatus(`Created ${row.name} · ${row.account_id}`);
                setName("");
                setUsername("");
                setPassword("");
                setKind("");
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            <label>
              Full name
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                minLength={2}
                required
              />
            </label>
            <label>
              Username
              <input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                minLength={3}
                required
              />
            </label>
            <label>
              Temporary password, minimum 12 characters
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                minLength={12}
                required
                autoComplete="new-password"
              />
            </label>
            <label>
              Role
              <select
                value={role}
                onChange={(e) => setRole(e.target.value as User["role"])}
              >
                <option value="doctor">Doctor</option>
                <option value="admin">Admin</option>
                <option value="caregiver">Caregiver</option>
              </select>
            </label>
            {role === "caregiver" && (
              <label>
                Caregiver type
                <select
                  aria-label="Caregiver type"
                  required
                  value={kind}
                  onChange={(e) => setKind(e.target.value)}
                >
                  <option value="">Choose caregiver type</option>
                  <option value="family">Family caregiver</option>
                  <option value="professional">In-hospital caregiver</option>
                </select>
              </label>
            )}
            <button className="primary" disabled={busy}>
              {busy ? "Creating…" : "Create account"}
            </button>
          </form>
          {status && <p role="status">{status}</p>}
          {error && (
            <p className="care-error" role="alert">
              {error}
            </p>
          )}
        </section>
        <section className="panel admin-form">
          <h3>Account directory</h3>
          <label>
            Search accounts
            <input
              aria-label="Search accounts"
              placeholder="Name, username or account ID"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </label>
          <div className="admin-scroll-list">
            {visible.map((a) => (
              <div className="appointment-row" key={a.user_id}>
                <div>
                  <strong>{a.name}</strong>
                  <small>
                    {a.username} · {a.role}
                    {a.caregiver_type ? ` · ${a.caregiver_type}` : ""}
                  </small>
                  <code>{a.account_id || a.user_id}</code>
                  <small>{a.disabled ? "Disabled" : "Enabled"}</small>
                  {a.role === "caregiver" && (
                    <label>
                      Caregiver type
                      <select
                        aria-label={`Caregiver type for ${a.username}`}
                        value={a.caregiver_type || "family"}
                        onChange={async (e) => {
                          if (
                            !confirm(
                              "Change caregiver type? Existing patient access will be revoked; assign the appropriate patients again.",
                            )
                          )
                            return;
                          try {
                            const updated = await patch<User>(
                              `/admin/accounts/${a.user_id}/caregiver-type`,
                              { caregiver_type: e.target.value },
                            );
                            setAccounts(
                              accounts.map((x) =>
                                x.user_id === a.user_id ? updated : x,
                              ),
                            );
                          } catch (e) {
                            setError((e as Error).message);
                          }
                        }}
                      >
                        <option value="family">Family caregiver</option>
                        <option value="professional">
                          In-hospital caregiver
                        </option>
                      </select>
                    </label>
                  )}
                </div>
                <button
                  className="text-button"
                  disabled={a.user_id === user.user_id || a.disabled}
                  onClick={async () => {
                    try {
                      await patch(`/admin/accounts/${a.user_id}/disable`, {});
                      setAccounts(
                        accounts.map((x) =>
                          x.user_id === a.user_id
                            ? { ...x, disabled: true }
                            : x,
                        ),
                      );
                    } catch (e) {
                      setError((e as Error).message);
                    }
                  }}
                >
                  Disable
                </button>
              </div>
            ))}
            {!visible.length && <p>No matching accounts.</p>}
          </div>
        </section>
      </div>
    </>
  );
}
