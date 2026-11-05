import type { User } from "./api";
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
            Review dictated text before sending. Audio is transcribed locally
            and is not retained after transcription.
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
