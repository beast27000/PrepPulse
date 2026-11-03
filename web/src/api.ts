export type User = {
  user_id: string;
  account_id?: string;
  caregiver_type?: "family" | "professional";
  availability?: "free" | "active";
  name: string;
  role: "doctor" | "admin" | "caregiver";
  disabled?: boolean;
  csrf: string;
  username: string;
};
export type Patient = {
  patient_id: string;
  name: string;
  dob?: string;
  age?: number;
  sex?: string;
  external_aliases: string[];
};
export type Appointment = {
  visit_id?: string;
  appointment_id: string;
  patient_id: string;
  patient_name: string;
  date: string;
  time: string;
  doctor_id: string;
  sex?: string;
  age?: number;
  external_aliases?: string[];
  status: string;
  reason: string;
};
export type Doc = {
  display_name?: string;
  visit_id?: string;
  created_at?: string;
  record_id: string;
  filename: string;
  document_type: string;
  visit_date?: string;
  status: string;
  error?: string;
  page_count?: number;
};
export type ProcessingJob = {
  job_id: string;
  status: string;
  stage?: string;
  documents_total?: number;
  documents_ready?: number;
  documents_failed?: number;
  evidence_chunks?: number;
  verified_findings?: number;
  error?: string;
};
export type FolderImportResult = {
  patient_id: string;
  patient_name: string;
  external_id: string;
  folder_alias: string;
  patient_created: boolean;
  files_selected: number;
  files_saved: number;
  files_unchanged: number;
  documents_queued: number;
  job?: ProcessingJob;
};
export type AdminPatientOverview = {
  patient: Patient;
  doctors: { user_id: string; name: string }[];
  documents: Doc[];
  visits: Visit[];
  appointments: Appointment[];
  stored_files: number;
  latest_job: ProcessingJob | null;
};
export type Citation = {
  document_id: string;
  document_title?: string;
  page_number: number;
  bbox: number[];
  snippet?: string;
  extracted_text?: string;
  source_verified?: boolean;
};
export type Finding = {
  finding_id: string;
  title: string;
  subtitle: string;
  date: string;
  severity: string;
  status: string;
  citation?: Citation | null;
  related_citations?: Citation[];
};
export type Brief = {
  gender?: string;
  patient_id: string;
  patient_name: string;
  age_sex: string;
  classification: { stage: string; category: string; diagnostic_basis: string };
  visit_focus: string;
  trajectory: {
    kpis: {
      name: string;
      value: string;
      unit: string;
      date_str: string;
      trend_direction: string;
      citation?: Citation | null;
    }[];
    summary: string;
  };
  care_gaps: {
    items: {
      title: string;
      details: string;
      severity: string;
      citation?: Citation | null;
    }[];
  };
  mismatches: {
    items: {
      title: string;
      description: string;
      citations?: Citation[];
      source_a_citation?: Citation | null;
      source_b_citation?: Citation | null;
    }[];
  };
  caregiver_prep: {
    mode: string;
    checklist: {
      id: string;
      completed: boolean;
      [key: string]: string | boolean;
    }[];
    available_languages: string[];
  };
  priority_findings: Finding[];
  metric_series: {
    metric_name: string;
    points: {
      date: string;
      value: number;
      unit: string;
      citation?: Citation | null;
    }[];
  }[];
  assistive_bubbles: {
    bubble_id: string;
    prompt_text: string;
    action_type: string;
  }[];
  raw_evidence_count: number;
  freshness_score: number;
  record_summaries?: RecordSummary[];
  diabetes_history?: {
    summary: string;
    start_date?: string;
    end_date?: string;
    records: RecordSummary[];
  };
};
export type RecordSummary = {
  record_id: string;
  date: string;
  title: string;
  category: string;
  summary: string;
  citation?: Citation;
  evidence: { text: string; citation: Citation }[];
};
export type ChatSession = {
  session_id: string;
  title: string;
  patient_id: string;
  updated_at: string;
  active_turn_id?: string | null;
};
export type ChartArtifact = {
  artifact_id: string;
  title: string;
  kind: "line" | "journey" | "table";
  created_at: string;
  note: string;
  series: {
    metric_name: string;
    points: {
      date: string;
      value: number;
      unit: string;
      citation: Citation;
      citation_index?: number;
    }[];
  }[];
  events: {
    date: string;
    title: string;
    text: string;
    citation: Citation;
    citation_index?: number;
  }[];
};
export type SavedChatMessage = {
  message_id: string;
  role: "user" | "assistant";
  text: string;
  citations?: Citation[];
  artifact_ids?: string[];
  created_at: string;
  presentation?: {
    show_chart: boolean;
    show_source: boolean;
    source_index?: number;
  };
};
export type ChatTurn = {
  turn_id: string;
  status: string;
  stage: string;
  query: string;
  error?: string;
  steps?: { label: string; at: string }[];
};
export type ChatBundle = {
  session: ChatSession;
  messages: SavedChatMessage[];
  artifacts: ChartArtifact[];
  active_turn: ChatTurn | null;
};
export type Visit = {
  visit_id: string;
  status: string;
  admitted: boolean;
  doctor_notes: string;
  started_at: string;
  doctor_id: string;
};

let csrf = "";
export function setCsrf(value: string) {
  csrf = value;
}

export async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.method && init.method !== "GET") headers.set("X-CSRF-Token", csrf);
  if (init.body && !(init.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  const res = await fetch("/api" + path, {
    ...init,
    headers,
    credentials: "same-origin",
  });
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    if (res.status === 404 && data?.detail === "Not Found" && /^(\/care\/|\/appointment-history|\/previous-patients|\/admin\/caregiver)/.test(path)) {
      throw new Error("This API process does not contain the current UI routes. Restart it with scripts/start_ui_api.ps1, refresh, and sign in again.");
    }
    const detail = Array.isArray(data?.detail)
      ? data.detail
          .map(
            (x: { loc?: string[]; msg: string }) =>
              `${x.loc?.slice(1).join(" / ") || "Input"}: ${x.msg}`,
          )
          .join("; ")
      : data?.detail;
    throw new Error(detail || `${res.status}: ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export function post<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: "POST", body: JSON.stringify(body) });
}
export async function postAudio(path: string, body: unknown): Promise<Blob> {
  const res = await fetch("/api" + path, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
    credentials: "same-origin",
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new Error(data?.detail || `${res.status}: ${res.statusText}`);
  }
  if (!res.headers.get("Content-Type")?.includes("audio/wav"))
    throw new Error("Speech server returned no audio");
  return res.blob();
}
export function patch<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: "PATCH", body: JSON.stringify(body) });
}
