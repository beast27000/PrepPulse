import { useCallback, useEffect, useRef, useState } from "react";
import {
  Activity,
  Bell,
  BookOpen,
  CalendarDays,
  Check,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  ClipboardCheck,
  CloudUpload,
  FileText,
  FolderOpen,
  HeartPulse,
  LogOut,
  Maximize2,
  Mic,
  Minimize2,
  Move,
  Plus,
  Search,
  Send,
  Settings2,
  ShieldCheck,
  Sparkles,
  Stethoscope,
  Volume2,
  X,
} from "lucide-react";
import {
  Appointment,
  Brief,
  Citation,
  Doc,
  Finding,
  Patient,
  User,
  Visit,
  patch,
  post,
  postAudio,
  request,
  setCsrf,
} from "./api";

type Page =
  | "Today"
  | "Patients"
  | "Records"
  | "Care pathways"
  | "Guidance library"
  | "Settings"
  | "New patient intake"
  | "Patient appointments"
  | "Patient directory"
  | "Accounts"
  | "Chat workspace";
type ChatMessage = {
  role: "user" | "assistant";
  text: string;
  citations?: Citation[];
};
const doctorPages: Page[] = [
  "Today",
  "Patients",
  "Records",
  "Care pathways",
  "Guidance library",
  "Settings",
];
const adminPages: Page[] = [
  "New patient intake",
  "Patient appointments",
  "Patient directory",
  "Accounts",
  "Settings",
];
const navIcons: Record<string, typeof Activity> = {
  Today: CalendarDays,
  Patients: HeartPulse,
  Records: FolderOpen,
  "Care pathways": ClipboardCheck,
  "Guidance library": BookOpen,
  Settings: Settings2,
  "New patient intake": Plus,
  "Patient appointments": CalendarDays,
  "Patient directory": HeartPulse,
  Accounts: ShieldCheck,
};
const labels: Record<string, string> = {
  en: "English",
  hi: "हिन्दी",
  ta: "தமிழ்",
  bn: "বাংলা",
  or: "ଓଡ଼ିଆ",
  te: "తెలుగు",
};
const today = () => new Date().toLocaleDateString("en-CA");
const ageOf = (dob?: string) =>
  dob ? new Date().getFullYear() - Number(dob.slice(0, 4)) : null;
const shortDate = (date?: string) =>
  date
    ? new Date(date + "T00:00:00").toLocaleDateString("en-US", {
        day: "2-digit",
        month: "short",
        year: "numeric",
      })
    : "Date unavailable";
const alias = (p: Patient) =>
  p.external_aliases?.find((x) => /^PP\d+$/.test(x)) || "";

function Login({ onLogin }: { onLogin: (u: User) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const u = await post<User>("/auth/login", { username, password });
      setCsrf(u.csrf);
      onLogin(u);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="login-screen">
      <div className="login-card">
        <div className="brand big">
          <span className="brand-mark">
            <Activity size={26} />
          </span>
          <span>
            <strong>PrepPulse</strong>
            <small>CLINICAL CHART REVIEW</small>
          </span>
        </div>
        <div className="eyebrow teal">SECURE WORKSPACE</div>
        <h1>Welcome back.</h1>
        <p>Sign in to review your assigned patients and visits.</p>
        <form onSubmit={submit}>
          <label>
            Username
            <input
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
            />
          </label>
          <label>
            Password
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </label>
          {error && (
            <div className="error" role="alert">
              {error}
            </div>
          )}
          <button className="primary full" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
        <span className="login-foot">PrepPulse · Assistive chart review</span>
      </div>
    </div>
  );
}

function ChatBox({
  patient,
  messages,
  setMessages,
  full = false,
  onExpand,
  onCitation,
}: {
  patient: Patient | null;
  messages: ChatMessage[];
  setMessages: React.Dispatch<React.SetStateAction<ChatMessage[]>>;
  full?: boolean;
  onExpand?: () => void;
  onCitation: (c: Citation) => void;
}) {
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [recording, setRecording] = useState(false);
  const [voiceError, setVoiceError] = useState("");
  const [ttsReady, setTtsReady] = useState(false);
  const [playingIndex, setPlayingIndex] = useState<number | null>(null);
  const playback = useRef<HTMLAudioElement | null>(null);
  const playbackUrl = useRef<string | null>(null);
  const media = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  useEffect(() => {
    let active = true;
    request<{ tts_ready: boolean }>("/voice/capabilities")
      .then((result) => {
        if (active) setTtsReady(result.tts_ready);
      })
      .catch(() => {
        if (active) setTtsReady(false);
      });
    return () => {
      active = false;
      playback.current?.pause();
      if (playbackUrl.current) URL.revokeObjectURL(playbackUrl.current);
    };
  }, []);
  async function readAloud(text: string, index: number) {
    if (playback.current) playback.current.pause();
    if (playbackUrl.current) URL.revokeObjectURL(playbackUrl.current);
    playback.current = null;
    playbackUrl.current = null;
    if (playingIndex === index) {
      setPlayingIndex(null);
      return;
    }
    if (!patient) return;
    setVoiceError("");
    try {
      const blob = await postAudio("/voice/speak", {
        patient_id: patient.patient_id,
        text: text.slice(0, 1200),
      });
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      playbackUrl.current = url;
      playback.current = audio;
      audio.onended = () => {
        setPlayingIndex(null);
        URL.revokeObjectURL(url);
        playbackUrl.current = null;
      };
      audio.onerror = () => {
        setPlayingIndex(null);
        setVoiceError("Audio playback failed.");
        URL.revokeObjectURL(url);
        playbackUrl.current = null;
      };
      await audio.play();
      setPlayingIndex(index);
    } catch (error) {
      setPlayingIndex(null);
      setVoiceError((error as Error).message);
    }
  }
  async function send(e?: React.FormEvent) {
    e?.preventDefault();
    const text = input.trim();
    if (!text || !patient || busy) return;
    setInput("");
    setBusy(true);
    setMessages((m) => [...m, { role: "user", text }]);
    try {
      const r = await post<{ answer_markdown: string; citations: Citation[] }>(
        "/chat/query",
        { patient_id: patient.patient_id, query: text },
      );
      setMessages((m) => [
        ...m,
        { role: "assistant", text: r.answer_markdown, citations: r.citations },
      ]);
    } catch (err) {
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          text: `Assistant unavailable: ${(err as Error).message}`,
        },
      ]);
    } finally {
      setBusy(false);
    }
  }
  async function toggleMic() {
    setVoiceError("");
    if (recording) {
      media.current?.stop();
      setRecording(false);
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      chunks.current = [];
      const recorder = new MediaRecorder(stream);
      media.current = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data.size) chunks.current.push(event.data);
      };
      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const form = new FormData();
        form.append(
          "file",
          new Blob(chunks.current, { type: recorder.mimeType || "audio/webm" }),
          "dictation.webm",
        );
        setBusy(true);
        try {
          const r = await request<{ transcript: string }>("/voice/transcribe", {
            method: "POST",
            body: form,
          });
          setInput(r.transcript);
          if (!r.transcript)
            setVoiceError(
              "No speech detected. Try again or type your question.",
            );
        } catch (err) {
          setVoiceError((err as Error).message);
        } finally {
          setBusy(false);
        }
      };
      recorder.start();
      setRecording(true);
    } catch (err) {
      setVoiceError((err as Error).message);
    }
  }
  return (
    <section className={"panel chat-panel " + (full ? "chat-full" : "")}>
      <div className="panel-heading">
        <div>
          <div className="eyebrow teal">
            <Sparkles size={14} /> PREPPULSE ASSISTANT
          </div>
          <h3>Ask about this record</h3>
        </div>
        {onExpand && (
          <button
            className="icon-button"
            title={full ? "Collapse chat" : "Expand chat"}
            onClick={onExpand}
          >
            {full ? <Minimize2 size={17} /> : <Maximize2 size={17} />}
          </button>
        )}
      </div>
      <div className="chat-messages" aria-live="polite">
        {messages.length === 0 ? (
          <div className="chat-empty">
            <Sparkles size={22} />
            <strong>Chart questions, with sources.</strong>
            <span>
              Ask about earlier visits, lab trends, medications, or the
              consultation brief.
            </span>
          </div>
        ) : (
          messages.map((m, i) => (
            <div key={i} className={"message " + m.role}>
              <div className="message-text">{m.text}</div>
              {m.citations?.length ? (
                <div className="message-cites">
                  {m.citations.map((c, j) => (
                    <button
                      key={j}
                      onClick={() => onCitation(c)}
                      disabled={!c.source_verified}
                    >
                      <FileText size={12} />
                      {c.document_title || "Source"} · p. {c.page_number}
                      {!c.source_verified ? " · unverified" : ""}
                    </button>
                  ))}
                </div>
              ) : null}
              {m.role === "assistant" && (
                <button
                  className="text-button muted"
                  disabled={!ttsReady || !patient}
                  title={
                    ttsReady
                      ? "Play this reply aloud"
                      : "No compatible local audio endpoint is available"
                  }
                  onClick={() => readAloud(m.text, i)}
                >
                  <Volume2 size={13} />{" "}
                  {playingIndex === i ? "Stop audio" : "Read aloud"}
                </button>
              )}
            </div>
          ))
        )}
      </div>
      <form className="chat-form" onSubmit={send}>
        <button
          type="button"
          className={"icon-button " + (recording ? "recording" : "")}
          title={recording ? "Stop dictation" : "Dictate question"}
          onClick={toggleMic}
          disabled={!patient || busy}
        >
          <Mic size={17} />
        </button>
        <input
          aria-label="Ask PrepPulse"
          placeholder={
            recording
              ? "Listening…"
              : patient
                ? "Ask about this patient…"
                : "Select a patient first"
          }
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={!patient || busy}
        />
        <button
          className="send-button"
          disabled={!input.trim() || !patient || busy}
          title="Send"
        >
          <Send size={17} />
        </button>
      </form>
      {voiceError && (
        <p className="small-error" role="alert">
          {voiceError}
        </p>
      )}
      <div className="chat-note">
        Dictation is reviewed before sending. Answers are assistive and require
        source review.
      </div>
    </section>
  );
}

