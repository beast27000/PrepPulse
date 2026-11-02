import "./conversation.css";
export const processName = (stage: string) =>
  ({
    classification_agent: "Classification agent",
    trajectory_agent: "Metabolic trajectory agent",
    care_gaps_agent: "Care gaps agent",
    mismatches_agent: "Record reconciliation agent",
    comorbidities_agent: "Clinical history agent",
    caregiver_prep_agent: "Handoff preparation agent",
    assistive_bubbles_agent: "Clinical prompts agent",
    brief_compiler: "Consultation brief compiler",
    history_synthesis_agent: "History synthesis agent",
    analysis: "RAG · indexing patient evidence",
    ocr: "OCR · processing records",
  })[stage] || stage.replaceAll("_", " ");
export default function ProcessBubble({
  label,
  detail,
  offset = false,
}: {
  label: string;
  detail?: string;
  offset?: boolean;
}) {
  return (
    <div
      className={"process-bubble " + (offset ? "offset" : "")}
      role="status"
      aria-live="polite"
    >
      <span className="process-orbit" />
      <span>
        <strong>{processName(label)}</strong>
        {detail && <small>{detail}</small>}
      </span>
      <span className="process-dots">
        <i />
        <i />
        <i />
      </span>
    </div>
  );
}
