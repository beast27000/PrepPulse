import { request, type User } from "./api";
import { useEffect, useState } from "react";
import "./preferences.css";

export type Preferences = {
  appearance: "system" | "light" | "dark";
  textSize: "standard" | "large";
  contrast: "standard" | "high";
  dictationLanguage: "auto" | "en" | "hi" | "ta" | "bn" | "te";
  appointmentTime: string;
  appointmentInterval: number;
};

export const defaultPreferences: Preferences = {
  appearance: "light",
  textSize: "standard",
  contrast: "standard",
  dictationLanguage: "auto",
  appointmentTime: "10:30",
  appointmentInterval: 30,
};

export function readPreferences(userId: string): Preferences {
  try {
    const value = JSON.parse(
      localStorage.getItem(`preppulse.preferences.${userId}`) || "{}",
    );
    return { ...defaultPreferences, ...value };
  } catch {
    return { ...defaultPreferences };
  }
}

export function SettingsControls({
  user,
  value,
  onChange,
}: {
  user: User;
  value: Preferences;
  onChange: (value: Preferences) => void;
}) {
  const change = (next: Partial<Preferences>) =>
    onChange({ ...value, ...next });
  return (
    <div className="settings-grid">
      <CloudRouting admin={user.role === "admin"} />
      <section className="panel settings-section">
        <div className="eyebrow teal">APPEARANCE</div>
        <h3>Display preferences</h3>
        <label>
          Color mode
          <select
            value={value.appearance}
            onChange={(event) =>
              change({
                appearance: event.target.value as Preferences["appearance"],
              })
            }
          >
            <option value="system">Follow system</option>
            <option value="light">Light</option>
            <option value="dark">Dark</option>
          </select>
        </label>
        <label>
          Text size
          <select
            value={value.textSize}
            onChange={(event) =>
              change({
                textSize: event.target.value as Preferences["textSize"],
              })
            }
          >
            <option value="standard">Standard</option>
            <option value="large">Large</option>
          </select>
        </label>
        <label>
          Contrast
          <select
            value={value.contrast}
            onChange={(event) =>
              change({
                contrast: event.target.value as Preferences["contrast"],
              })
            }
          >
            <option value="standard">Standard</option>
            <option value="high">High contrast</option>
          </select>
        </label>
      </section>
      {user.role === "doctor" ? (
        <section className="panel settings-section">
          <div className="eyebrow teal">DOCTOR VOICE</div>
          <h3>Assistant preferences</h3>
          <label>
            Dictation language
            <select
              value={value.dictationLanguage}
              onChange={(event) =>
                change({
                  dictationLanguage: event.target
                    .value as Preferences["dictationLanguage"],
                })
              }
            >
              <option value="auto">Detect automatically</option>
              <option value="en">English</option>
              <option value="hi">Hindi</option>
              <option value="ta">Tamil</option>
              <option value="bn">Bengali</option>
              <option value="te">Telugu</option>
            </select>
          </label>
          <p>
            Review dictated text before sending. Microphone recordings are not
            retained by the application after transcription.
          </p>
        </section>
      ) : (
        <section className="panel settings-section">
          <div className="eyebrow teal">ADMIN SCHEDULING</div>
          <h3>Appointment defaults</h3>
          <label>
            Default start time
            <input
              type="time"
              value={value.appointmentTime}
              onChange={(event) =>
                change({ appointmentTime: event.target.value })
              }
            />
          </label>
          <label>
            Time step
            <select
              value={value.appointmentInterval}
              onChange={(event) =>
                change({ appointmentInterval: Number(event.target.value) })
              }
            >
              <option value={15}>15 minutes</option>
              <option value={30}>30 minutes</option>
              <option value={60}>60 minutes</option>
            </select>
          </label>
          <p>
            These defaults prefill the local appointment form. Each visit time
            can still be edited.
          </p>
        </section>
      )}
      <section className="panel settings-section settings-account">
        <div className="eyebrow teal">ACCOUNT</div>
        <h3>{user.name}</h3>
        <p>
          {user.role === "admin" ? "Administrator" : "Doctor"} · {user.username}
        </p>
        <p>
          Display and input preferences are saved in this browser for this
          account.
        </p>
      </section>
    </div>
  );
}

function CloudRouting({ admin }: { admin: boolean }) {
  const [mode, setMode] = useState("auto");
  const [available, setAvailable] = useState(false);
  const [status, setStatus] = useState("");
  const [testing, setTesting] = useState(false);
  const [checks, setChecks] = useState<{ checked_at: string; providers: { provider: string; status: string; detail: string; elapsed_seconds: number }[] } | null>(null);
  useEffect(() => {
    request<{ mode: string; cloud: boolean }>("/ai/status")
      .then((value) => { setMode(value.mode); setAvailable(value.cloud); })
      .catch(() => {});
  }, []);
  return <section className="panel settings-section">
    <div className="eyebrow teal">AI SERVICES</div>
    <h3>Provider availability</h3>
    {available && admin ? <label>Shared provider route
      <select value={mode} onChange={async (event) => {
        const next = event.target.value;
        setStatus("Saving...");
        try {
          await request("/admin/ai-routing", { method: "PUT", body: JSON.stringify({ mode: next }) });
          setMode(next); setStatus("Saved. Applies to new AI requests.");
        } catch (error) { setStatus(error instanceof Error ? error.message : "Could not save"); }
      }}>
        <option value="auto">Sarvam, then Azure fallback</option>
        <option value="azure">Azure only</option>
        <option value="sarvam">Sarvam only</option>
        <option value="disabled">Pause new AI requests</option>
      </select>
    </label> : <p>{available ? `Active route: ${mode === "auto" ? "Sarvam, then Azure fallback" : mode}. The administrator manages the shared route.` : "Local model configuration"}</p>}
    <p>{available ? "These tests check chat and agent inference. Translation and dictation use their separately configured services." : "Checks the locally configured model server."}</p>
    <button className="secondary" disabled={testing} onClick={async () => {
      setTesting(true); setStatus("Testing providers…");
      try { setChecks(await request("/ai/test", { method: "POST" })); setStatus(""); }
      catch (e) { setStatus((e as Error).message); } finally { setTesting(false); }
    }}>{testing ? "Testing…" : "Test providers"}</button>
    {checks && <div aria-live="polite"><p>Checked {new Date(checks.checked_at).toLocaleString()}</p>
      {checks.providers.map(x => <p key={x.provider}><strong>{x.provider}: {x.status.replaceAll("_", " ")}</strong><br />{x.detail} · {x.elapsed_seconds}s</p>)}
    </div>}
    <p role="status">{status}</p>
  </section>;
}