function SourceProof({
  patient,
  citation,
  expanded,
  onExpand,
}: {
  patient: Patient | null;
  citation: Citation | null;
  expanded: boolean;
  onExpand: () => void;
}) {
  const verified = !!citation?.source_verified && !!patient;
  const [failed, setFailed] = useState(false);
  useEffect(
    () => setFailed(false),
    [citation?.document_id, citation?.page_number],
  );
  const box = citation?.bbox;
  return (
    <section className={"panel proof-panel " + (expanded ? "expanded" : "")}>
      <div className="panel-heading">
        <div>
          <div className="eyebrow teal">
            <FileText size={14} /> SOURCE PROOF
          </div>
          <h3>{citation?.document_title || "Select a finding"}</h3>
          <p>
            {citation
              ? verified
                ? "Citation linked to the selected finding"
                : "Exact source proof is not verified"
              : "Choose a cited item to inspect its source."}
          </p>
        </div>
        <button
          className="icon-button"
          onClick={onExpand}
          title={expanded ? "Collapse source proof" : "Expand source proof"}
        >
          {expanded ? <Minimize2 size={17} /> : <Maximize2 size={17} />}
        </button>
      </div>
      {verified && !failed ? (
        <>
          <div className="source-caption">
            <FileText size={13} />
            {citation?.document_title} <span>page {citation?.page_number}</span>
          </div>
          <div className="proof-preview">
            <img
              alt="Original document page"
              src={`/api/patients/${patient!.patient_id}/documents/${citation!.document_id}/page/${citation!.page_number}`}
              onError={() => setFailed(true)}
            />
            {box && (
              <div
                className="proof-highlight"
                style={{
                  left: box[0] / 10 + "%",
                  top: box[1] / 10 + "%",
                  width: (box[2] - box[0]) / 10 + "%",
                  height: (box[3] - box[1]) / 10 + "%",
                }}
              />
            )}
          </div>
          <div className="proof-citation">
            {citation?.document_title} · page {citation?.page_number} · box [
            {box?.join(", ")}]
          </div>
          <p className="proof-snippet">
            {citation?.snippet || citation?.extracted_text}
          </p>
        </>
      ) : (
        <div className="proof-unavailable">
          <CircleHelp size={22} />
          <strong>
            {failed
              ? "Source page unavailable"
              : citation
                ? "Source needs verification"
                : "Source preview"}
          </strong>
          <span>
            {failed
              ? "The document could not be displayed. Review the record list."
              : citation
                ? "This agent result does not yet have a verified document span. Review the original record before using it."
                : "Validated citations will display the original document and highlighted text here."}
          </span>
        </div>
      )}
    </section>
  );
}

