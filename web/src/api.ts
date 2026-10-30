export type User = {
  user_id: string;
  name: string;
  role: "doctor" | "admin";
  csrf: string;
  username: string;
};
export type Patient = {
  patient_id: string;
  name: string;
  dob?: string;
  sex?: string;
  external_aliases: string[];
};
export type Appointment = {
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
  record_id: string;
  filename: string;
  document_type: string;
  visit_date?: string;
  status: string;
  error?: string;
  page_count?: number;
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
};
export type Brief = {
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
    throw new Error(data?.detail || `${res.status}: ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export function post<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: "POST", body: JSON.stringify(body) });
}
export function patch<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: "PATCH", body: JSON.stringify(body) });
}
