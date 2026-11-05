import { useEffect, useRef, useState } from "react";
import { Patient, User, post, request } from "./api";
import "./care.css";
import {
  notifyCareChanged,
  subscribeCare,
  useCareLanguage,
  useCareLabels,
  useCareTranslation,
  requestCareLanguage,
  careText,
  careSnapshotReady,
} from "./careView";

export const languages: Record<string, string> = {
  en: "English",
  hi: "हिन्दी",
  ta: "தமிழ்",
  bn: "বাংলা",
  or: "ଓଡ଼ିଆ",
  te: "తెలుగు",
};
const dayNow = () =>
  new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(
    new Date(),
  );
type Item = {
  item_id: string;
  text: string;
  texts?: Record<string, string>;
  source_language: string;
  frequency: "once" | "daily";
  source: "agent" | "doctor";
};
type Medication = {
  medication_id: string;
  name: string;
  dose: string;
  dose_texts?: Record<string, string>;
  kind: string;
  start_date: string;
  duration: number;
  duration_unit: string;
  times: string[];
  food: string;
};
type Draft = {
  checks?: Record<string, boolean>;
  revision: number;
  items: Item[];
  medications: Medication[];
  doctor_notes: string;
  notes_language: string;
  notes_texts?: Record<string, string>;
  translation_status: string;
  language_status?: Record<
    string,
    { status: string; completed: number; total: number }
  >;
};
type Plan = Draft & {
  pathway_id: string;
  approved_at: string;
  approved_name?: string;
  mode: string;
  visit_id: string;
};
type Report = {
  completed: boolean;
  reported_name: string;
  reported_at: string;
};
type Task = {
  task_id: string;
  text: string;
  texts?: Record<string, string>;
  kind: string;
  slot?: string;
  medication?: Medication;
  report?: Report;
};
type Followup = {
  tasks: Task[];
  reports: (Report & { task_id: string; day?: string })[];
  notes: {
    note_id: string;
    text: string;
    author_name: string;
    created_at: string;
  }[];
  past_due_unreported: number;
};
type Bundle = {
  suggestions?: { text_en: string; texts?: Record<string, string> }[];
  suggestion_revision?: number;
  suggestion_status?: Record<
    string,
    { status: string; completed: number; total: number }
  >;
  draft: Draft | null;
  visit: { visit_id: string; admitted: boolean } | null;
  plans: Plan[];
  followup: Followup | null;
  day: string;
};
const id = () => crypto.randomUUID();
const draftEditors = new Map<string, () => Promise<boolean>>();
export async function flushCareDrafts() {
  return (
    await Promise.all([...draftEditors.values()].map((save) => save()))
  ).every(Boolean);
}

export function CollapsePanel({
  title,
  children,
  revealKey,
}: {
  title: string;
  children: React.ReactNode;
  revealKey?: unknown;
}) {
  const [closed, setClosed] = useState(false);
  useEffect(() => {
    if (revealKey) setClosed(false);
  }, [revealKey]);
  return (
    <section className={"collapsible-care " + (closed ? "is-closed" : "")}>
      <button
        className="secondary collapse-heading"
        aria-expanded={!closed}
        onClick={() => setClosed(!closed)}
      >
        {closed ? "+" : "−"} {title}
      </button>
      <div hidden={closed}>{children}</div>
    </section>
  );
}