function FloatingAssistant({
  patient,
  messages,
  setMessages,
  onCitation,
}: {
  patient: Patient | null;
  messages: ChatMessage[];
  setMessages: React.Dispatch<React.SetStateAction<ChatMessage[]>>;
  onCitation: (c: Citation) => void;
}) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ x: number; y: number }>(() => {
    try {
      return (
        JSON.parse(
          localStorage.getItem("preppulse-bubble-position") || "null",
        ) || { x: 24, y: 24 }
      );
    } catch {
      return { x: 24, y: 24 };
    }
  });
  const dragging = useRef<{
    x: number;
    y: number;
    px: number;
    py: number;
  } | null>(null);
  const moved = useRef(false);
  function down(e: React.PointerEvent) {
    moved.current = false;
    dragging.current = { x: e.clientX, y: e.clientY, px: pos.x, py: pos.y };
    e.currentTarget.setPointerCapture(e.pointerId);
  }
  function move(e: React.PointerEvent) {
    if (!dragging.current) return;
    const dx = dragging.current.x - e.clientX;
    const dy = dragging.current.y - e.clientY;
    if (Math.abs(dx) + Math.abs(dy) > 5) moved.current = true;
    setPos({
      x: Math.max(
        8,
        Math.min(window.innerWidth - 68, dragging.current.px + dx),
      ),
      y: Math.max(
        8,
        Math.min(window.innerHeight - 68, dragging.current.py + dy),
      ),
    });
  }
  function up() {
    dragging.current = null;
    localStorage.setItem("preppulse-bubble-position", JSON.stringify(pos));
  }
  return (
    <div className="floating-assistant" style={{ right: pos.x, bottom: pos.y }}>
      {open && (
        <div className="floating-panel">
          <ChatBox
            patient={patient}
            messages={messages}
            setMessages={setMessages}
            onCitation={onCitation}
            onExpand={() => setOpen(false)}
          />
        </div>
      )}
      <button
        className="floating-trigger"
        title="Move or open PrepPulse assistant"
        onPointerDown={down}
        onPointerMove={move}
        onPointerUp={up}
        onClick={() => {
          if (!moved.current) setOpen((v) => !v);
        }}
      >
        <Sparkles size={21} />
        <Move size={11} />
      </button>
    </div>
  );
}

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState<Page>("Patients");
  const [patients, setPatients] = useState<Patient[]>([]);
  const [selected, setSelected] = useState<Patient | null>(null);
  const [search, setSearch] = useState("");
  const [showSearch, setShowSearch] = useState(false);
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [documents, setDocuments] = useState<Doc[]>([]);
  const [brief, setBrief] = useState<Brief | null>(null);
  const [job, setJob] = useState<{
    job_id: string;
    status: string;
    error?: string;
  } | null>(null);
  const [visits, setVisits] = useState<Visit[]>([]);
  const [citation, setCitation] = useState<Citation | null>(null);
  const [recordPreview, setRecordPreview] = useState<Doc | null>(null);
  const [proofExpanded, setProofExpanded] = useState(false);
  const [chatExpanded, setChatExpanded] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [language, setLanguage] = useState("en");
  const [notice, setNotice] = useState("");
  const [uploadOpen, setUploadOpen] = useState(false);
  const [chatFullscreen, setChatFullscreen] = useState(false);
  const [pathway, setPathway] = useState<{
    mode: string;
    doctor_notes: string;
    reviewed_evidence: { title: string; citation: Citation }[];
    items: { item_id: string; text: string; completed: boolean }[];
    agent_suggestions: string[];
  } | null>(null);
  const [pathwayHistory, setPathwayHistory] = useState<
    {
      pathway_id: string;
      mode: string;
      approved_at: string;
      doctor_notes: string;
      items: { text: string; completed: boolean }[];
    }[]
  >([]);
  const [notes, setNotes] = useState("");
  const [newPathwayItem, setNewPathwayItem] = useState("");
  const [accounts, setAccounts] = useState<User[]>([]);
  const activeVisit = visits.find(
    (v) => v.status === "active" && v.doctor_id === user?.user_id,
  );
  const nav = user?.role === "admin" ? adminPages : doctorPages;

  const loadPatients = useCallback(
    async (q = "") => {
      if (!user) return;
      try {
        const rows = await request<Patient[]>(
          "/patients?q=" + encodeURIComponent(q),
        );
        setPatients(rows);
        if (!selected && rows.length && user.role === "doctor")
          setSelected(rows[0]);
      } catch (err) {
        setNotice((err as Error).message);
      }
    },
    [user, selected],
  );
  const loadSelected = useCallback(async () => {
    if (!selected || user?.role !== "doctor") return;
    const id = selected.patient_id;
    const results = await Promise.allSettled([
      request<Doc[]>(`/patients/${id}/documents`),
      request<{ brief: Brief }>(`/patients/${id}/brief`),
      request<Visit[]>(`/patients/${id}/visits`),
      request<{ job_id: string; status: string; error?: string } | null>(
        `/patients/${id}/brief/jobs/latest`,
      ),
    ]);
    if (results[0].status === "fulfilled") setDocuments(results[0].value);
    if (results[1].status === "fulfilled") setBrief(results[1].value.brief);
    else setBrief(null);
    if (results[2].status === "fulfilled") setVisits(results[2].value);
    if (results[3].status === "fulfilled") setJob(results[3].value);
  }, [selected, user]);
  const loadAppointments = useCallback(async () => {
    if (!user) return;
    try {
      setAppointments(await request<Appointment[]>("/appointments"));
    } catch (err) {
      setNotice((err as Error).message);
    }
  }, [user]);
  useEffect(() => {
    request<User>("/auth/me")
      .then((u) => {
        setCsrf(u.csrf);
        setUser(u);
        setPage(u.role === "admin" ? "New patient intake" : "Patients");
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);
  useEffect(() => {
    if (user) loadPatients();
  }, [user]);
  useEffect(() => {
    loadSelected();
    setCitation(null);
    setMessages([]);
  }, [selected?.patient_id]);
  useEffect(() => {
    if (user) loadAppointments();
    const timer = setInterval(loadAppointments, 15000);
    return () => clearInterval(timer);
  }, [user, loadAppointments]);
  useEffect(() => {
    if (!selected || !job || !["queued", "running"].includes(job.status))
      return;
    const timer = setInterval(async () => {
      try {
        const next = await request<typeof job>(
          `/patients/${selected.patient_id}/brief/jobs/latest`,
        );
        setJob(next);
        if (next?.status === "complete") loadSelected();
      } catch {}
    }, 3000);
    return () => clearInterval(timer);
  }, [selected, job?.status, loadSelected]);
  useEffect(() => {
    if (user?.role === "admin")
      request<User[]>("/admin/accounts")
        .then(setAccounts)
        .catch(() => {});
  }, [user]);
  useEffect(() => {
    if (activeVisit && page === "Care pathways") {
      request<typeof pathway>(`/visits/${activeVisit.visit_id}/pathway`)
        .then(setPathway)
        .catch(() => {});
      setNotes(activeVisit.doctor_notes || "");
    }
  }, [activeVisit?.visit_id, page]);
  useEffect(() => {
    if (selected && page === "Care pathways")
      request<typeof pathwayHistory>(
        `/patients/${selected.patient_id}/pathways`,
      )
        .then(setPathwayHistory)
        .catch(() => setPathwayHistory([]));
  }, [selected?.patient_id, page, visits]);

  async function run<T>(
    action: () => Promise<T>,
    success?: string,
  ): Promise<T | undefined> {
    try {
      const value = await action();
      if (success) setNotice(success);
      return value;
    } catch (err) {
      setNotice((err as Error).message);
    }
  }
  function pick(p: Patient) {
    setSelected(p);
    setSearch("");
    setShowSearch(false);
    setPage("Patients");
    setChatFullscreen(false);
  }
  async function startVisit() {
    if (!selected) return;
    await run(
      () => post<Visit>(`/patients/${selected.patient_id}/visits`, {}),
      "Visit started",
    );
    loadSelected();
  }
  async function setAdmission(admitted: boolean) {
    if (!activeVisit) {
      setNotice("Start a visit first.");
      return;
    }
    await run(
      () => post(`/visits/${activeVisit.visit_id}/admission`, { admitted }),
      admitted ? "Caregiver pathway selected" : "Family pathway selected",
    );
    loadSelected();
  }
  async function generateBrief() {
    if (!selected) return;
    const result = await run(
      () => post<typeof job>(`/patients/${selected.patient_id}/brief/jobs`, {}),
      "Clinical analysis queued",
    );
    if (result) setJob(result);
  }
  async function reviewFinding(
    f: Finding,
    decision: "accepted" | "edited" | "rejected",
  ) {
    if (!activeVisit) {
      setNotice("Start a visit before reviewing findings.");
      return;
    }
    const edited_text =
      decision === "edited"
        ? prompt("Edit the finding text for this visit:", f.title)
        : undefined;
    if (decision === "edited" && !edited_text) return;
    await run(
      () =>
        post(`/visits/${activeVisit.visit_id}/decisions`, {
          finding_id: f.finding_id,
          decision,
          edited_text,
        }),
      "Review decision saved",
    );
  }
  async function saveNotes() {
    if (!activeVisit) return;
    await run(
      () => post(`/visits/${activeVisit.visit_id}/notes`, { notes }),
      "Clinician notes saved",
    );
    loadSelected();
  }
  async function refreshPathway() {
    if (activeVisit) {
      const next = await run(() =>
        request<typeof pathway>(`/visits/${activeVisit.visit_id}/pathway`),
      );
      if (next) setPathway(next);
    }
  }
  async function addPathwayItem(text: string) {
    if (!activeVisit || !text.trim()) return;
    const result = await run(
      () => post(`/visits/${activeVisit.visit_id}/pathway/items`, { text }),
      "Pathway item added for clinician review",
    );
    if (result) {
      setNewPathwayItem("");
      refreshPathway();
    }
  }
  async function checkPathwayItem(itemId: string, completed: boolean) {
    if (!activeVisit) return;
    await run(() =>
      patch(`/visits/${activeVisit.visit_id}/pathway/items/${itemId}`, {
        completed,
      }),
    );
    refreshPathway();
  }
  async function endVisit() {
    if (!activeVisit) return;
    if (
      !confirm(
        "Review and finalize this visit pathway? This records your clinical approval.",
      )
    )
      return;
    const confirm_evidence_only =
      !notes.trim() &&
      confirm(
        "No clinician notes were entered. Finalize an evidence-only record?",
      );
    if (!notes.trim() && !confirm_evidence_only) return;
    if (notes !== activeVisit.doctor_notes)
      await post(`/visits/${activeVisit.visit_id}/notes`, { notes });
    const result = await run(
      () =>
        post(`/visits/${activeVisit.visit_id}/end`, {
          confirm: true,
          confirm_evidence_only,
        }),
      "Visit ended and pathway finalized",
    );
    if (result) {
      loadSelected();
      setPage("Care pathways");
    }
  }
  async function logout() {
    await run(() => post("/auth/logout", {}));
    setUser(null);
    setSelected(null);
    setBrief(null);
  }
  if (loading) return <div className="boot">Opening PrepPulse…</div>;
  if (!user) return <Login onLogin={setUser} />;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">
            <Activity size={23} />
          </span>
          <span>
            <strong>PrepPulse</strong>
            <small>CLINICAL CHART REVIEW</small>
          </span>
        </div>
        <nav aria-label="Main navigation">
          <span className="nav-caption">WORKSPACE</span>
          {nav.map((item) => {
            const Icon = navIcons[item];
            return (
              <button
                key={item}
                className={"nav-item " + (page === item ? "active" : "")}
                onClick={() => {
                  setPage(item);
                  setChatFullscreen(false);
                }}
              >
                <Icon size={17} />
                {item}
                {item === "Today" &&
                  appointments.some((a) => a.status === "scheduled") && (
                    <i className="nav-dot" />
                  )}
              </button>
            );
          })}
        </nav>
        <div className="sidebar-bottom">
          <div className="avatar">
            {user.name
              .split(" ")
              .map((x) => x[0])
              .slice(0, 2)
              .join("")
              .toUpperCase()}
          </div>
          <div>
            <strong>{user.name}</strong>
            <small>{user.role === "admin" ? "Administrator" : "Doctor"}</small>
          </div>
          <button className="icon-button" onClick={logout} title="Sign out">
            <LogOut size={17} />
          </button>
        </div>
      </aside>
      <div className="app-body">
        <header className="topbar">
          <div className="breadcrumb">
            Workspace <ChevronRight size={14} />{" "}
            <strong>{chatFullscreen ? "Chat workspace" : page}</strong>
          </div>
          <div className="topbar-right">
            {user.role === "doctor" && (
              <>
                <span className="top-patient">
                  {selected
                    ? `${selected.name} · ${selected.patient_id}`
                    : "Select a patient"}
                </span>
                <div className="top-search">
                  <Search size={16} />
                  <input
                    aria-label="Search patients"
                    placeholder="Search name or patient ID"
                    value={search}
                    onFocus={() => setShowSearch(true)}
                    onChange={(e) => {
                      setSearch(e.target.value);
                      setShowSearch(true);
                      loadPatients(e.target.value);
                    }}
                  />
                  {showSearch && search && (
                    <div className="search-popover">
                      {patients.length ? (
                        patients.map((p) => (
                          <button key={p.patient_id} onClick={() => pick(p)}>
                            <strong>{p.name}</strong>
                            <span>
                              {p.patient_id}
                              {alias(p) ? ` · ${alias(p)}` : ""}
                            </span>
                          </button>
                        ))
                      ) : (
                        <div className="empty-small">
                          No assigned patient found
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </>
            )}
            <button className="icon-button" title="Notifications">
              <Bell size={18} />
            </button>
            <div className="top-avatar">
              {user.name.slice(0, 2).toUpperCase()}
            </div>
          </div>
        </header>
        {notice && (
          <div className="notice" role="status">
            <span>{notice}</span>
            <button onClick={() => setNotice("")} aria-label="Dismiss">
              <X size={14} />
            </button>
          </div>
        )}
        <main className="content">
          {user.role === "doctor" ? (
            <>
              {page === "Patients" && !chatFullscreen && (
                <>
                  <div className="page-intro">
                    <div>
                      <div className="eyebrow teal">
                        <span className="pulse-dot" /> PRE-CONSULTATION
                        WORKSPACE
                      </div>
                      <h1>
                        Good{" "}
                        {new Date().getHours() < 12
                          ? "morning"
                          : new Date().getHours() < 17
                            ? "afternoon"
                            : "evening"}
                        , Dr. {user.name.split(" ").at(-1)}.
                      </h1>
                      <p>
                        {selected
                          ? `One focused brief for ${selected.name}.`
                          : "Select an assigned patient to begin chart review."}
                      </p>
                    </div>
                    <div className="intro-actions">
                      {selected && (
                        <>
                          <button className="secondary" onClick={startVisit}>
                            {activeVisit ? "Visit active" : "Start visit"}
                          </button>
                          <button
                            className="primary"
                            onClick={() => setUploadOpen(true)}
                          >
                            <CloudUpload size={17} /> Upload new record
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                  <div className="info-banner">
                    <CircleHelp size={15} /> You are viewing an assistive care
                    brief. Confirm findings against source records before
                    clinical use.
                  </div>
                  {selected ? (
                    <div
                      className={
                        "workspace-grid " +
                        (proofExpanded || chatExpanded ? "panel-wide" : "")
                      }
                    >
                      <div className="main-column">
                        <section className="panel consultation-panel">
                          <div className="consultation-heading">
                            <div>
                              <h2>
                                <ClipboardCheck size={21} /> Current
                                consultation brief
                              </h2>
                              <p>
                                {selected.name} <span>·</span>{" "}
                                {brief?.age_sex ||
                                  (ageOf(selected.dob)
                                    ? `${ageOf(selected.dob)} years`
                                    : "Age unavailable")}{" "}
                                <span>·</span>{" "}
                                {brief?.classification.stage ||
                                  "Classification pending"}{" "}
                                <span>·</span> {selected.patient_id}
                                {alias(selected) ? ` · ${alias(selected)}` : ""}
                              </p>
                            </div>
                            <span className="status-pill">
                              <ShieldCheck size={13} />
                              {brief ? "Ready to review" : "Awaiting analysis"}
                            </span>
                          </div>
                          {job &&
                            ["queued", "running", "failed"].includes(
                              job.status,
                            ) && (
                              <div className={"job-banner " + job.status}>
                                {job.status === "failed"
                                  ? `Analysis failed: ${job.error || "Try again"}`
                                  : `Analysis ${job.status}…`}
                              </div>
                            )}
                          {!brief ? (
                            <div className="brief-empty">
                              <Stethoscope size={26} />
                              <h3>No consultation brief yet</h3>
                              <p>
                                Process this patient’s records to create an
                                evidence-linked review.
                              </p>
                              <button
                                className="primary"
                                onClick={generateBrief}
                                disabled={
                                  !documents.length || job?.status === "running"
                                }
                              >
                                Run clinical analysis
                              </button>
                            </div>
                          ) : (
                            <>
                              <div className="four-cards">
                                <div className="brief-card cool">
                                  <div className="card-head">
                                    <span className="card-no">01</span>
                                    <div>
                                      <span className="eyebrow">
                                        WHAT CHANGED
                                      </span>
                                      <h3>Metabolic trajectory</h3>
                                    </div>
                                    <Activity size={18} />
                                  </div>
                                  <div className="kpis">
                                    {brief.trajectory.kpis.length ? (
                                      brief.trajectory.kpis
                                        .slice(0, 3)
                                        .map((k, i) => (
                                          <button
                                            key={i}
                                            className="kpi"
                                            onClick={() =>
                                              k.citation &&
                                              setCitation(k.citation)
                                            }
                                          >
                                            <small>{k.name}</small>
                                            <strong>{k.value}</strong>
                                            <span>
                                              {k.date_str?.slice(5) || "—"} ·{" "}
                                              {k.trend_direction}
                                            </span>
                                          </button>
                                        ))
                                    ) : (
                                      <p className="empty-small">
                                        No supported metrics found.
                                      </p>
                                    )}
                                  </div>
                                </div>
                                <div className="brief-card warm">
                                  <div className="card-head">
                                    <span className="card-no">02</span>
                                    <div>
                                      <span className="eyebrow">
                                        STILL TO CLOSE
                                      </span>
                                      <h3>Care gaps</h3>
                                    </div>
                                    <CalendarDays size={17} />
                                  </div>
                                  {brief.care_gaps.items.length ? (
                                    brief.care_gaps.items
                                      .slice(0, 3)
                                      .map((g, i) => (
                                        <button
                                          key={i}
                                          className="card-list-item"
                                          onClick={() =>
                                            g.citation &&
                                            setCitation(g.citation)
                                          }
                                        >
                                          <i
                                            className={
                                              "severity-dot " + g.severity
                                            }
                                          />
                                          <span>
                                            <strong>{g.title}</strong>
                                            <small>{g.details}</small>
                                          </span>
                                          <ChevronRight size={15} />
                                        </button>
                                      ))
                                  ) : (
                                    <p className="empty-small">
                                      No care gaps identified.
                                    </p>
                                  )}
                                </div>
                                <div className="brief-card rose">
                                  <div className="card-head">
                                    <span className="card-no">03</span>
                                    <div>
                                      <span className="eyebrow">
                                        RESOLVE BEFORE PLAN
                                      </span>
                                      <h3>Record mismatches</h3>
                                    </div>
                                    <CircleHelp size={17} />
                                  </div>
                                  {brief.mismatches.items.length ? (
                                    brief.mismatches.items
                                      .slice(0, 3)
                                      .map((m, i) => (
                                        <button
                                          key={i}
                                          className="card-list-item"
                                          onClick={() =>
                                            setCitation(
                                              m.citations?.find(
                                                (c) => c.source_verified,
                                              ) ||
                                                m.source_a_citation ||
                                                null,
                                            )
                                          }
                                        >
                                          <i className="severity-dot critical" />
                                          <span>
                                            <strong>{m.title}</strong>
                                            <small>{m.description}</small>
                                          </span>
                                          <ChevronRight size={15} />
                                        </button>
                                      ))
                                  ) : (
                                    <p className="empty-small">
                                      No documented mismatches found.
                                    </p>
                                  )}
                                </div>
                                <div className="brief-card blue">
                                  <div className="card-head">
                                    <span className="card-no">04</span>
                                    <div>
                                      <span className="eyebrow">
                                        FAMILY HANDOFF
                                      </span>
                                      <h3>
                                        {activeVisit?.admitted
                                          ? "Caregiver pathway"
                                          : "Family prep sheet"}
                                      </h3>
                                    </div>
                                    <ClipboardCheck size={17} />
                                  </div>
                                  {brief.caregiver_prep.checklist
                                    .slice(0, 3)
                                    .map((item, i) => (
                                      <div className="check-preview" key={i}>
                                        <Check size={15} />
                                        {String(
                                          item[`text_${language}`] ||
                                            item.text_en,
                                        )}
                                      </div>
                                    ))}
                                </div>
                              </div>
                              <div className="visit-strip">
                                <div>
                                  <span>VISIT FOCUS</span>
                                  <strong>
                                    {brief.visit_focus || "Chart review"}
                                  </strong>
                                  <small>Clinician review required</small>
                                </div>
                                <div>
                                  <span>LATEST METRIC</span>
                                  <strong>
                                    {brief.trajectory.kpis[0]?.value || "—"}
                                  </strong>
                                  <small>
                                    {brief.trajectory.kpis[0]?.name ||
                                      "No metric"}
                                  </small>
                                </div>
                                <div>
                                  <span>OPEN ITEMS</span>
                                  <strong>
                                    {brief.care_gaps.items.length +
                                      brief.mismatches.items.length}
                                  </strong>
                                  <small>Potential review items</small>
                                </div>
                              </div>
                              <div className="findings">
                                <div className="section-heading">
                                  <div>
                                    <h3>Priority findings</h3>
                                    <p>
                                      Select a finding to inspect its source
                                      proof
                                    </p>
                                  </div>
                                  <span>
                                    {brief.priority_findings.length} findings
                                  </span>
                                </div>
                                {brief.priority_findings.length ? (
                                  brief.priority_findings.map((f) => (
                                    <article
                                      key={f.finding_id}
                                      className="finding"
                                    >
                                      <div
                                        className={"finding-bar " + f.severity}
                                      />
                                      <div className="finding-main">
                                        <strong>{f.title}</strong>
                                        <p>{f.subtitle}</p>
                                        <button
                                          className="source-link"
                                          disabled={
                                            !f.citation?.source_verified
                                          }
                                          onClick={() =>
                                            setCitation(f.citation || null)
                                          }
                                        >
                                          <FileText size={13} />
                                          {f.citation?.source_verified
                                            ? `${f.citation.document_title} · ${shortDate(f.date)} · p. ${f.citation.page_number}`
                                            : "No verified direct source attached"}
                                        </button>
                                      </div>
                                      <div className="finding-controls">
                                        <div>
                                          <button
                                            onClick={() =>
                                              reviewFinding(f, "accepted")
                                            }
                                          >
                                            Accept
                                          </button>
                                          <button
                                            onClick={() =>
                                              reviewFinding(f, "edited")
                                            }
                                          >
                                            Edit
                                          </button>
                                          <button
                                            onClick={() =>
                                              reviewFinding(f, "rejected")
                                            }
                                          >
                                            Reject
                                          </button>
                                        </div>
                                        <span className="finding-status">
                                          {f.status.replace("_", " ")}
                                        </span>
                                      </div>
                                    </article>
                                  ))
                                ) : (
                                  <p className="empty-small">
                                    No priority findings were generated.
                                  </p>
                                )}
                              </div>
                            </>
                          )}
                        </section>
                        <div className="bottom-actions">
                          <button
                            className="secondary"
                            onClick={generateBrief}
                            disabled={job?.status === "running"}
                          >
                            Refresh brief
                          </button>
                          {activeVisit && (
                            <>
                              <button
                                className="secondary"
                                onClick={() =>
                                  setAdmission(!activeVisit.admitted)
                                }
                              >
                                {activeVisit.admitted
                                  ? "End admission flag"
                                  : "Admit patient"}
                              </button>
                              <button
                                className="primary"
                                onClick={() => {
                                  setPage("Care pathways");
                                  setNotes(activeVisit.doctor_notes || "");
                                }}
                              >
                                Review pathway / end session
                              </button>
                            </>
                          )}
                        </div>
                        {brief?.assistive_bubbles?.length ? (
                          <div className="suggestions">
                            {brief.assistive_bubbles.map((b) => (
                              <button
                                key={b.bubble_id}
                                onClick={() => {
                                  setChatFullscreen(true);
                                  setPage("Chat workspace");
                                }}
                              >
                                <Sparkles size={14} />
                                {b.prompt_text}
                              </button>
                            ))}
                          </div>
                        ) : null}
                      </div>
                      <div
                        className={
                          "right-column " +
                          (chatExpanded ? "chat-inline-expanded" : "")
                        }
                      >
                        <SourceProof
                          patient={selected}
                          citation={citation}
                          expanded={proofExpanded}
                          onExpand={() => setProofExpanded((v) => !v)}
                        />
                        <button
                          className="secondary inline-expand"
                          onClick={() => setChatExpanded((v) => !v)}
                        >
                          {chatExpanded
                            ? "Collapse assistant"
                            : "Expand assistant inline"}
                        </button>
                        <ChatBox
                          patient={selected}
                          messages={messages}
                          setMessages={setMessages}
                          onCitation={setCitation}
                          onExpand={() => setChatFullscreen(true)}
                        />
                        {brief && (
                          <section className="panel checklist-panel">
                            <div className="panel-heading">
                              <div>
                                <div className="eyebrow teal">
                                  <ClipboardCheck size={14} /> CAREGIVER HANDOFF
                                </div>
                                <h3>Visit checklist</h3>
                              </div>
                              <select
                                aria-label="Checklist language"
                                value={language}
                                onChange={(e) => setLanguage(e.target.value)}
                              >
                                {brief.caregiver_prep.available_languages.map(
                                  (l) => (
                                    <option key={l} value={l}>
                                      {labels[l] || l}
                                    </option>
                                  ),
                                )}
                              </select>
                            </div>
                            {brief.caregiver_prep.checklist.map((item) => (
                              <label key={item.id} className="check-row">
                                <input type="checkbox" />
                                {String(
                                  item[`text_${language}`] || item.text_en,
                                )}
                              </label>
                            ))}
                            <p className="small-muted">
                              Checklist selections are for this view; approved
                              pathway notes are saved separately.
                            </p>
                          </section>
                        )}
                        <div className="freshness">
                          <div>
                            <strong>Brief for clinician review</strong>
                            <small>
                              Built from {brief?.raw_evidence_count || 0}{" "}
                              evidence chunks · verify sources
                            </small>
                          </div>
                          <div className="fresh-ring">
                            {brief ? "Review" : "—"}
                          </div>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="panel empty-page">
                      No assigned patient yet. Ask an admin to assign one.
                    </div>
                  )}
                </>
              )}
              {page === "Today" && (
                <>
                  <PageHeading
                    eyebrow="YOUR SCHEDULE"
                    title="Today’s patients"
                    text={`Appointments for ${shortDate(today())}. Select a card to open the patient workspace.`}
                  />
                  <div className="card-carousel">
                    {appointments.filter((a) => a.status === "scheduled")
                      .length ? (
                      appointments
                        .filter((a) => a.status === "scheduled")
                        .map((a) => (
                          <button
                            className="patient-card"
                            key={a.appointment_id}
                            onClick={() => {
                              const p = patients.find(
                                (x) => x.patient_id === a.patient_id,
                              );
                              if (p) pick(p);
                            }}
                          >
                            <span className="card-time">{a.time}</span>
                            <div className="patient-avatar">
                              {a.patient_name.slice(0, 2).toUpperCase()}
                            </div>
                            <strong>{a.patient_name}</strong>
                            <small>{a.patient_id}</small>
                            <div className="card-meta">
                              {a.age || "—"} years ·{" "}
                              {a.sex || "Sex unavailable"}
                            </div>
                            <div className="card-meta">{shortDate(a.date)}</div>
                            <span className="card-open">
                              Open workspace <ChevronRight size={15} />
                            </span>
                          </button>
                        ))
                    ) : (
                      <div className="panel empty-page">
                        No scheduled appointments for today.
                      </div>
                    )}
                  </div>
                </>
              )}
              {page === "Records" && (
                <>
                  <PageHeading
                    eyebrow="DOCUMENT LIBRARY"
                    title="Patient records"
                    text="Browse assigned patients and inspect their dated source files."
                  />
                  <PatientCarousel
                    patients={patients}
                    selected={selected}
                    onPick={setSelected}
                  />
                  {selected && (
                    <section className="panel records-panel">
                      <div className="panel-heading">
                        <div>
                          <div className="eyebrow teal">PATIENT RECORDS</div>
                          <h3>{selected.name}</h3>
                        </div>
                        <button
                          className="secondary"
                          onClick={() => setUploadOpen(true)}
                        >
                          <CloudUpload size={15} /> Add record
                        </button>
                      </div>
                      {documents.length ? (
                        documents.map((d) => (
                          <div key={d.record_id} className="record-row">
                            <FileText size={19} />
                            <div>
                              <strong>{d.filename}</strong>
                              <small>
                                {shortDate(d.visit_date)} · {d.document_type} ·{" "}
                                {d.status}
                                {d.error ? ` · ${d.error}` : ""}
                              </small>
                            </div>
                            <button
                              className="text-button"
                              onClick={() => setRecordPreview(d)}
                            >
                              Preview
                            </button>
                          </div>
                        ))
                      ) : (
                        <p>No documents uploaded for this patient.</p>
                      )}
                      {recordPreview &&
                        documents.some(
                          (d) => d.record_id === recordPreview.record_id,
                        ) && (
                          <div className="records-preview">
                            <div className="section-heading">
                              <strong>{recordPreview.filename}</strong>
                              <button
                                className="text-button"
                                onClick={() => setRecordPreview(null)}
                              >
                                Close
                              </button>
                            </div>
                            <img
                              alt={`First page of ${recordPreview.filename}`}
                              src={`/api/patients/${selected.patient_id}/documents/${recordPreview.record_id}/page/1`}
                            />
                            <p>
                              Original document preview. No finding is
                              highlighted unless its citation is verified.
                            </p>
                          </div>
                        )}
                    </section>
                  )}
                </>
              )}
              {page === "Care pathways" && (
                <>
                  <PageHeading
                    eyebrow="CONTINUITY OF CARE"
                    title="Care pathways"
                    text="Clinician-reviewed family or caregiver handoff, based on visit context."
                  />
                  <PatientCarousel
                    patients={patients}
                    selected={selected}
                    onPick={setSelected}
                  />
                  {selected && (
                    <section className="panel pathway-panel">
                      <div className="panel-heading">
                        <div>
                          <div className="eyebrow teal">
                            {activeVisit?.admitted
                              ? "CAREGIVER PATHWAY"
                              : "FAMILY PATHWAY"}
                          </div>
                          <h3>{selected.name}</h3>
                        </div>
                        <span className="status-pill">
                          {activeVisit ? "Draft visit" : "No active visit"}
                        </span>
                      </div>
                      {activeVisit ? (
                        <>
                          <p className="pathway-help">
                            Add what you discussed with the patient or
                            caregiver. Only your notes, approved checklist
                            items, and verified, reviewed evidence can enter the
                            finalized pathway.
                          </p>
                          <div className="pathway-tools">
                            <button
                              className="secondary"
                              onClick={() =>
                                setAdmission(!activeVisit.admitted)
                              }
                            >
                              {activeVisit.admitted
                                ? "Switch to family pathway"
                                : "Admit · caregiver pathway"}
                            </button>
                            <span>
                              Admission is a PrepPulse care-workflow flag.
                            </span>
                          </div>
                          <label className="notes-label">
                            Clinician handoff notes
                            <textarea
                              rows={6}
                              placeholder="Enter instructions, follow-up details, and points discussed during this visit…"
                              value={notes}
                              onChange={(e) => setNotes(e.target.value)}
                            />
                          </label>
                          <div className="pathway-evidence">
                            <h4>Pathway checklist</h4>
                            {pathway?.items?.map((item) => (
                              <label className="check-row" key={item.item_id}>
                                <input
                                  type="checkbox"
                                  checked={item.completed}
                                  onChange={(e) =>
                                    checkPathwayItem(
                                      item.item_id,
                                      e.target.checked,
                                    )
                                  }
                                />
                                {item.text}
                              </label>
                            ))}
                            <div className="inline-form">
                              <input
                                aria-label="New pathway checklist item"
                                placeholder="Add a clinician-approved checklist item"
                                value={newPathwayItem}
                                onChange={(e) =>
                                  setNewPathwayItem(e.target.value)
                                }
                              />
                              <button
                                className="secondary"
                                onClick={() => addPathwayItem(newPathwayItem)}
                                disabled={!newPathwayItem.trim()}
                              >
                                Add
                              </button>
                            </div>
                            {pathway?.agent_suggestions?.length ? (
                              <>
                                <h4>
                                  Agent suggestions · review before adding
                                </h4>
                                {pathway.agent_suggestions.map((text, i) => (
                                  <div className="suggestion-row" key={i}>
                                    <span>{text}</span>
                                    <button
                                      className="text-button"
                                      onClick={() => addPathwayItem(text)}
                                    >
                                      Review and add
                                    </button>
                                  </div>
                                ))}
                              </>
                            ) : null}
                          </div>
                          <div className="form-actions">
                            <button className="secondary" onClick={saveNotes}>
                              Save draft notes
                            </button>
                            <button className="primary" onClick={endVisit}>
                              Review and end session
                            </button>
                          </div>
                          <div className="pathway-evidence">
                            <h4>Verified, reviewed findings</h4>
                            {pathway?.reviewed_evidence?.length ? (
                              pathway.reviewed_evidence.map((e, i) => (
                                <button
                                  key={i}
                                  className="source-link"
                                  onClick={() => setCitation(e.citation)}
                                >
                                  {e.title}
                                </button>
                              ))
                            ) : (
                              <p>
                                No findings have both verified source proof and
                                clinician review yet.
                              </p>
                            )}
                          </div>
                        </>
                      ) : (
                        <div className="brief-empty">
                          <ClipboardCheck size={24} />
                          <p>
                            Start a visit on the Patients page to draft a
                            pathway.
                          </p>
                          <button
                            className="primary"
                            onClick={() => setPage("Patients")}
                          >
                            Open patient workspace
                          </button>
                        </div>
                      )}
                    </section>
                  )}
                  {selected && pathwayHistory.length > 0 && (
                    <section className="panel pathway-panel">
                      <div className="eyebrow teal">
                        PREVIOUS APPROVED PATHWAYS
                      </div>
                      <h3>Earlier visits</h3>
                      {pathwayHistory.map((entry) => (
                        <div className="history-row" key={entry.pathway_id}>
                          <strong>
                            {entry.mode === "caregiver"
                              ? "Caregiver"
                              : "Family"}{" "}
                            pathway ·{" "}
                            {shortDate(entry.approved_at.slice(0, 10))}
                          </strong>
                          <p>
                            {entry.doctor_notes ||
                              "Evidence-only record approved by the clinician."}
                          </p>
                          <small>
                            {entry.items?.length || 0} clinician-approved
                            checklist items
                          </small>
                        </div>
                      ))}
                    </section>
                  )}
                </>
              )}
              {page === "Guidance library" && (
                <>
                  <PageHeading
                    eyebrow="APPROVED RESOURCES"
                    title="Guidance library"
                    text="Clinician-approved resources will be available here."
                  />
                  <div className="panel empty-page">
                    <BookOpen size={28} />
                    <h3>No guidance has been approved for publication.</h3>
                    <p>
                      PrepPulse does not generate library guidance from patient
                      records.
                    </p>
                  </div>
                </>
              )}
              {page === "Settings" && (
                <>
                  <PageHeading
                    eyebrow="PREFERENCES"
                    title="Settings"
                    text="Your local PrepPulse workspace settings."
                  />
                  <div className="panel settings-panel">
                    <h3>Signed in account</h3>
                    <p>
                      {user.name} · {user.role}
                    </p>
                    <h3>Voice</h3>
                    <p>
                      Dictation runs locally and waits for your transcript
                      review. Spoken replies become available after a local TTS
                      runtime and model path are configured.
                    </p>
                  </div>
                </>
              )}
              {(page === "Chat workspace" || chatFullscreen) && (
                <>
                  <div className="page-intro">
                    <div>
                      <div className="eyebrow teal">PATIENT ASSISTANT</div>
                      <h1>Chart conversation</h1>
                      <p>
                        {selected?.name || "Select a patient"} · Review prior
                        records and linked evidence.
                      </p>
                    </div>
                    <button
                      className="secondary"
                      onClick={() => {
                        setChatFullscreen(false);
                        setPage("Patients");
                      }}
                    >
                      Back to Patients
                    </button>
                  </div>
                  <div className="chat-workspace">
                    <ChatBox
                      patient={selected}
                      messages={messages}
                      setMessages={setMessages}
                      full
                      onCitation={setCitation}
                    />
                    <div>
                      <SourceProof
                        patient={selected}
                        citation={citation}
                        expanded
                        onExpand={() => {}}
                      />
                      <section className="panel context-panel">
                        <h3>Patient context</h3>
                        <p>{brief?.classification.stage || "No brief yet"}</p>
                        <p>
                          {documents.length} records ·{" "}
                          {brief?.metric_series.length || 0} metric series
                        </p>
                        {brief && <p>{brief.trajectory.summary}</p>}
                        <h4>Metric charts and tables</h4>
                        {brief?.metric_series.slice(0, 5).map((s) => (
                          <MetricExplorer
                            key={s.metric_name}
                            series={s}
                            onCitation={setCitation}
                          />
                        ))}
                        <h4>Previous records</h4>
                        {documents.map((d) => (
                          <button
                            className="context-row record-button"
                            key={d.record_id}
                            onClick={() => setRecordPreview(d)}
                          >
                            <strong>{d.filename}</strong>
                            <span>{shortDate(d.visit_date)}</span>
                          </button>
                        ))}
                        {recordPreview && selected && (
                          <div className="record-preview">
                            <div className="section-heading">
                              <strong>{recordPreview.filename}</strong>
                              <button
                                className="text-button"
                                onClick={() => setRecordPreview(null)}
                              >
                                Close
                              </button>
                            </div>
                            <img
                              alt={`Page 1 of ${recordPreview.filename}`}
                              src={`/api/patients/${selected.patient_id}/documents/${recordPreview.record_id}/page/1`}
                            />
                            <p>
                              Document preview. No claim-specific highlight is
                              selected.
                            </p>
                          </div>
                        )}
                      </section>
                    </div>
                  </div>
                </>
              )}
            </>
          ) : (
            <AdminPages
              page={page}
              user={user}
              patients={patients}
              accounts={accounts}
              setAccounts={setAccounts}
              reloadPatients={() => loadPatients()}
              reloadAppointments={loadAppointments}
              appointments={appointments}
              run={run}
            />
          )}
        </main>
        {user.role === "doctor" &&
          page !== "Patients" &&
          page !== "Chat workspace" &&
          !chatFullscreen && (
            <FloatingAssistant
              patient={selected}
              messages={messages}
              setMessages={setMessages}
              onCitation={setCitation}
            />
          )}
      </div>
      {uploadOpen && selected && (
        <UploadModal
          patient={selected}
          onClose={() => setUploadOpen(false)}
          onUploaded={() => {
            loadSelected();
            setNotice(
              "Record uploaded. Run or refresh the clinical analysis when ready.",
            );
          }}
        />
      )}
    </div>
  );
}

function MetricExplorer({
  series,
  onCitation,
}: {
  series: Brief["metric_series"][number];
  onCitation: (c: Citation) => void;
}) {
  const points = [...series.points].sort((a, b) =>
    a.date.localeCompare(b.date),
  );
  if (!points.length)
    return (
      <p className="small-muted">
        {series.metric_name}: no chartable measurements.
      </p>
    );
  const values = points.map((p) => p.value);
  const low = Math.min(...values),
    high = Math.max(...values);
  const span = high - low || 1;
  const coords = points.map((p, i) => ({
    x: points.length === 1 ? 150 : 24 + (i * 252) / (points.length - 1),
    y: 76 - ((p.value - low) / span) * 52,
  }));
  return (
    <div className="metric-explorer">
      <strong>{series.metric_name}</strong>
      <svg
        viewBox="0 0 300 100"
        role="img"
        aria-label={`${series.metric_name} trend chart`}
      >
        <line x1="18" y1="78" x2="284" y2="78" stroke="#d5e5e5" />
        <polyline
          points={coords.map((p) => `${p.x},${p.y}`).join(" ")}
          fill="none"
          stroke="#348f89"
          strokeWidth="2.5"
        />
        {coords.map((p, i) => (
          <circle key={i} cx={p.x} cy={p.y} r="4" fill="#348f89" />
        ))}
      </svg>
      <table>
        <thead>
          <tr>
            <th>Date</th>
            <th>Value</th>
            <th>Source</th>
          </tr>
        </thead>
        <tbody>
          {points.map((p, i) => (
            <tr key={i}>
              <td>{shortDate(p.date)}</td>
              <td>
                {p.value} {p.unit}
              </td>
              <td>
                {p.citation?.source_verified ? (
                  <button
                    className="source-link"
                    onClick={() => onCitation(p.citation!)}
                  >
                    View
                  </button>
                ) : (
                  "Unverified"
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PageHeading({
  eyebrow,
  title,
  text,
}: {
  eyebrow: string;
  title: string;
  text: string;
}) {
  return (
    <div className="page-intro">
      <div>
        <div className="eyebrow teal">
          <span className="pulse-dot" /> {eyebrow}
        </div>
        <h1>{title}</h1>
        <p>{text}</p>
      </div>
    </div>
  );
}
function PatientCarousel({
  patients,
  selected,
  onPick,
}: {
  patients: Patient[];
  selected: Patient | null;
  onPick: (p: Patient) => void;
}) {
  return (
    <div className="card-carousel compact">
      {patients.map((p) => (
        <button
          className={
            "patient-card " +
            (selected?.patient_id === p.patient_id ? "chosen" : "")
          }
          key={p.patient_id}
          onClick={() => onPick(p)}
        >
          <div className="patient-avatar">
            {p.name.slice(0, 2).toUpperCase()}
          </div>
          <strong>{p.name}</strong>
          <small>{p.patient_id}</small>
          <div className="card-meta">
            {alias(p) || "PrepPulse intake"} · {ageOf(p.dob) || "—"} years
          </div>
          <span className="card-open">
            View patient <ChevronRight size={15} />
          </span>
        </button>
      ))}
    </div>
  );
}

function UploadModal({
  patient,
  onClose,
  onUploaded,
}: {
  patient: Patient;
  onClose: () => void;
  onUploaded: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [type, setType] = useState("consult");
  const [date, setDate] = useState(today());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function upload(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    form.append("document_type", type);
    form.append("visit_date", date);
    setBusy(true);
    setError("");
    try {
      await request(`/patients/${patient.patient_id}/documents`, {
        method: "POST",
        body: form,
      });
      onUploaded();
      onClose();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label="Upload patient record"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="panel-heading">
          <div>
            <div className="eyebrow teal">PATIENT RECORD</div>
            <h2>Upload new record</h2>
            <p>
              {patient.name} · {patient.patient_id}
            </p>
          </div>
          <button className="icon-button" onClick={onClose}>
            <X size={18} />
          </button>
        </div>
        <form onSubmit={upload}>
          <label>
            Document
            <input
              type="file"
              accept=".pdf,.png,.jpg,.jpeg"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
              required
            />
          </label>
          <div className="form-grid">
            <label>
              Document type
              <select value={type} onChange={(e) => setType(e.target.value)}>
                <option value="consult">Consultation</option>
                <option value="lab">Lab report</option>
                <option value="rx">Prescription</option>
                <option value="discharge">Discharge summary</option>
              </select>
            </label>
            <label>
              Visit date
              <input
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
              />
            </label>
          </div>
          {error && <div className="error">{error}</div>}
          <div className="form-actions">
            <button className="secondary" type="button" onClick={onClose}>
              Cancel
            </button>
            <button className="primary" disabled={busy || !file}>
              {busy ? "Uploading…" : "Upload record"}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}

function AdminPages({
  page,
  user,
  patients,
  accounts,
  setAccounts,
  reloadPatients,
  reloadAppointments,
  appointments,
  run,
}: {
  page: Page;
  user: User;
  patients: Patient[];
  accounts: User[];
  setAccounts: (a: User[]) => void;
  reloadPatients: () => void;
  reloadAppointments: () => void;
  appointments: Appointment[];
  run: <T>(
    action: () => Promise<T>,
    success?: string,
  ) => Promise<T | undefined>;
}) {
  const doctors = accounts.filter(
    (a) =>
      a.role === "doctor" && !(a as User & { disabled?: boolean }).disabled,
  );
  const [name, setName] = useState("");
  const [dob, setDob] = useState("");
  const [sex, setSex] = useState("");
  const [doctor, setDoctor] = useState("");
  const [appointmentPatient, setAppointmentPatient] = useState("");
  const [appointmentDate, setAppointmentDate] = useState(today());
  const [appointmentTime, setAppointmentTime] = useState("10:30");
  const [reason, setReason] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [accountName, setAccountName] = useState("");
  const [role, setRole] = useState<"doctor" | "admin">("doctor");
  const [intakePatient, setIntakePatient] = useState<Patient | null>(null);
  const [editAppointment, setEditAppointment] = useState<Appointment | null>(
    null,
  );
  const selectedDoctor = doctor || doctors[0]?.user_id || "";
  async function addPatient(e: React.FormEvent) {
    e.preventDefault();
    const result = await run(
      () =>
        post<Patient>("/patients", {
          name,
          dob: dob || null,
          sex: sex || null,
          doctor_id: selectedDoctor,
        }),
      "Patient registered. Add initial documents now.",
    );
    if (result) {
      setName("");
      setDob("");
      setIntakePatient(result);
      reloadPatients();
    }
  }
  async function addAppointment(e: React.FormEvent) {
    e.preventDefault();
    const body = {
      patient_id: appointmentPatient,
      doctor_id: selectedDoctor,
      date: appointmentDate,
      time: appointmentTime,
      reason,
    };
    const result = editAppointment
      ? await run(
          () => patch(`/appointments/${editAppointment.appointment_id}`, body),
          "Appointment updated",
        )
      : await run(() => post("/appointments", body), "Appointment scheduled");
    if (result) {
      setEditAppointment(null);
      reloadAppointments();
    }
  }
  function chooseAppointment(a: Appointment) {
    setEditAppointment(a);
    setAppointmentPatient(a.patient_id);
    setDoctor(a.doctor_id);
    setAppointmentDate(a.date);
    setAppointmentTime(a.time);
    setReason(a.reason);
  }
  async function addAccount(e: React.FormEvent) {
    e.preventDefault();
    const result = await run(
      () =>
        post<User>("/admin/accounts", {
          name: accountName,
          username,
          password,
          role,
        }),
      "Account created",
    );
    if (result) {
      setAccounts([...accounts, result]);
      setPassword("");
      setUsername("");
      setAccountName("");
    }
  }
  async function importSamples() {
    if (!selectedDoctor) return;
    const form = new FormData();
    form.append("doctor_id", selectedDoctor);
    const result = await run(
      () =>
        request<{ patients_created: number }>("/admin/import-samples", {
          method: "POST",
          body: form,
        }),
      "Sample registry import finished",
    );
    if (result) reloadPatients();
  }
  return (
    <>
      {page === "New patient intake" && (
        <>
          <PageHeading
            eyebrow="ADMIN WORKSPACE"
            title="New patient intake"
            text="Create a permanent PrepPulse patient record, then add documents across visits."
          />
          <div className="admin-grid">
            <section className="panel admin-form">
              <div className="panel-heading">
                <div>
                  <div className="eyebrow teal">01 · REGISTER</div>
                  <h3>Patient details</h3>
                </div>
                <Plus size={18} />
              </div>
              <form onSubmit={addPatient}>
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
                    Sex
                    <select
                      value={sex}
                      onChange={(e) => setSex(e.target.value)}
                    >
                      <option value="">Not provided</option>
                      <option>Female</option>
                      <option>Male</option>
                      <option>Other</option>
                    </select>
                  </label>
                </div>
                <label>
                  Assign doctor
                  <select
                    value={selectedDoctor}
                    onChange={(e) => setDoctor(e.target.value)}
                    required
                  >
                    <option value="">Select doctor</option>
                    {doctors.map((d) => (
                      <option key={d.user_id} value={d.user_id}>
                        {d.name}
                      </option>
                    ))}
                  </select>
                </label>
                <button className="primary" disabled={!selectedDoctor}>
                  Register patient
                </button>
              </form>
            </section>
            <section className="panel admin-form">
              <div className="panel-heading">
                <div>
                  <div className="eyebrow teal">02 · ADD DOCUMENTS</div>
                  <h3>Initial or later visit records</h3>
                </div>
                <CloudUpload size={18} />
              </div>
              <p>
                Choose a registered patient to append a document. Additional
                visits use the same permanent PrepPulse ID.
              </p>
              <select
                aria-label="Patient for document upload"
                value={intakePatient?.patient_id || ""}
                onChange={(e) =>
                  setIntakePatient(
                    patients.find((p) => p.patient_id === e.target.value) ||
                      null,
                  )
                }
              >
                <option value="">Select patient</option>
                {patients.map((p) => (
                  <option key={p.patient_id} value={p.patient_id}>
                    {p.name} · {p.patient_id}
                  </option>
                ))}
              </select>
              {intakePatient && (
                <UploadModal
                  patient={intakePatient}
                  onClose={() => setIntakePatient(null)}
                  onUploaded={reloadPatients}
                />
              )}
            </section>
            <section className="panel admin-form">
              <div className="panel-heading">
                <div>
                  <div className="eyebrow teal">03 · EXISTING DATA</div>
                  <h3>Import sample patients</h3>
                </div>
                <FolderOpen size={18} />
              </div>
              <p>
                Import the local dataset once. PrepPulse IDs stay separate from
                folder aliases such as PP001. Repeating the import does not
                create duplicate patients.
              </p>
              <p className="small-muted">
                Folder names are authoritative when a manifest contains a
                conflicting ID.
              </p>
              <button
                className="secondary"
                onClick={importSamples}
                disabled={!selectedDoctor}
              >
                Import local sample registry
              </button>
            </section>
          </div>
        </>
      )}
      {page === "Patient appointments" && (
        <>
          <PageHeading
            eyebrow="SCHEDULE"
            title="Patient appointments"
            text="Schedule visits for assigned doctors. Their Today page refreshes automatically."
          />
          <div className="admin-grid">
            <section className="panel admin-form">
              <h3>
                {editAppointment ? "Edit appointment" : "New appointment"}
              </h3>
              <form onSubmit={addAppointment}>
                <label>
                  Patient
                  <select
                    value={appointmentPatient}
                    onChange={(e) => setAppointmentPatient(e.target.value)}
                    required
                  >
                    <option value="">Select a patient</option>
                    {patients.map((p) => (
                      <option key={p.patient_id} value={p.patient_id}>
                        {p.name} · {p.patient_id}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Doctor
                  <select
                    value={selectedDoctor}
                    onChange={(e) => setDoctor(e.target.value)}
                    required
                  >
                    {doctors.map((d) => (
                      <option key={d.user_id} value={d.user_id}>
                        {d.name}
                      </option>
                    ))}
                  </select>
                </label>
                <div className="form-grid">
                  <label>
                    Visit date
                    <input
                      type="date"
                      value={appointmentDate}
                      onChange={(e) => setAppointmentDate(e.target.value)}
                      required
                    />
                  </label>
                  <label>
                    Time
                    <input
                      type="time"
                      value={appointmentTime}
                      onChange={(e) => setAppointmentTime(e.target.value)}
                      required
                    />
                  </label>
                </div>
                <label>
                  Reason or note
                  <input
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                  />
                </label>
                <div className="form-actions">
                  <button
                    className="primary"
                    disabled={!appointmentPatient || !selectedDoctor}
                  >
                    {editAppointment ? "Save changes" : "Schedule visit"}
                  </button>
                  {editAppointment && (
                    <button
                      className="secondary"
                      type="button"
                      onClick={() => setEditAppointment(null)}
                    >
                      Cancel edit
                    </button>
                  )}
                </div>
              </form>
            </section>
            <section className="panel admin-form">
              <h3>Today’s appointments</h3>
              {appointments.length ? (
                appointments.map((a) => (
                  <div className="appointment-row" key={a.appointment_id}>
                    <span className="card-time">{a.time}</span>
                    <div>
                      <strong>{a.patient_name}</strong>
                      <small>
                        {a.patient_id} · {a.status}
                      </small>
                    </div>
                    <button
                      className="text-button"
                      onClick={() => chooseAppointment(a)}
                      disabled={a.status === "cancelled"}
                    >
                      Edit
                    </button>
                    <button
                      className="text-button"
                      onClick={async () => {
                        await run(
                          () =>
                            post(
                              `/appointments/${a.appointment_id}/cancel`,
                              {},
                            ),
                          "Appointment cancelled",
                        );
                        reloadAppointments();
                      }}
                      disabled={a.status === "cancelled"}
                    >
                      Cancel
                    </button>
                  </div>
                ))
              ) : (
                <p>No appointments today.</p>
              )}
            </section>
          </div>
        </>
      )}
      {page === "Patient directory" && (
        <>
          <PageHeading
            eyebrow="REGISTRY"
            title="Patient directory"
            text="Search patients by name, PrepPulse ID, or existing dataset alias."
          />
          <div className="card-carousel compact">
            {patients.map((p) => (
              <div key={p.patient_id} className="patient-card">
                <div className="patient-avatar">
                  {p.name.slice(0, 2).toUpperCase()}
                </div>
                <strong>{p.name}</strong>
                <small>{p.patient_id}</small>
                <div className="card-meta">
                  {alias(p) || "PrepPulse intake"}
                </div>
                <select
                  aria-label={`Assign doctor to ${p.name}`}
                  defaultValue=""
                  onChange={(e) =>
                    run(
                      () =>
                        post(
                          `/patients/${p.patient_id}/assign/${e.target.value}`,
                          {},
                        ),
                      "Doctor assigned",
                    )
                  }
                >
                  <option value="">Assign another doctor</option>
                  {doctors.map((d) => (
                    <option key={d.user_id} value={d.user_id}>
                      {d.name}
                    </option>
                  ))}
                </select>
              </div>
            ))}
          </div>
        </>
      )}
      {page === "Accounts" && (
        <>
          <PageHeading
            eyebrow="ACCESS CONTROL"
            title="Accounts"
            text="Administrators create and disable doctor accounts. No public registration is available."
          />
          <div className="admin-grid">
            <section className="panel admin-form">
              <h3>Create account</h3>
              <form onSubmit={addAccount}>
                <label>
                  Full name
                  <input
                    value={accountName}
                    onChange={(e) => setAccountName(e.target.value)}
                    required
                  />
                </label>
                <label>
                  Username
                  <input
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
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
                  />
                </label>
                <label>
                  Role
                  <select
                    value={role}
                    onChange={(e) =>
                      setRole(e.target.value as "doctor" | "admin")
                    }
                  >
                    <option value="doctor">Doctor</option>
                    <option value="admin">Admin</option>
                  </select>
                </label>
                <button className="primary">Create account</button>
              </form>
            </section>
            <section className="panel admin-form">
              <h3>Current accounts</h3>
              {accounts.map((a) => (
                <div className="appointment-row" key={a.user_id}>
                  <div className="patient-avatar tiny">
                    {a.name.slice(0, 2).toUpperCase()}
                  </div>
                  <div>
                    <strong>{a.name}</strong>
                    <small>
                      {a.username} · {a.role}
                    </small>
                  </div>
                  <button
                    className="text-button"
                    disabled={
                      a.user_id === user.user_id ||
                      !!(a as User & { disabled?: boolean }).disabled
                    }
                    onClick={async () => {
                      await run(
                        () => patch(`/admin/accounts/${a.user_id}/disable`, {}),
                        "Account disabled",
                      );
                      setAccounts(
                        accounts.map((x) =>
                          x.user_id === a.user_id
                            ? ({ ...x, disabled: true } as User)
                            : x,
                        ),
                      );
                    }}
                  >
                    Disable
                  </button>
                </div>
              ))}
            </section>
          </div>
        </>
      )}
      {page === "Settings" && (
        <>
          <PageHeading
            eyebrow="ADMIN SETTINGS"
            title="Settings"
            text="Local PrepPulse workspace configuration."
          />
          <div className="panel settings-panel">
            <h3>Administrator</h3>
            <p>
              {user.name} · {user.username}
            </p>
            <p>
              Sample records remain local. Configure model paths and session
              secret through environment variables.
            </p>
          </div>
        </>
      )}
    </>
  );
}
