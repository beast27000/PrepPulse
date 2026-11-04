import { useCallback, useEffect, useRef, useState } from "react";
import {
  Activity,
  Bell,
  CalendarDays,
  Check,
  ChevronRight,
  CircleHelp,
  ClipboardCheck,
  CloudUpload,
  FileText,
  FolderOpen,
  HeartPulse,
  LogOut,
  Maximize2,
  PanelLeftClose,
  PanelLeftOpen,
  Move,
  Plus,
  Search,
  Settings2,
  ShieldCheck,
  Sparkles,
  Stethoscope,
  X,
} from "lucide-react";
import {
  AdminPatientOverview,
  Appointment,
  Brief,
  Citation,
  Doc,
  FolderImportResult,
  Finding,
  Patient,
  ProcessingJob,
  User,
  Visit,
  patch,
  post,
  request,
  setCsrf,
} from "./api";
import RecordWorkspace from "./RecordWorkspace";
import CareWorkspace, { CollapsePanel, flushCareDrafts } from "./CareWorkspace";
import UnifiedIntake from "./UnifiedIntake";
import CaregiverAdmin from "./CaregiverAdmin";
import AccountsAdmin from "./AccountsAdmin";
import AdminPatientDetails from "./AdminPatientDetails";
import CareChecklist, { CareCardHeading } from "./CareChecklist";
import { useCareLanguage, useCareLabels } from "./careView";
import "./administration.css";
import VisitHistory, { AppointmentHistory } from "./VisitHistory";
import PatientConversation from "./PatientConversation";
import ProcessBubble from "./ProcessBubble";
import BriefHistory from "./BriefHistory";
import {
  defaultPreferences,
  Preferences,
  readPreferences,
  SettingsControls,
} from "./preferences";

type Page =
  | "Appointment history"
  | "Today"
  | "Patients"
  | "Records"
  | "Care pathways"
  | "Settings"
  | "New patient intake"
  | "Patient appointments"
  | "Patient directory"
  | "Accounts"
  | "Caregivers"
  | "My care plans"
  | "Chat workspace"
  | "Record workspace";