export default function CareWorkspace({
  patient,
  role,
  compact = false,
  historyOnly = false,
  initialPlanId,
  onEnded,
  onStart,
  onAdmission,
}: {
  patient: Patient;
  role: User["role"];
  compact?: boolean;
  historyOnly?: boolean;
  initialPlanId?: string;
  onEnded?: () => void;
  onStart?: () => void;
  onAdmission?: (admitted: boolean) => void;
}) {
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [language, setLanguage] = useCareLanguage(patient.patient_id);
  const [editingItems, setEditingItems] = useState(new Set<string>());
  const label = useCareLabels(language);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [reporting, setReporting] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [newItem, setNewItem] = useState("");
  const [planId, setPlanId] = useState("");
  const [follow, setFollow] = useState<Followup | null>(null);
  const [note, setNote] = useState("");
  const [day, setDay] = useState(dayNow());
  const lastDay = useRef(dayNow());
  const draftRef = useRef(draft);
  draftRef.current = draft;
  const dirtyRef = useRef(dirty);
  dirtyRef.current = dirty;
  const saving = useRef(false);
  const editVersion = useRef(0);
  const saveRef = useRef<() => Promise<boolean>>(async () => true);
  const lastAttempt = useRef(-1);
  const activePatient = useRef(patient.patient_id);
  activePatient.current = patient.patient_id;
  async function load() {
    try {
      const data = await request<Bundle>(
        `/care/patients/${patient.patient_id}?day=${day}`,
      );
      if (activePatient.current !== patient.patient_id) return;
      setBundle(data);
      setError("");
      if (!dirtyRef.current && !saving.current)
        setDraft(historyOnly ? null : data.draft);
      setPlanId((current) =>
        data.plans.some((x) => x.pathway_id === current)
          ? current
          : initialPlanId || data.plans[0]?.pathway_id || "",
      );
      if (!planId || planId === data.plans[0]?.pathway_id)
        setFollow(data.followup);
      else if (data.plans.some((x) => x.pathway_id === planId))
        setFollow(
          await request<Followup>(`/care/pathways/${planId}?day=${day}`),
        );
    } catch (err) {
      setError((err as Error).message);
    }
  }
  useEffect(() => {
    setBundle(null);
    setDraft(null);
    setDirty(false);
    dirtyRef.current = false;
    setPlanId("");
    setFollow(null);
    setError("");
    setEditingItems(new Set());
    load();
  }, [patient.patient_id]);
  useEffect(() => {
    const unsubscribe = subscribeCare(patient.patient_id, load);
    const timer = setInterval(
      () => {
        const next = dayNow(),
          previous = lastDay.current;
        if (next !== previous) {
          setDay((current) => (current === previous ? next : current));
          lastDay.current = next;
        }
        load();
      },
      language === "en" ? 5000 : 1500,
    );
    return () => {
      clearInterval(timer);
      unsubscribe();
    };
  }, [patient.patient_id, day, planId, language]);
  useEffect(() => {
    if (!planId) return;
    let active = true;
    request<Followup>(`/care/pathways/${planId}?day=${day}`)
      .then((x) => {
        if (active) setFollow(x);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [planId, day]);
  function edit(next: Draft) {
    editVersion.current++;
    dirtyRef.current = true;
    setDirty(true);
    setDraft(next);
    setStatus("Unsaved changes");
  }
  async function save() {
    const value = draftRef.current;
    if (!dirtyRef.current) return true;
    if (!value || !bundle?.visit) return false;
    if (saving.current) return false;
    saving.current = true;
    setBusy(true);
    setError("");
    const version = editVersion.current;
    lastAttempt.current = version;
    try {
      const result = await request<Draft>(
        `/care/visits/${bundle.visit.visit_id}/draft`,
        { method: "PUT", body: JSON.stringify(value) },
      );
      if (activePatient.current !== patient.patient_id) return false;
      if (version === editVersion.current) {
        setDraft({ ...result, checks: draftRef.current?.checks });
        dirtyRef.current = false;
        setDirty(false);
      } else
        setDraft((current) =>
          current ? { ...current, revision: result.revision } : current,
        );
      draftRef.current =
        version === editVersion.current
          ? result
          : draftRef.current
            ? { ...draftRef.current, revision: result.revision }
            : null;
      setStatus("Saved · translations updating");
      notifyCareChanged(patient.patient_id);
      return version === editVersion.current;
    } catch (err) {
      setError((err as Error).message);
      return false;
    } finally {
      saving.current = false;
      setBusy(false);
    }
  }
  saveRef.current = save;
  useEffect(() => {
    if (role !== "doctor" || historyOnly) return;
    const key = id();
    draftEditors.set(key, () => saveRef.current());
    return () => {
      draftEditors.delete(key);
    };
  }, [patient.patient_id, role, historyOnly]);
  useEffect(() => {
    if (!dirty || busy) return;
    if (lastAttempt.current === editVersion.current) return;
    if (
      draft?.medications.some(
        (m) =>
          !m.name.trim() ||
          !m.dose.trim() ||
          !m.times.length ||
          !m.start_date ||
          m.duration < 1,
      )
    )
      return;
    const timer = setTimeout(() => {
      save();
    }, 1300);
    return () => clearTimeout(timer);
  }, [draft, dirty, busy]);
  function changeItem(index: number, changes: Partial<Item>) {
    if (!draft) return;
    edit({
      ...draft,
      items: draft.items.map((x, i) =>
        i === index ? { ...x, ...changes } : x,
      ),
    });
  }
  async function checkDraftItem(itemId: string, completed: boolean) {
    if (!bundle?.visit) return;
    const before = draft?.checks;
    setDraft((current) =>
      current
        ? { ...current, checks: { ...current.checks, [itemId]: completed } }
        : current,
    );
    try {
      await request(
        `/care/visits/${bundle.visit.visit_id}/checks/${encodeURIComponent(itemId)}`,
        {
          method: "PUT",
          body: JSON.stringify({ completed }),
        },
      );
      setDraft((current) =>
        current
          ? { ...current, checks: { ...current.checks, [itemId]: completed } }
          : current,
      );
      notifyCareChanged(patient.patient_id);
    } catch (e) {
      setDraft((current) =>
        current ? { ...current, checks: before } : current,
      );
      setError((e as Error).message);
    }
  }
  async function finalize(download = false) {
    if (!bundle?.visit || !(await save())) return;
    if (
      !confirm(
        label(
          "Sign off these instructions and end the visit? This preserves a permanent record.",
        ),
      )
    )
      return;
    setBusy(true);
    setError("");
    try {
      const plan = await post<Plan>(`/visits/${bundle.visit.visit_id}/end`, {
        confirm: true,
        confirm_evidence_only: true,
        draft_revision: draftRef.current?.revision,
      });
      dirtyRef.current = false;
      setDirty(false);
      setDraft(null);
      setStatus("Signed and saved in patient records");
      await load();
      onEnded?.();
      if (download) await downloadPdf(plan.pathway_id);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function downloadPdf(pathwayId: string) {
    const response = await fetch(
      `/api/care/pathways/${pathwayId}/pdf?language=${language}`,
      { credentials: "same-origin" },
    );
    if (!response.ok) {
      const body = await response.json();
      throw Error(body.detail || "Download failed");
    }
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = url;
    link.download = `PrepPulse-${pathwayId}-${language}.pdf`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
  }
  async function tick(task: Task, completed: boolean) {
    const before = follow;
    setReporting(true);
    setFollow((current) =>
      current
        ? {
            ...current,
            tasks: current.tasks.map((x) =>
              x.task_id === task.task_id
                ? {
                    ...x,
                    report: {
                      completed,
                      reported_name: "Saving…",
                      reported_at: new Date().toISOString(),
                    },
                  }
                : x,
            ),
          }
        : current,
    );
    try {
      setError("");
      await request(`/care/pathways/${planId}/report`, {
        method: "PUT",
        body: JSON.stringify({ task_id: task.task_id, day, completed }),
      });
      setFollow(await request<Followup>(`/care/pathways/${planId}?day=${day}`));
    } catch (err) {
      setFollow(before);
      setError((err as Error).message);
    } finally {
      setReporting(false);
    }
  }
  const plan = bundle?.plans.find((x) => x.pathway_id === planId);
  const draftReady = careSnapshotReady(draft, language);
  const planReady = careSnapshotReady(plan, language);
  useCareTranslation(
    patient.patient_id,
    "draft",
    draft ? bundle?.visit?.visit_id : undefined,
    draft?.revision || 0,
    language,
  );
  useCareTranslation(
    patient.patient_id,
    "signed",
    plan?.pathway_id,
    plan?.revision || 0,
    language,
  );
  const translation = (draft || plan)?.language_status?.[language];
  useCareTranslation(
    patient.patient_id,
    "preview",
    !draft && !plan && bundle?.suggestions?.length
      ? patient.patient_id
      : undefined,
    bundle?.suggestion_revision || 0,
    language,
  );
  const doseText = (med: Medication) =>
    !med.dose
      ? ""
      : med.dose_texts?.[language] ||
        (language === "en" && !/[\u0900-\u0C7F]/u.test(med.dose)
          ? med.dose
          : label("Translating…"));
  const translated = (item: Item) => careText(item, language);
  async function beginVisit() {
    setBusy(true);
    try {
      await onStart?.();
      await load();
    } finally {
      setBusy(false);
    }
  }
  return (
    <div
      lang={language}
      className={"care-workspace " + (compact ? "care-compact" : "")}
    >
      <div className="panel-heading">
        <div>
          <div className="eyebrow teal">
            {bundle?.visit?.admitted || plan?.mode === "caregiver"
              ? label("CAREGIVER HANDOFF")
              : label("FAMILY PATHWAY")}
          </div>
          <h3>{compact ? label("Visit checklist") : patient.name}</h3>
        </div>
        <select
          aria-label="Care pathway language"
          value={language}
          onChange={(e) => {
            setEditingItems(new Set());
            setLanguage(e.target.value);
          }}
        >
          {Object.entries(languages).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
      </div>
      {error && (
        <p className="care-error" role="alert">
          {error}
          <button
            className="text-button"
            onClick={() => {
              setError("");
              load();
            }}
          >
            {label("Reload")}
          </button>
        </p>
      )}
      {!bundle && !error && <p role="status">{label("Loading care plan…")}</p>}
      {translation && translation.status !== "complete" && (
        <p className="small-muted" role="status">
          {label(
            ["queued", "running"].includes(translation.status)
              ? "Translating…"
              : "Translation incomplete",
          )}{" "}
          {translation.completed}/{translation.total}
        </p>
      )}
      {draft && role === "doctor" && (
        <>
          <p className="small-muted">
            {label(
              "Draft · edits save automatically. Agent suggestions require your review before sign-off.",
            )}
          </p>
          {draft.items.map((item, i) => (
            <div className="care-edit-item" key={item.item_id}>
              {!editingItems.has(item.item_id) && (
                <div className="care-item-view">
                  <label className="check-row">
                    <input
                      type="checkbox"
                      aria-label={`Pathway checklist ${i + 1}`}
                      checked={!!draft.checks?.[item.item_id]}
                      onChange={(e) =>
                        checkDraftItem(item.item_id, e.target.checked)
                      }
                    />
                    <span>
                      {draftReady ? translated(item) : label("Translating…")}
                    </span>
                  </label>
                  <button
                    className="text-button"
                    disabled={!draftReady}
                    aria-label={`Edit checklist item ${i + 1}`}
                    onClick={() =>
                      setEditingItems(new Set([...editingItems, item.item_id]))
                    }
                  >
                    {label("Edit")}
                  </button>
                </div>
              )}
              {editingItems.has(item.item_id) && (
                <>
                  <input
                    aria-label={`Checklist item ${i + 1}`}
                    value={translated(item) || ""}
                    onChange={(e) =>
                      changeItem(i, {
                        text: e.target.value,
                        source_language: language,
                        texts: { [language]: e.target.value },
                        source: "doctor",
                      })
                    }
                  />
                  {!translated(item) && (
                    <small>
                      {label("Source text shown · translation pending")}
                    </small>
                  )}
                  <div className="care-row">
                    <select
                      aria-label={`Checklist frequency ${i + 1}`}
                      value={item.frequency}
                      onChange={(e) =>
                        changeItem(i, {
                          frequency: e.target.value as Item["frequency"],
                        })
                      }
                    >
                      <option value="once">{label("once")}</option>
                      <option value="daily">{label("daily")}</option>
                    </select>
                    <span className="small-muted">
                      {item.source === "agent"
                        ? label("Agent suggestion")
                        : label("Clinician edited")}
                    </span>
                    <button
                      className="text-button"
                      onClick={() =>
                        edit({
                          ...draft,
                          items: draft.items.filter((_, n) => n !== i),
                        })
                      }
                    >
                      {label("Remove")}
                    </button>
                    <button
                      className="text-button"
                      onClick={() =>
                        setEditingItems((current) => {
                          const next = new Set(current);
                          next.delete(item.item_id);
                          return next;
                        })
                      }
                    >
                      {label("Done editing")}
                    </button>
                  </div>
                </>
              )}
            </div>
          ))}
          <div className="inline-form">
            <input
              aria-label="Add checklist instruction"
              placeholder={label("Add a checklist instruction")}
              value={newItem}
              onChange={(e) => setNewItem(e.target.value)}
            />
            <button
              className="secondary"
              disabled={!newItem.trim()}
              onClick={() => {
                edit({
                  ...draft,
                  items: [
                    ...draft.items,
                    {
                      item_id: id(),
                      text: newItem.trim(),
                      source_language: language,
                      texts: { [language]: newItem.trim() },
                      frequency: "once",
                      source: "doctor",
                    },
                  ],
                });
                setNewItem("");
              }}
            >
              {label("Add")}
            </button>
          </div>
          <p className="small-muted" role="status">
            {label(
              busy
                ? "Saving…"
                : dirty
                  ? "Unsaved changes"
                  : status || "Saved draft",
            )}{" "}
            · {label("Translation")}:{" "}
            {label(
              translation?.status === "complete"
                ? "Complete"
                : translation?.status === "partial" ||
                    translation?.status === "unavailable"
                  ? "Translation incomplete"
                  : "Translating…",
            )}
          </p>
          <button
            className="text-button"
            disabled={busy || dirty}
            onClick={async () => {
              try {
                await requestCareLanguage(
                  patient.patient_id,
                  "draft",
                  bundle!.visit!.visit_id,
                  draft.revision,
                  language,
                  true,
                );
                setStatus("Translation queued");
                await load();
              } catch (e) {
                setError((e as Error).message);
              }
            }}
          >
            {label("Refresh translations")}
          </button>
          {!compact && (
            <>
              <button
                className="secondary"
                onClick={() => onAdmission?.(!bundle?.visit?.admitted)}
              >
                {bundle?.visit?.admitted
                  ? label("Switch to family pathway")
                  : label("Admit · caregiver pathway")}
              </button>
              <label>
                {label("notes")} ({languages[language]})
                <textarea
                  rows={5}
                  disabled={!draftReady}
                  placeholder={!draftReady ? label("Translating…") : ""}
                  value={
                    draftReady
                      ? draft.notes_texts?.[language] || draft.doctor_notes
                      : ""
                  }
                  onChange={(e) =>
                    edit({
                      ...draft,
                      doctor_notes: e.target.value,
                      notes_language: language,
                      notes_texts: { [language]: e.target.value },
                    })
                  }
                />
              </label>
              {draft.doctor_notes && !draft.notes_texts?.[language] && (
                <p className="small-muted">
                  {label("Source notes shown · translation pending")}
                </p>
              )}
              <h3>{label("prescriptions")}</h3>
              <p className="small-muted">
                {label(
                  "Enter the prescribed name and exact dose / application instructions. Choose the schedule below.",
                )}
              </p>
              {draft.medications.map((med, i) => {
                const change = (value: Partial<Medication>) =>
                  edit({
                    ...draft,
                    medications: draft.medications.map((x, n) =>
                      n === i ? { ...x, ...value } : x,
                    ),
                  });
                return (
                  <fieldset className="care-med" key={med.medication_id}>
                    <legend>
                      {label("Prescription")} {i + 1}
                    </legend>
                    <div className="form-grid">
                      <label>
                        {label("Name")}
                        <input
                          aria-label={`Medication name ${i + 1}`}
                          value={med.name}
                          onChange={(e) => change({ name: e.target.value })}
                        />
                      </label>
                      <label>
                        {label("Dose / application")}
                        <input
                          aria-label={`Medication dose ${i + 1}`}
                          title={med.dose}
                          disabled={!draftReady}
                          value={doseText(med)}
                          onChange={(e) =>
                            change({
                              dose: e.target.value,
                              dose_texts: { [language]: e.target.value },
                            })
                          }
                        />
                      </label>
                    </div>
                    <div className="form-grid">
                      <label>
                        {label("Type")}
                        <select
                          value={med.kind}
                          onChange={(e) => change({ kind: e.target.value })}
                        >
                          <option value="medicine">{label("Medicine")}</option>
                          <option value="injection">
                            {label("Injection")}
                          </option>
                          <option value="treatment">
                            {label("Treatment / pack")}
                          </option>
                        </select>
                      </label>
                      <label>
                        {label("Start date")}
                        <input
                          type="date"
                          value={med.start_date}
                          onChange={(e) =>
                            change({ start_date: e.target.value })
                          }
                        />
                      </label>
                      <label>
                        {label("Duration")}
                        <input
                          type="number"
                          min="1"
                          max={med.duration_unit === "months" ? 24 : 730}
                          value={med.duration}
                          onChange={(e) =>
                            change({ duration: Number(e.target.value) })
                          }
                        />
                      </label>
                      <label>
                        {label("Unit")}
                        <select
                          value={med.duration_unit}
                          onChange={(e) =>
                            change({ duration_unit: e.target.value })
                          }
                        >
                          <option value="days">{label("Days")}</option>
                          <option value="months">{label("Months")}</option>
                        </select>
                      </label>
                    </div>
                    <div
                      className="care-row"
                      role="group"
                      aria-label="Daily dose times"
                    >
                      {["morning", "afternoon", "evening", "bedtime"].map(
                        (slot) => (
                          <button
                            key={slot}
                            className={
                              med.times.includes(slot) ? "primary" : "secondary"
                            }
                            aria-pressed={med.times.includes(slot)}
                            onClick={() =>
                              change({
                                times: med.times.includes(slot)
                                  ? med.times.filter((x) => x !== slot)
                                  : [...med.times, slot],
                              })
                            }
                          >
                            {label(slot)}
                          </button>
                        ),
                      )}
                    </div>
                    <label>
                      {label("Food timing")}
                      <select
                        value={med.food}
                        onChange={(e) => change({ food: e.target.value })}
                      >
                        {[
                          "before food",
                          "after food",
                          "with food",
                          "not applicable",
                        ].map((x) => (
                          <option key={x} value={x}>
                            {label(x)}
                          </option>
                        ))}
                      </select>
                    </label>
                    <button
                      className="text-button"
                      onClick={() =>
                        edit({
                          ...draft,
                          medications: draft.medications.filter(
                            (_, n) => n !== i,
                          ),
                        })
                      }
                    >
                      {label("Remove prescription")}
                    </button>
                  </fieldset>
                );
              })}
              <button
                className="secondary"
                onClick={() =>
                  edit({
                    ...draft,
                    medications: [
                      ...draft.medications,
                      {
                        medication_id: id(),
                        name: "",
                        dose: "",
                        kind: "medicine",
                        start_date: dayNow(),
                        duration: 7,
                        duration_unit: "days",
                        times: ["morning"],
                        food: "not applicable",
                      },
                    ],
                  })
                }
              >
                {label("+ Add medication / treatment")}
              </button>
              <div className="form-actions">
                <button className="secondary" disabled={busy} onClick={save}>
                  {label("Save draft")}
                </button>
                <button
                  className="primary"
                  disabled={busy}
                  onClick={() => finalize()}
                >
                  {label("Sign off and end session")}
                </button>
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={() => finalize(true)}
                >
                  {label("Download and end session")}
                </button>
              </div>
            </>
          )}
        </>
      )}
      {!draft && role === "doctor" && !historyOnly && (
        <p>
          {bundle?.plans.length
            ? label(
                "Previous signed checklist and completion are preserved below.",
              )
            : label(
                "Start the first visit to edit and approve this patient's checklist.",
              )}{" "}
          {onStart && (
            <button className="secondary" disabled={busy} onClick={beginVisit}>
              {label("Start visit and edit checklist")}
            </button>
          )}
        </p>
      )}
      {!draft &&
        role === "doctor" &&
        !historyOnly &&
        !bundle?.plans.length &&
        !!bundle?.suggestions?.length && (
          <div className="care-suggestion-preview">
            <h4>
              {label(
                "Patient-specific suggestions · awaiting clinician review",
              )}
            </h4>
            {careSnapshotReady({ items: bundle.suggestions }, language) ? (
              bundle.suggestions.map((x, i) => (
                <p key={i}>{careText(x, language)}</p>
              ))
            ) : (
              <p role="status">{label("Translating…")}</p>
            )}
          </div>
        )}
      {!!bundle?.plans.length && (
        <div className="signed-plan">
          <h3>
            {draft
              ? label("Previous signed plan · caregiver follow-up")
              : label("Signed pathways")}
          </h3>
          <select
            aria-label="Signed care pathway"
            value={planId}
            onChange={(e) => setPlanId(e.target.value)}
          >
            {bundle.plans.map((x) => (
              <option key={x.pathway_id} value={x.pathway_id}>
                {x.approved_at.slice(0, 10)} · {label(x.mode)} ·{" "}
                {x.approved_name || "Clinician"}
              </option>
            ))}
          </select>
          {plan && (
            <>
              <p className="small-muted">
                {label("Signed")} {new Date(plan.approved_at).toLocaleString()}{" "}
                · {plan.approved_name}.{" "}
                {label("Completion below is caregiver-reported.")}
              </p>
              {!planReady && (
                <p role="status">
                  {label(
                    plan.language_status?.[language] &&
                      !["queued", "running"].includes(
                        plan.language_status[language].status,
                      )
                      ? "Translation incomplete"
                      : "Translating…",
                  )}
                </p>
              )}
              {!compact && planReady && (
                <>
                  <h4>{label("notes")}</h4>
                  <p className="care-notes">
                    {plan.notes_texts?.[language] ||
                      plan.doctor_notes ||
                      label("No additional notes")}
                  </p>
                  {plan.doctor_notes &&
                    !plan.notes_texts?.[language] &&
                    plan.notes_language !== language && (
                      <small>
                        {label("Source language · translation unavailable")}
                      </small>
                    )}
                  {!!plan.medications?.length && (
                    <div className="care-table">
                      <table>
                        <thead>
                          <tr>
                            <th>{label("Prescription / dose")}</th>
                            <th>{label("Schedule")}</th>
                            <th>{label("Duration")}</th>
                          </tr>
                        </thead>
                        <tbody>
                          {plan.medications.map((m) => (
                            <tr key={m.medication_id}>
                              <td>
                                {m.name}
                                <br />
                                <strong title={m.dose}>{doseText(m)}</strong>
                              </td>
                              <td>
                                {m.times.map(label).join(", ")} ·{" "}
                                {label(m.food)}
                              </td>
                              <td>
                                {m.start_date} · {m.duration}{" "}
                                {label(m.duration_unit)}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </>
              )}
              <label>
                {label("Follow-up date")}
                <input
                  type="date"
                  max={dayNow()}
                  value={day}
                  onChange={(e) => setDay(e.target.value)}
                />
              </label>
              {follow && planReady && (
                <>
                  <p className="care-due">
                    {follow.past_due_unreported}{" "}
                    {label("past-due tasks not reported complete")}
                  </p>
                  {follow.tasks.map((task) => (
                    <label className="check-row" key={task.task_id}>
                      <input
                        type="checkbox"
                        checked={task.report?.completed || false}
                        disabled={role !== "caregiver" || reporting}
                        onChange={(e) => tick(task, e.target.checked)}
                      />
                      <span>
                        {task.kind === "checklist"
                          ? careText(
                              plan.items.find((item) =>
                                task.task_id.startsWith(`${item.item_id}:`),
                              ) || { text: "" },
                              language,
                            )
                          : task.text}
                        {task.kind === "medication" && (
                          <strong>
                            {" "}
                            ·{" "}
                            {task.medication
                              ? doseText(
                                  plan.medications.find(
                                    (med) =>
                                      med.medication_id ===
                                      task.medication?.medication_id,
                                  ) || task.medication,
                                )
                              : ""}{" "}
                            · {label(task.slot || "")} ·{" "}
                            {label(task.medication?.food || "")}
                          </strong>
                        )}
                        {task.report && (
                          <small>
                            {task.report.completed
                              ? label("Reported complete")
                              : label("Marked incomplete")}{" "}
                            {label("by")} {task.report.reported_name} ·{" "}
                            {new Date(task.report.reported_at).toLocaleString()}
                          </small>
                        )}
                      </span>
                    </label>
                  ))}
                  {!follow.tasks.length && (
                    <p>{label("No tasks scheduled on this date.")}</p>
                  )}
                  {!!follow.reports.length && (
                    <details>
                      <summary>
                        {label("Reported completion history")} ·{" "}
                        {follow.reports.length}
                      </summary>
                      {follow.reports
                        .slice()
                        .sort((a, b) =>
                          b.reported_at.localeCompare(a.reported_at),
                        )
                        .slice(0, 200)
                        .map((row) => {
                          const item = plan.items.find((x) =>
                            row.task_id.startsWith(`${x.item_id}:`),
                          );
                          const med = plan.medications?.find((x) =>
                            row.task_id.startsWith(`${x.medication_id}:`),
                          );
                          return (
                            <label className="check-row" key={row.task_id}>
                              <input
                                type="checkbox"
                                checked={row.completed}
                                disabled
                                readOnly
                              />
                              <span>
                                {item
                                  ? careText(item, language)
                                  : med
                                    ? `${med.name} · ${doseText(med)} · ${label(row.task_id.split(":").at(-1) || "")}`
                                    : row.task_id}
                                <small>
                                  {row.day} · {row.reported_name} ·{" "}
                                  {new Date(row.reported_at).toLocaleString()}
                                </small>
                              </span>
                            </label>
                          );
                        })}
                      {follow.reports.length > 200 && (
                        <p>
                          {label(
                            "Latest 200 reports shown. Select a follow-up date above to inspect that day's tasks.",
                          )}
                        </p>
                      )}
                    </details>
                  )}
                  <h4>{label("Caregiver notes")}</h4>
                  {follow.notes.map((x) => (
                    <div className="care-note" key={x.note_id}>
                      <p>{x.text}</p>
                      <small>
                        {x.author_name} ·{" "}
                        {new Date(x.created_at).toLocaleString()}
                      </small>
                    </div>
                  ))}
                </>
              )}
              {role === "caregiver" && (
                <>
                  <textarea
                    aria-label="Caregiver note for doctor"
                    placeholder={label(
                      "Share an observation or question with the doctor",
                    )}
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                  />
                  <button
                    className="secondary"
                    disabled={!note.trim()}
                    onClick={async () => {
                      try {
                        await post(`/care/pathways/${planId}/notes`, {
                          text: note,
                        });
                        setNote("");
                        setFollow(
                          await request<Followup>(
                            `/care/pathways/${planId}?day=${day}`,
                          ),
                        );
                      } catch (e) {
                        setError((e as Error).message);
                      }
                    }}
                  >
                    {label("Send note")}
                  </button>
                </>
              )}
              <button
                className="text-button"
                onClick={async () => {
                  try {
                    await requestCareLanguage(
                      patient.patient_id,
                      "signed",
                      planId,
                      plan.revision || 0,
                      language,
                      true,
                    );
                    setStatus("Translation queued");
                  } catch (e) {
                    setError((e as Error).message);
                  }
                }}
              >
                {label("Refresh signed translations")}
              </button>
              <span role="status" className="small-muted">
                {label(status)}
              </span>
              <button
                className="secondary"
                disabled={!planReady}
                onClick={() =>
                  downloadPdf(planId).catch((e) => setError(e.message))
                }
              >
                {label("Download pathway")} · {languages[language]}
              </button>
            </>
          )}
        </div>
      )}
      {bundle && !bundle.plans.length && !draft && (
        <p>{label("No signed pathway has been shared yet.")}</p>
      )}
    </div>
  );
}
