import { useEffect, useState } from "react";
import { ProcessingJob, post } from "./api";
import ProcessBubble, { processName } from "./ProcessBubble";

export default function IngestionStatus({ job, patientId, onRetry, admin = false }: {
  job?: ProcessingJob | null; patientId: string; admin?: boolean;
  onRetry: (job: ProcessingJob) => void;
}) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [, tick] = useState(0);
  const active = job && ["queued", "running"].includes(job.status);
  useEffect(() => { if (!active) return; const timer = setInterval(() => tick(x => x + 1), 1000); return () => clearInterval(timer); }, [active]);
  const elapsed = job?.created_at ? Math.max(0, Math.floor((Date.now() - Date.parse(job.created_at)) / 1000)) : 0;
  return <div className="ingestion-status">
    <strong>{job?.status === "queued" ? "Waiting for processing" : job?.status === "running" ? "Processing records" : job?.status === "complete" ? "Processing completed" : job?.status === "failed" ? "Processing failed" : "No analysis has been started"}</strong>
    {job && <p>{processName(job.stage || job.status)} · {job.documents_ready || 0}/{job.documents_total || 0} OCR ready{job.documents_failed ? ` · ${job.documents_failed} failed` : ""}
      {job.queue_position ? ` · queue position ${job.queue_position}` : ""}
      {active ? ` · ${Math.floor(elapsed / 60)}m ${elapsed % 60}s elapsed` : ""}</p>}
    {job?.current_file && active && <p>Current file: {job.current_file}</p>}
    {job?.updated_at && <small>Last progress: {new Date(job.updated_at).toLocaleTimeString()}</small>}
    {active && <div className="ingestion-animation"><ProcessBubble label={job.stage || "Waiting for processing"} detail="Work continues in the background" /></div>}
    {job?.error && <p className="care-error" role="alert">{job.error}</p>}
    {(!job || job.status === "failed") && <button type="button" className="secondary" disabled={busy} onClick={async () => {
      setBusy(true); setError("");
      try { onRetry(await post<ProcessingJob>(admin ? `/admin/patients/${patientId}/processing/retry` : `/patients/${patientId}/brief/jobs`, {})); }
      catch (e) { setError((e as Error).message); } finally { setBusy(false); }
    }}>{busy ? "Queuing…" : "Retry processing"}</button>}
    {error && <p role="alert">{error}</p>}
  </div>;
}
