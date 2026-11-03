import { useEffect, useRef, useState } from "react";
import { Patient, request } from "./api";
import { languages } from "./CareWorkspace";
import { notifyCareChanged, subscribeCare, useCareLanguage } from "./careView";
import "./care.css";

type Item = {
  item_id?: string;
  text?: string;
  text_en?: string;
  texts?: Record<string, string>;
  source_language?: string;
  source?: string;
  frequency?: string;
};
type Bundle = {
  draft: { items: Item[]; checks?: Record<string, boolean> } | null;
  visit: { visit_id: string } | null;
  plans: { pathway_id: string; items: Item[] }[];
  suggestions: Item[];
  followup: {
    tasks: { item_id?: string; report?: { completed: boolean } }[];
  } | null;
};

export default function CareChecklist({
  patient,
  onEdit,
  summary = false,
}: {
  patient: Patient;
  onEdit: () => void;
  summary?: boolean;
}) {
  const [data, setData] = useState<Bundle | null>(null);
  const [language, setLanguage] = useCareLanguage(patient.patient_id);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const checking = useRef(false);
  const loadVersion = useRef(0);
  useEffect(() => {
    let active = true;
    async function load() {
      if (checking.current) return;
      const version = ++loadVersion.current;
      try {
        const result = await request<Bundle>(
          `/care/patients/${patient.patient_id}`,
        );
        if (active && version === loadVersion.current) {
          setData(result);
          setError("");
        }
      } catch (e) {
        if (active) setError((e as Error).message);
      }
    }
    load();
    const unsubscribe = subscribeCare(patient.patient_id, load);
    const timer = setInterval(load, 5000);
    return () => {
      active = false;
      clearInterval(timer);
      unsubscribe();
    };
  }, [patient.patient_id]);
  const draft =
    !!data?.draft && (!!data.draft.items.length || !data.plans.length);
  const signed = !draft && !!data?.plans.length;
  const rows = (
    draft
      ? data!.draft!.items
      : signed
        ? data!.plans[0].items
        : data?.suggestions || []
  )
    .map((row, index) => ({ row, index }))
    .sort(
      (a, b) =>
        Number(b.row.source === "doctor") - Number(a.row.source === "doctor") ||
        a.index - b.index,
    )
    .map(({ row }) => row);
  async function check(item: Item, completed: boolean) {
    if (!data?.visit || !item.item_id || !draft) return;
    const before = data;
    checking.current = true;
    loadVersion.current++;
    setBusy(true);
    setData({
      ...data,
      draft: {
        ...data.draft!,
        checks: { ...data.draft?.checks, [item.item_id]: completed },
      },
    });
    try {
      await request(
        `/care/visits/${data.visit.visit_id}/checks/${encodeURIComponent(item.item_id)}`,
        {
          method: "PUT",
          body: JSON.stringify({ completed }),
        },
      );
      checking.current = false;
      notifyCareChanged(patient.patient_id);
    } catch (e) {
      setData(before);
      setError((e as Error).message);
    } finally {
      checking.current = false;
      setBusy(false);
    }
  }
  async function download() {
    if (!data?.plans[0]) return;
    try {
      const response = await fetch(
        `/api/care/pathways/${data.plans[0].pathway_id}/pdf?language=${language}`,
        { credentials: "same-origin" },
      );
      if (!response.ok)
        throw Error((await response.json()).detail || "Download unavailable");
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = `PrepPulse-${data.plans[0].pathway_id}-${language}.pdf`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 10000);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <div
      className={
        "care-workspace care-checklist " +
        (summary ? "care-card-preview" : "care-compact")
      }
    >
      {!summary && (
        <div className="panel-heading">
          <h3>Visit checklist</h3>
          <select
            aria-label="Care pathway language"
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
          >
            {Object.entries(languages).map(([key, value]) => (
              <option key={key} value={key}>
                {value}
              </option>
            ))}
          </select>
        </div>
      )}
      <p className="small-muted">
        {signed
          ? "Signed checklist · caregiver-reported completion"
          : draft
            ? "Visit preparation · checked by the clinician"
            : "Suggested preparation · review with the clinician"}
      </p>
      {rows.slice(0, summary ? 3 : rows.length).map((item, index) => {
        const translated =
          item.texts?.[language] ||
          (item.source_language === language ? item.text : undefined) ||
          (language === "en"
            ? item.text_en || item.text
            : ((item as Record<string, unknown>)[`text_${language}`] as
                string | undefined));
        const checked = signed
          ? data?.followup?.tasks.find((task) => task.item_id === item.item_id)
              ?.report?.completed
          : !!(item.item_id && data?.draft?.checks?.[item.item_id]);
        return (
          <label className="check-row" key={item.item_id || index}>
            <input
              type="checkbox"
              aria-label={`${summary ? "Card" : "Visit"} checklist ${index + 1}`}
              checked={!!checked}
              disabled={!draft || busy}
              onChange={(e) => check(item, e.target.checked)}
            />
            <span>
              {translated || item.text || item.text_en}
              {!translated && <small>Source text · translation pending</small>}
            </span>
          </label>
        );
      })}
      {!rows.length && (
        <p className="small-muted">
          No checklist instructions yet. Add them in Care pathways.
        </p>
      )}
      {error && (
        <p className="care-error" role="alert">
          {error}
        </p>
      )}
      <div className="care-checklist-actions">
        <button className="text-button" onClick={onEdit}>
          Edit pathway
        </button>
        {!summary && !!data?.plans.length && (
          <button className="secondary" onClick={download}>
            Download pathway · {languages[language]}
          </button>
        )}
      </div>
    </div>
  );
}