const doctorPages: Page[] = [
  "Today",
  "Patients",
  "Records",
  "Care pathways",
  "Settings",
];
const adminPages: Page[] = [
  "New patient intake",
  "Patient appointments",
  "Patient directory",
  "Accounts",
  "Caregivers",
  "Settings",
];
const navIcons: Record<string, typeof Activity> = {
  Today: CalendarDays,
  Patients: HeartPulse,
  Records: FolderOpen,
  "Care pathways": ClipboardCheck,
  Settings: Settings2,
  "New patient intake": Plus,
  "Patient appointments": CalendarDays,
  "Patient directory": HeartPulse,
  Accounts: ShieldCheck,
  Caregivers: HeartPulse,
  "My care plans": ClipboardCheck,
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
            <small>DIABETES CLINICAL INTELLIGENCE</small>
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
  const proofScrollRef = useRef<HTMLDivElement | null>(null);
  const proofImageRef = useRef<HTMLImageElement | null>(null);
  useEffect(
    () => setFailed(false),
    [citation?.document_id, citation?.page_number],
  );
  const box = citation?.bbox;
  const precise =
    !!box &&
    box.length === 4 &&
    (box[2] - box[0]) * (box[3] - box[1]) <= 100_000;
  function centerProof() {
    if (precise && proofScrollRef.current && proofImageRef.current)
      proofScrollRef.current.scrollTop = Math.max(
        0,
        ((box[1] + box[3]) / 2000) * proofImageRef.current.clientHeight -
          proofScrollRef.current.clientHeight / 2,
      );
  }
  useEffect(centerProof, [
    citation?.document_id,
    citation?.page_number,
    box?.join(","),
  ]);
  return (
    <section className={"panel proof-panel " + (expanded ? "expanded" : "")}>
      <div className="panel-heading">
        <div>
          <div className="eyebrow teal">
            <FileText size={14} /> SOURCE PROOF
          </div>
          <h3>
            {citation?.document_title
              ?.replace(/^\d+_\d{4}-\d{2}-\d{2}_/, "")
              .replace(/\.pdf$/i, "")
              .replaceAll("_", " ") || "Select a finding"}
          </h3>
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
          title="Open record workspace"
          aria-label="Open full record workspace"
        >
          <Maximize2 size={17} />
        </button>
      </div>
      {verified && !failed ? (
        <>
          <div className="source-caption">
            <FileText size={13} />
            {citation?.document_title} <span>page {citation?.page_number}</span>
          </div>
          <div className="proof-scroll" ref={proofScrollRef}>
            <div className="proof-preview">
              <img
                ref={proofImageRef}
                onLoad={centerProof}
                alt="Original document page"
                src={`/api/patients/${patient!.patient_id}/documents/${citation!.document_id}/page/${citation!.page_number}`}
                onError={() => setFailed(true)}
              />
              {precise && (
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
          </div>
          <div className="proof-citation">
            Verified source excerpt · page {citation?.page_number}
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
  onCitation,
  preferences,
  userId,
  onExpand,
}: {
  patient: Patient | null;
  onCitation: (c: Citation) => void;
  preferences: Preferences;
  userId: string;
  onExpand: () => void;
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
          <PatientConversation
            patient={patient}
            userId={userId}
            onOpenRecord={onCitation}
            preferences={preferences}
            onExpand={() => {
              setOpen(false);
              onExpand();
            }}
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
  const [preferences, setPreferences] =
    useState<Preferences>(defaultPreferences);
  const [loading, setLoading] = useState(true);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(
    () => localStorage.getItem("preppulse.sidebar-collapsed") === "true",
  );
  const [page, commitPage] = useState<Page>("Patients");
  const [patients, setPatients] = useState<Patient[]>([]);
  const [selected, setSelected] = useState<Patient | null>(null);
  const [careLanguage] = useCareLanguage(selected?.patient_id || "");
  const careLabel = useCareLabels(
    careLanguage,
    !!user && user.role !== "admin",
  );
  const portalLabel = (text: string) =>
    user?.role === "caregiver" ? careLabel(text) : text;
  const selectedPatientRef = useRef<string | null>(null);
  selectedPatientRef.current = selected?.patient_id || null;
  const [search, setSearch] = useState("");
  const [showSearch, setShowSearch] = useState(false);
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [documents, setDocuments] = useState<Doc[]>([]);
  const [brief, setBrief] = useState<Brief | null>(null);
  const [job, setJob] = useState<ProcessingJob | null>(null);
  const [visits, setVisits] = useState<Visit[]>([]);
  const [citation, setCitation] = useState<Citation | null>(null);
  const [chatExpanded, setChatExpanded] = useState(false);
  const [rightClosed, setRightClosed] = useState(false);
  const [requestedVisit, setRequestedVisit] = useState("");
  const [language, setLanguage] = useState("en");
  const [notice, setNotice] = useState("");
  const [apiMismatch, setApiMismatch] = useState(false);
  const [historical, setHistorical] = useState<{
    patient: Patient;
    visit: Visit | null;
    brief: Brief | null;
    documents: Doc[];
    visits: Visit[];
    snapshot_available: boolean;
  } | null>(null);
  const historicalRef = useRef(historical);
  historicalRef.current = historical;
  const [uploadOpen, setUploadOpen] = useState(false);
  const [chatFullscreen, setChatFullscreen] = useState(false);
  const [recordReturnPage, setRecordReturnPage] = useState<Page>("Patients");
  const [accounts, setAccounts] = useState<User[]>([]);
  const activeVisit = visits.find(
    (v) =>
      !historical && v.status === "active" && v.doctor_id === user?.user_id,
  );
  const nav: Page[] =
    user?.role === "admin"
      ? adminPages
      : user?.role === "caregiver"
        ? ["My care plans"]
        : doctorPages;
  async function setPage(next: Page) {
    if (await flushCareDrafts()) {
      commitPage(next);
      return true;
    }
    setNotice(
      "Complete the care draft fields and wait for saving before switching pages.",
    );
    return false;
  }
  function acceptLogin(next: User) {
    setPreferences(readPreferences(next.user_id));
    setUser(next);
    setPage(
      next.role === "admin"
        ? "New patient intake"
        : next.role === "caregiver"
          ? "My care plans"
          : "Patients",
    );
  }
  useEffect(() => {
    if (!user) return;
    try {
      localStorage.setItem(
        `preppulse.preferences.${user.user_id}`,
        JSON.stringify(preferences),
      );
    } catch {
      /* Display preferences still work for this session. */
    }
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      document.documentElement.dataset.theme =
        preferences.appearance === "system"
          ? media.matches
            ? "dark"
            : "light"
          : preferences.appearance;
      document.documentElement.dataset.textSize = preferences.textSize;
      document.documentElement.dataset.contrast = preferences.contrast;
    };
    apply();
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [user?.user_id, preferences]);

  const loadPatients = useCallback(
    async (q = "") => {
      if (!user) return;
      try {
        const rows = await request<Patient[]>(
          "/patients?q=" + encodeURIComponent(q),
        );
        setPatients(rows);
        if (!selected && rows.length && user.role !== "admin")
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
    if (historicalRef.current?.patient.patient_id === id) {
      const old = historicalRef.current;
      setDocuments(old.documents);
      setBrief(old.brief);
      setVisits(old.visits);
      setJob(null);
      return;
    }
    const results = await Promise.allSettled([
      request<Doc[]>(`/patients/${id}/documents`),
      request<{ brief: Brief }>(`/patients/${id}/brief`),
      request<Visit[]>(`/patients/${id}/visits`),
      request<ProcessingJob | null>(`/patients/${id}/brief/jobs/latest`),
    ]);
    if (selectedPatientRef.current !== id) return;
    if (results[0].status === "fulfilled") setDocuments(results[0].value);
    if (results[1].status === "fulfilled") {
      const nextBrief = results[1].value.brief;
      setBrief(nextBrief);
      const firstEvidence =
        nextBrief.priority_findings.find(
          (item) => item.citation?.source_verified,
        )?.citation ||
        nextBrief.trajectory.kpis.find((item) => item.citation?.source_verified)
          ?.citation;
      if (firstEvidence) setCitation((current) => current || firstEvidence);
    } else setBrief(null);
    if (results[2].status === "fulfilled") setVisits(results[2].value);
    if (results[3].status === "fulfilled") setJob(results[3].value);
  }, [selected, user]);
  const loadAppointments = useCallback(async () => {
    if (!user || user.role === "caregiver") return;
    try {
      setAppointments(await request<Appointment[]>("/appointments"));
    } catch (err) {
      setNotice((err as Error).message);
    }
  }, [user]);
  useEffect(() => {
    async function checkRuntime() {
      try {
        const r = await fetch("/api/runtime");
        const value = r.ok ? await r.json() : null;
        setApiMismatch(value?.contract !== "preppulse-ui-care-4");
      } catch {
        setApiMismatch(true);
      }
    }
    checkRuntime();
    const timer = setInterval(checkRuntime, 30000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    request<User>("/auth/me")
      .then((u) => {
        setCsrf(u.csrf);
        acceptLogin(u);
        setPage(
          u.role === "admin"
            ? "New patient intake"
            : u.role === "caregiver"
              ? "My care plans"
              : "Patients",
        );
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);
  useEffect(() => {
    if (user) loadPatients();
  }, [user]);
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "instant" });
  }, [page, chatFullscreen]);
  useEffect(() => {
    setDocuments([]);
    setBrief(null);
    setJob(null);
    setVisits([]);
    setCitation(null);
    loadSelected();
  }, [selected?.patient_id, historical]);
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
        if (next?.status === "complete") {
          await loadSelected();
          setNotice(
            "Clinical analysis complete. Review the source-linked findings.",
          );
        }
      } catch {}
    }, 3000);
    return () => clearInterval(timer);
  }, [selected, job?.status, loadSelected]);
  useEffect(() => {
    if (user?.role !== "admin") return;
    const load = () =>
      request<User[]>("/admin/accounts")
        .then(setAccounts)
        .catch(() => {});
    load();
    const timer = setInterval(load, 10000);
    return () => clearInterval(timer);
  }, [user]);
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
  async function pick(p: Patient) {
    if (!(await flushCareDrafts())) {
      setNotice(
        "Complete and save the current care draft before changing patients.",
      );
      return;
    }
    historicalRef.current = null;
    setHistorical(null);
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
  function openRecordWorkspace() {
    setRecordReturnPage(
      chatFullscreen || page === "Chat workspace"
        ? "Chat workspace"
        : "Patients",
    );
    setChatFullscreen(false);
    setPage("Record workspace");
  }
  function selectEvidence(source: Citation | null | undefined, title: string) {
    setRightClosed(false);
    setCitation(
      source
        ? { ...source }
        : {
            document_id: "",
            document_title: title,
            page_number: 1,
            bbox: [],
            source_verified: false,
          },
    );
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
  async function choosePatient(p: Patient) {
    if (await flushCareDrafts()) {
      historicalRef.current = null;
      setHistorical(null);
      setSelected(p);
    } else
      setNotice(
        "Complete and save the current care draft before changing patients.",
      );
  }
  async function openHistorical(p: Patient, visitId?: string) {
    if (!(await flushCareDrafts())) return;
    try {
      const value = await request<NonNullable<typeof historical>>(
        `/patients/${p.patient_id}/historical-workspace${visitId ? `?visit_id=${visitId}` : ""}`,
      );
      historicalRef.current = value;
      setHistorical(value);
      setSelected(value.patient);
      setDocuments(value.documents);
      setBrief(value.brief);
      setVisits(value.visits);
      setJob(null);
      setCitation(null);
      setChatFullscreen(false);
      commitPage("Patients");
    } catch (e) {
      setNotice((e as Error).message);
    }
  }
  async function expandChat() {
    if (await flushCareDrafts()) setChatFullscreen(true);
    else setNotice("Complete and save the care draft before opening chat.");
  }
  async function logout() {
    if (!(await flushCareDrafts())) {
      setNotice("Complete and save the care draft before signing out.");
      return;
    }
    await run(() => post("/auth/logout", {}));
    setUser(null);
    setSelected(null);
    setBrief(null);
    document.documentElement.dataset.theme = "light";
    document.documentElement.dataset.textSize = "standard";
    document.documentElement.dataset.contrast = "standard";
  }
  if (loading) return <div className="boot">Opening PrepPulse…</div>;
  if (!user) return <Login onLogin={acceptLogin} />;

  return (
    <div
      className={"app-shell " + (sidebarCollapsed ? "sidebar-collapsed" : "")}
      lang={user.role === "caregiver" ? careLanguage : undefined}
    >
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">
            <Activity size={23} />
          </span>
          <span>
            <strong>PrepPulse</strong>
            <small>DIABETES CLINICAL INTELLIGENCE</small>
          </span>
        </div>
        <nav aria-label="Main navigation">
          <span className="nav-caption">{portalLabel("WORKSPACE")}</span>
          {nav.map((item) => {
            const Icon = navIcons[item];
            return (
              <button
                key={item}
                title={portalLabel(item)}
                aria-label={portalLabel(item)}
                className={"nav-item " + (page === item ? "active" : "")}
                onClick={async () => {
                  if (!(await setPage(item))) return;
                  if (item === "Patients") {
                    historicalRef.current = null;
                    setHistorical(null);
                  }
                  setChatFullscreen(false);
                }}
              >
                <Icon size={17} />
                <span className="nav-label">{portalLabel(item)}</span>
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
            <small>
              {user.role === "admin"
                ? "Administrator"
                : user.role === "caregiver"
                  ? careLabel("Caregiver")
                  : "Doctor"}
            </small>
          </div>
          <button
            className="icon-button"
            onClick={logout}
            title={portalLabel("Sign out")}
          >
            <LogOut size={17} />
          </button>
        </div>
      </aside>
      <div className="app-body">
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="icon-button sidebar-toggle"
              title={
                sidebarCollapsed ? "Expand navigation" : "Collapse navigation"
              }
              aria-label={
                sidebarCollapsed ? "Expand navigation" : "Collapse navigation"
              }
              onClick={() => {
                setSidebarCollapsed(!sidebarCollapsed);
                localStorage.setItem(
                  "preppulse.sidebar-collapsed",
                  String(!sidebarCollapsed),
                );
              }}
            >
              {sidebarCollapsed ? (
                <PanelLeftOpen size={18} />
              ) : (
                <PanelLeftClose size={18} />
              )}
            </button>
            {portalLabel("Workspace")} <ChevronRight size={14} />{" "}
            <strong>
              {chatFullscreen ? "Chat workspace" : portalLabel(page)}
            </strong>
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
        {apiMismatch && (
          <div className="api-version-notice" role="alert">
            The API process is older than this UI. Run{" "}
            <code>
              powershell -ExecutionPolicy Bypass -File scripts/start_ui_api.ps1
            </code>{" "}
            from the PrepPulse folder, then refresh and sign in. New
            caregiver/history features cannot work until the API is restarted.
          </div>
        )}
        {notice && (
          <div className="notice" role="status">
            <span>{notice}</span>
            <button onClick={() => setNotice("")} aria-label="Dismiss">
              <X size={14} />
            </button>
          </div>
        )}
        <main
          className={
            "content " +
            (page === "Chat workspace" || chatFullscreen
              ? "conversation-content"
              : "")
          }
        >
          {user.role === "doctor" ? (
            <>
              {page === "Appointment history" && (
                <AppointmentHistory
                  full
                  onBack={() => setPage("Records")}
                  onOpen={(a) => {
                    const p = patients.find(
                      (x) => x.patient_id === a.patient_id,
                    );
                    if (p) openHistorical(p, a.visit_id);
                  }}
                />
              )}
              {page === "Patients" && !chatFullscreen && (
                <>
                  {historical && (
                    <div className="historical-banner">
                      <strong>
                        Historical patient workspace
                        {historical.visit
                          ? ` · ${new Date(historical.visit.started_at).toLocaleString()}`
                          : ""}
                      </strong>
                      <p>
                        {historical.snapshot_available
                          ? "Showing the brief saved at this visit. Source Proof and chat remain available."
                          : "This older visit has no saved brief snapshot. The latest available brief is shown for reference, not as a reconstruction of that visit."}{" "}
                        Chat searches all uploaded patient records.
                      </p>
                      <button
                        className="secondary"
                        onClick={() => setPage("Records")}
                      >
                        Back to Records
                      </button>
                    </div>
                  )}
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
                          <button
                            className="secondary"
                            onClick={() => setRightClosed(!rightClosed)}
                          >
                            {rightClosed
                              ? "Show assistant / care panels"
                              : "Collapse right panels"}
                          </button>
                          {!historical && (
                            <>
                              <button
                                className="secondary"
                                onClick={startVisit}
                              >
                                {activeVisit ? "Visit active" : "Start visit"}
                              </button>
                              <button
                                className="secondary"
                                onClick={generateBrief}
                                disabled={
                                  job?.status === "queued" ||
                                  job?.status === "running" ||
                                  !documents.length
                                }
                              >
                                <Activity size={17} /> Analyze records
                              </button>
                              <button
                                className="primary"
                                onClick={() => setUploadOpen(true)}
                              >
                                <CloudUpload size={17} /> Upload new record
                              </button>
                            </>
                          )}
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
                        (rightClosed
                          ? "rail-collapsed"
                          : chatExpanded
                            ? "panel-wide"
                            : "")
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
                                {selected.dob || selected.age != null
                                  ? `${ageOf(selected.dob) ?? selected.age} years / ${selected.sex || brief?.gender || "Not recorded"}`
                                  : brief?.age_sex ||
                                    `Age unavailable / ${selected.sex || "Not recorded"}`}{" "}
                                <span>·</span>{" "}
                                {brief?.classification.stage ||
                                  "Classification pending"}{" "}
                                <span>·</span> {selected.patient_id}
                                {alias(selected) ? ` · ${alias(selected)}` : ""}
                              </p>
                            </div>
                            <span className="status-pill">
                              <ShieldCheck size={13} />
                              {job?.status === "queued" ||
                              job?.status === "running"
                                ? "Updating analysis"
                                : brief
                                  ? "Ready to review"
                                  : "Awaiting analysis"}
                            </span>
                          </div>
                          {job &&
                            ["queued", "running", "failed"].includes(
                              job.status,
                            ) && (
                              <div className={"job-banner " + job.status}>
                                {job.status === "failed"
                                  ? `Analysis failed: ${job.error || "Try again"}`
                                  : `Analysis ${job.status} · ${job.stage || "waiting"} · ${job.documents_ready || 0}/${job.documents_total || documents.length} documents ready`}
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
                                  !documents.length ||
                                  job?.status === "queued" ||
                                  job?.status === "running"
                                }
                              >
                                Run clinical analysis
                              </button>
                            </div>
                          ) : (
                            <>
                              <BriefHistory
                                brief={brief}
                                onCitation={(source) =>
                                  selectEvidence(source, "Record")
                                }
                              />
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
                                              selectEvidence(k.citation, k.name)
                                            }
                                          >
                                            <small>{k.name}</small>
                                            <strong>
                                              {k.value}
                                              {k.unit &&
                                              !k.value.includes(k.unit)
                                                ? k.unit === "%"
                                                  ? "%"
                                                  : ` ${k.unit}`
                                                : ""}
                                            </strong>
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
                                            selectEvidence(g.citation, g.title)
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
                                      No source-backed care gap was confirmed.
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
                                            selectEvidence(
                                              m.citations?.find(
                                                (c) => c.source_verified,
                                              ) || m.source_a_citation,
                                              m.title,
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
                                {!historical && (
                                  <div className="brief-card blue">
                                    <div className="card-head">
                                      <span className="card-no">04</span>
                                      <div>
                                        <CareCardHeading patient={selected} />
                                      </div>
                                      <ClipboardCheck size={17} />
                                    </div>
                                    <CareChecklist
                                      key={selected.patient_id}
                                      patient={selected}
                                      summary
                                      onEdit={() => setPage("Care pathways")}
                                    />
                                  </div>
                                )}
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
                                    {brief.trajectory.kpis[0]?.unit === "%" &&
                                    !brief.trajectory.kpis[0]?.value.includes(
                                      "%",
                                    )
                                      ? "%"
                                      : ""}
                                  </strong>
                                  <small>
                                    {brief.trajectory.kpis[0]?.name ||
                                      "No metric"}
                                  </small>
                                </div>
                                <div>
                                  <span>OPEN ITEMS</span>
                                  <strong>
                                    {brief.priority_findings.length}
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
                                            selectEvidence(f.citation, f.title)
                                          }
                                        >
                                          <FileText size={13} />
                                          {f.citation?.source_verified
                                            ? `${f.citation.document_title} · ${shortDate(f.date)} · p. ${f.citation.page_number}`
                                            : "No verified direct source attached"}
                                        </button>
                                        {f.related_citations?.map(
                                          (source, index) => (
                                            <button
                                              className="source-link"
                                              key={index}
                                              onClick={() =>
                                                setCitation(source)
                                              }
                                            >
                                              <FileText size={13} />
                                              Previous measurement ·{" "}
                                              {source.document_title}
                                            </button>
                                          ),
                                        )}
                                      </div>
                                      <div
                                        className="finding-controls"
                                        hidden={!!historical}
                                      >
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
                        <div className="bottom-actions" hidden={!!historical}>
                          <button
                            className="secondary"
                            onClick={generateBrief}
                            disabled={
                              job?.status === "queued" ||
                              job?.status === "running"
                            }
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
                                  expandChat();
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
                        hidden={rightClosed}
                        className={
                          "right-column " +
                          (chatExpanded ? "chat-inline-expanded" : "")
                        }
                      >
                        <CollapsePanel title="PrepPulse assistant">
                          <button
                            className="secondary inline-expand"
                            onClick={() => setChatExpanded((v) => !v)}
                          >
                            {chatExpanded
                              ? "Standard column width"
                              : "Expand assistant inline"}
                          </button>
                          <PatientConversation
                            patient={selected}
                            userId={user.user_id}
                            preferences={preferences}
                            onOpenRecord={(source) => {
                              setCitation(source);
                              openRecordWorkspace();
                            }}
                            onExpand={() => expandChat()}
                          />
                        </CollapsePanel>
                        <CollapsePanel
                          title="Source Proof"
                          revealKey={citation}
                        >
                          <SourceProof
                            patient={selected}
                            citation={citation}
                            expanded={false}
                            onExpand={openRecordWorkspace}
                          />
                        </CollapsePanel>
                        {!historical && (
                          <CollapsePanel
                            title={careLabel("Caregiver handoff / checklist")}
                          >
                            <section className="panel checklist-panel">
                              <CareChecklist
                                key={selected.patient_id}
                                patient={selected}
                                onEdit={() => setPage("Care pathways")}
                              />
                            </section>
                          </CollapsePanel>
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
                    text="Browse previous visits, signed care pathways, caregiver follow-up and original source records."
                  />
                  <PatientCarousel
                    patients={patients}
                    selected={selected}
                    onPick={(p) => {
                      setSelected(p);
                      setRequestedVisit("");
                    }}
                  />
                  <AppointmentHistory
                    onExpand={() => setPage("Appointment history")}
                    onOpen={(a) => {
                      const p = patients.find(
                        (x) => x.patient_id === a.patient_id,
                      );
                      if (p) {
                        setSelected(p);
                        setRequestedVisit(a.visit_id || "");
                      }
                    }}
                  />
                  {selected && (
                    <VisitHistory
                      key={selected.patient_id}
                      patient={selected}
                      visits={visits}
                      initialVisit={requestedVisit}
                      onRecords={() => {
                        setCitation(null);
                        setRecordReturnPage("Records");
                        setPage("Record workspace");
                      }}
                      onEvidence={(source) => {
                        setCitation(source);
                        setRecordReturnPage("Records");
                        setPage("Record workspace");
                      }}
                    />
                  )}
                </>
              )}
              {page === "Care pathways" && (
                <>
                  <PageHeading
                    eyebrow="CONTINUITY OF CARE"
                    title="Care pathways"
                    text="Review and sign the visit checklist, clinician notes and prescription schedule."
                  />
                  <PatientCarousel
                    patients={patients}
                    selected={selected}
                    onPick={choosePatient}
                  />
                  {selected && (
                    <section className="panel pathway-panel">
                      <CareWorkspace
                        key={selected.patient_id}
                        patient={selected}
                        role="doctor"
                        onStart={startVisit}
                        onAdmission={setAdmission}
                        onEnded={() => {
                          loadSelected();
                          setPage("Records");
                        }}
                      />
                    </section>
                  )}
                </>
              )}
              {page === "Settings" && (
                <>
                  <PageHeading
                    eyebrow="PREFERENCES"
                    title="Settings"
                    text="Your local PrepPulse workspace settings."
                  />
                  <SettingsControls
                    user={user}
                    value={preferences}
                    onChange={setPreferences}
                  />
                </>
              )}
              {page === "Record workspace" && selected && (
                <RecordWorkspace
                  patient={selected}
                  documents={documents}
                  citation={citation}
                  onClose={() => setPage(recordReturnPage)}
                />
              )}
              {(page === "Chat workspace" || chatFullscreen) && (
                <>
                  <div className="conversation-page-top">
                    <span>
                      {selected?.name || "Select a patient"} · Patient
                      conversation
                    </span>
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
                  <PatientConversation
                    patient={selected}
                    userId={user.user_id}
                    preferences={preferences}
                    full
                    onOpenRecord={(source) => {
                      setCitation(source);
                      openRecordWorkspace();
                    }}
                  />
                </>
              )}
            </>
          ) : user.role === "caregiver" ? (
            <>
              <PageHeading
                eyebrow={careLabel("PREPPULSE CARE")}
                title={careLabel("My care plans")}
                text={careLabel(
                  "Your assigned patients, signed instructions, daily tasks and notes for the doctor.",
                )}
              />
              <PatientCarousel
                patients={patients}
                selected={selected}
                onPick={choosePatient}
                label={careLabel}
              />
              {selected ? (
                <section className="panel pathway-panel">
                  <CareWorkspace
                    key={selected.patient_id}
                    patient={selected}
                    role="caregiver"
                  />
                </section>
              ) : (
                <section className="panel empty-page">
                  {careLabel(
                    "No patient has been assigned. Ask your administrator to assign caregiver access.",
                  )}
                </section>
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
              preferences={preferences}
              setPreferences={setPreferences}
              navigate={setPage}
            />
          )}
        </main>
        {user.role === "doctor" &&
          page !== "Patients" &&
          page !== "Chat workspace" &&
          page !== "Record workspace" &&
          !chatFullscreen && (
            <FloatingAssistant
              patient={selected}
              userId={user.user_id}
              onExpand={() => expandChat()}
              onCitation={(source) => {
                setCitation(source);
                openRecordWorkspace();
              }}
              preferences={preferences}
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
      {(job?.status === "running" || job?.status === "queued") && (
        <ProcessBubble
          label={job.stage || "Waiting for analysis"}
          detail={`${job.documents_ready || 0}/${job.documents_total || documents.length} records processed`}
          offset={page === "Chat workspace" || chatFullscreen}
        />
      )}
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
  label = (text) => text,
}: {
  patients: Patient[];
  selected: Patient | null;
  onPick: (p: Patient) => void;
  label?: (text: string) => string;
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
            {alias(p) || label("PrepPulse intake")} ·{" "}
            {ageOf(p.dob) ?? p.age ?? "—"} {label("years")}
          </div>
          <span className="card-open">
            {label("View patient")} <ChevronRight size={15} />
          </span>
        </button>
      ))}
    </div>
  );
}

function UploadModal({
  visitId,
  initialDate,
  patient,
  onClose,
  onUploaded,
}: {
  patient: Patient;
  visitId?: string;
  initialDate?: string;
  onClose: () => void;
  onUploaded: () => void;
}) {
  const [files, setFiles] = useState<File[]>([]);
  const [folder, setFolder] = useState(false);
  const [type, setType] = useState("consult");
  const [date, setDate] = useState(initialDate || today());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<FolderImportResult | null>(null);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (folder) input.current?.setAttribute("webkitdirectory", "");
    else input.current?.removeAttribute("webkitdirectory");
    setFiles([]);
  }, [folder]);
  useEffect(() => {
    if (!result?.job || !["queued", "running"].includes(result.job.status))
      return;
    const timer = setInterval(async () => {
      try {
        let job: ProcessingJob | null;
        try {
          job = await request<ProcessingJob>(
            `/patients/${patient.patient_id}/brief/jobs/latest`,
          );
        } catch {
          job = (
            await request<AdminPatientOverview>(
              `/admin/patients/${patient.patient_id}/overview`,
            )
          ).latest_job;
        }
        if (job)
          setResult((current) => (current ? { ...current, job } : current));
        onUploaded();
      } catch (e) {
        setError((e as Error).message);
      }
    }, 3000);
    return () => clearInterval(timer);
  }, [result?.job?.status, patient.patient_id]);
  async function upload(e: React.FormEvent) {
    e.preventDefault();
    if (!files.length) return;
    const form = new FormData();
    if (folder)
      files.forEach((file) => {
        form.append("files", file, file.name);
        form.append("paths", file.webkitRelativePath);
      });
    else {
      form.append("file", files[0]);
      form.append("document_type", type);
      form.append("visit_date", date);
      if (visitId) form.append("visit_id", visitId);
    }
    setBusy(true);
    setError("");
    try {
      const response = await request<FolderImportResult>(
        `/patients/${patient.patient_id}/${folder ? "folder" : "documents"}`,
        { method: "POST", body: form },
      );
      onUploaded();
      if (folder) {
        setResult(response);
        setFiles([]);
      } else onClose();
    } catch (e) {
      setError((e as Error).message);
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
            <h2>Upload patient records</h2>
            <p>
              {patient.name} · {patient.patient_id}
            </p>
          </div>
          <button
            className="icon-button"
            onClick={onClose}
            aria-label="Close upload"
          >
            <X size={18} />
          </button>
        </div>
        <div className="form-actions">
          <button
            className={!folder ? "primary" : "secondary"}
            onClick={() => setFolder(false)}
          >
            Upload record
          </button>
          <button
            className={folder ? "primary" : "secondary"}
            onClick={() => setFolder(true)}
          >
            Upload patient folder
          </button>
        </div>
        <form onSubmit={upload}>
          <label>
            {folder ? "Patient folder (ID_Patient_Name)" : "Document"}
            <input
              key={String(folder)}
              ref={input}
              type="file"
              multiple={folder}
              accept={folder ? undefined : ".pdf,.png,.jpg,.jpeg"}
              onChange={(e) => setFiles(Array.from(e.target.files || []))}
              required
            />
          </label>
          {!folder && (
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
          )}
          {!!files.length && <p>{files.length} files selected</p>}
          {error && (
            <div className="error" role="alert">
              {error}
            </div>
          )}
          <div className="form-actions">
            <button className="secondary" type="button" onClick={onClose}>
              Close
            </button>
            <button className="primary" disabled={busy || !files.length}>
              {busy ? "Uploading…" : folder ? "Upload folder" : "Upload record"}
            </button>
          </div>
        </form>
        {result && (
          <div role="status">
            <p>
              {result.files_saved} files saved · {result.files_unchanged}{" "}
              unchanged · {result.documents_queued} documents queued
            </p>
            <p>
              {result.job?.stage || result.job?.status} ·{" "}
              {result.job?.documents_ready || 0}/
              {result.job?.documents_total || result.documents_queued} processed
            </p>
            {result.job?.error && <p className="error">{result.job.error}</p>}
          </div>
        )}
      </section>
    </div>
  );
}

function AdminPages({
  navigate,
  page,
  user,
  patients,
  accounts,
  setAccounts,
  reloadPatients,
  reloadAppointments,
  appointments,
  run,
  preferences,
  setPreferences,
}: {
  page: Page;
  navigate: (page: Page) => void;
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
  preferences: Preferences;
  setPreferences: (value: Preferences) => void;
}) {
  const doctors = accounts.filter(
    (a) =>
      a.role === "doctor" && !(a as User & { disabled?: boolean }).disabled,
  );
  const [doctor, setDoctor] = useState("");
  const [appointmentPatient, setAppointmentPatient] = useState("");
  const [appointmentDate, setAppointmentDate] = useState(today());
  const [appointmentTime, setAppointmentTime] = useState(
    preferences.appointmentTime,
  );
  const [reason, setReason] = useState("");
  const [directoryPatient, setDirectoryPatient] = useState<Patient | null>(
    null,
  );
  const [editAppointment, setEditAppointment] = useState<Appointment | null>(
    null,
  );
  const [directoryUpload, setDirectoryUpload] = useState<{
    visitId?: string;
    day?: string;
  } | null>(null);
  const selectedDoctor = doctor || doctors[0]?.user_id || "";
  useEffect(() => {
    if (!editAppointment) setAppointmentTime(preferences.appointmentTime);
  }, [preferences.appointmentTime]);
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
  return (
    <>
      {page === "New patient intake" && (
        <>
          <PageHeading
            eyebrow="ADMIN WORKSPACE"
            title="New patient intake"
            text="Create a permanent PrepPulse patient record, then add documents across visits."
          />
          <UnifiedIntake
            patients={patients}
            accounts={accounts}
            reload={reloadPatients}
          />
        </>
      )}
      {page === "Caregivers" && (
        <CaregiverAdmin
          patients={patients}
          accounts={accounts}
          setAccounts={setAccounts}
        />
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
                      step={preferences.appointmentInterval * 60}
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
          <AppointmentHistory
            onExpand={() => navigate("Appointment history")}
            onOpen={(a) => {
              const p = patients.find((x) => x.patient_id === a.patient_id);
              if (p) {
                setDirectoryPatient(p);
                navigate("Patient directory");
              }
            }}
          />
        </>
      )}
      {page === "Appointment history" && (
        <AppointmentHistory
          full
          onBack={() => navigate("Patient appointments")}
          onOpen={(a) => {
            const p = patients.find((x) => x.patient_id === a.patient_id);
            if (p) {
              setDirectoryPatient(p);
              navigate("Patient directory");
            }
          }}
        />
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
              <div
                key={p.patient_id}
                className={
                  "patient-card " +
                  (directoryPatient?.patient_id === p.patient_id
                    ? "chosen"
                    : "")
                }
              >
                <button
                  className="directory-card-button"
                  onClick={() => setDirectoryPatient(p)}
                  aria-label={`View admin details for ${p.name}`}
                >
                  <div className="patient-avatar">
                    {p.name.slice(0, 2).toUpperCase()}
                  </div>
                  <strong>{p.name}</strong>
                  <small>{p.patient_id}</small>
                  <div className="card-meta">
                    {alias(p) || "PrepPulse intake"}
                  </div>
                  <span className="card-open">
                    View admin details <ChevronRight size={15} />
                  </span>
                </button>
                <select
                  aria-label={`Assign doctor to ${p.name}`}
                  defaultValue=""
                  onChange={async (e) => {
                    await run(
                      () =>
                        post(
                          `/patients/${p.patient_id}/assign/${e.target.value}`,
                          {},
                        ),
                      "Doctor assigned",
                    );
                  }}
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
          {directoryPatient && (
            <AdminPatientDetails
              key={directoryPatient.patient_id}
              patient={directoryPatient}
              doctors={doctors}
              onClose={() => setDirectoryPatient(null)}
              onUpdated={reloadPatients}
              onUpload={(visitId, day) => setDirectoryUpload({ visitId, day })}
            />
          )}
          {directoryPatient && directoryUpload && (
            <UploadModal
              patient={directoryPatient}
              onClose={() => setDirectoryUpload(null)}
              onUploaded={reloadPatients}
              visitId={directoryUpload.visitId}
              initialDate={directoryUpload.day}
            />
          )}
        </>
      )}
      {page === "Accounts" && (
        <AccountsAdmin
          user={user}
          accounts={accounts}
          setAccounts={setAccounts}
        />
      )}
      {page === "Settings" && (
        <>
          <PageHeading
            eyebrow="ADMIN SETTINGS"
            title="Settings"
            text="Local PrepPulse workspace configuration."
          />
          <SettingsControls
            user={user}
            value={preferences}
            onChange={setPreferences}
          />
        </>
      )}
    </>
  );
}
