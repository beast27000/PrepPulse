import { useEffect, useState } from "react";
import { Patient, request } from "./api";
type Row = { item_id?: string; text?: string; text_en?: string };
type State = {
  draft: { items: Row[] } | null;
  plans: { items: Row[] }[];
  suggestions?: Row[];
  followup: { reports: { task_id: string; completed: boolean }[] } | null;
};
export default function CareSummary({
  patient,
  onOpen,
}: {
  patient: Patient;
  onOpen: () => void;
}) {
  const [data, setData] = useState<State | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const row = await request<State>(
          `/care/patients/${patient.patient_id}`,
        );
        if (active) {
          setData(row);
          setError("");
        }
      } catch (e) {
        if (active) setError((e as Error).message);
      }
    }
    load();
    const timer = setInterval(load, 5000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [patient.patient_id]);
  const rows = data?.draft?.items.length
    ? data.draft.items
    : data?.plans[0]?.items || data?.suggestions || [];
  return (
    <>
      <p className="small-muted">
        {data?.draft?.items.length
          ? "Current editable visit draft"
          : data?.plans.length
            ? "Previous signed checklist · completion retained"
            : "Patient-specific preparation · review before approval"}
      </p>
      {rows.slice(0, 3).map((row, i) => (
        <div className="check-preview" key={row.item_id || i}>
          <input
            aria-label={`Saved checklist preview ${i + 1}`}
            type="checkbox"
            disabled
            checked={
              !!row.item_id &&
              !!data?.plans.length &&
              !data?.draft?.items.length &&
              !!data?.followup?.reports.some(
                (r) => r.task_id.startsWith(row.item_id + ":") && r.completed,
              )
            }
          />
          <span>{row.text || row.text_en}</span>
        </div>
      ))}
      {!rows.length && !error && (
        <p className="small-muted">
          No patient-specific checklist has been returned. You can add clinician
          instructions in the editable checklist.
        </p>
      )}
      {error && <p role="alert">{error}</p>}
      <button className="text-button" onClick={onOpen}>
        Open editable checklist / pathway
      </button>
    </>
  );
}
