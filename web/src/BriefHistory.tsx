import { useState } from "react";
import { ArrowUpRight, FileText } from "lucide-react";
import { Brief, Citation, RecordSummary } from "./api";
import "./history.css";

export default function BriefHistory({
  brief,
  onCitation,
}: {
  brief: Brief;
  onCitation: (citation: Citation) => void;
}) {
  const [tab, setTab] = useState("diabetes_history");
  const records = brief.record_summaries || [];
  if (!records.length) return null;
  const visible =
    tab === "all"
      ? records
      : records.filter((record) => record.category === tab);
  const hba1c = brief.metric_series.find(
    (series) => series.metric_name === "HbA1c",
  );
  const other = records.filter((record) => record.category === "other_history");
  const first = hba1c?.points[0],
    last = hba1c?.points.at(-1);
  function card(record: RecordSummary) {
    return (
      <button
        className="history-record"
        key={record.record_id}
        onClick={() => record.citation && onCitation(record.citation)}
      >
        <div className="history-record-top">
          <time>{record.date}</time>
          <FileText size={15} />
        </div>
        <strong>{record.title}</strong>
        <p>{record.summary}</p>
        <span>
          Inspect source record <ArrowUpRight size={13} />
        </span>
      </button>
    );
  }
  return (
    <section className="brief-history">
      <div className="diabetes-history-lead">
        <div>
          <div className="eyebrow teal">DIABETES JOURNEY</div>
          <h2>
            {brief.diabetes_history?.start_date?.slice(0, 4)}–
            {brief.diabetes_history?.end_date?.slice(0, 4)} · documented history
          </h2>
          <p>{brief.diabetes_history?.summary || brief.trajectory.summary}</p>
        </div>
        {first && last && (
          <button
            className="history-glycemic"
            onClick={() => last.citation && onCitation(last.citation)}
          >
            <small>HbA1c · first → latest documented</small>
            <strong>
              {first.value}% <span>→</span> {last.value}%
            </strong>
            <span>
              {first.date} → {last.date}
            </span>
          </button>
        )}
      </div>
      {other.length > 0 && (
        <div className="key-history">
          <div className="eyebrow teal">OTHER DOCUMENTED HISTORY</div>
          <div>
            {other.map((record) => (
              <button
                key={record.record_id}
                onClick={() => record.citation && onCitation(record.citation)}
              >
                <time>{record.date}</time>
                <strong>{record.title}</strong>
                <span>{record.summary}</span>
                <small>Source record ↗</small>
              </button>
            ))}
          </div>
        </div>
      )}
      <div
        className="history-tabs"
        role="group"
        aria-label="Clinical history category"
      >
        <button
          className={tab === "diabetes_history" ? "active" : ""}
          onClick={() => setTab("diabetes_history")}
        >
          Diabetes history{" "}
          <span>
            {records.filter((r) => r.category === "diabetes_history").length}
          </span>
        </button>
        <button
          className={tab === "other_history" ? "active" : ""}
          onClick={() => setTab("other_history")}
        >
          Admissions & other history{" "}
          <span>
            {records.filter((r) => r.category === "other_history").length}
          </span>
        </button>
        <button
          className={tab === "all" ? "active" : ""}
          onClick={() => setTab("all")}
        >
          All source visits
        </button>
      </div>
      <div className="history-records">{visible.map(card)}</div>
    </section>
  );
}
