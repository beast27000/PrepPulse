import { useEffect, useState } from "react";
import { post, request } from "./api";

const events = new EventTarget();
const languages = new Map<string, string>();
let labelRequest: Promise<Record<string, Record<string, string>>> | undefined;
export function useCareLabels(language: string, enabled = true) {
  const [labels, setLabels] = useState<Record<string, Record<string, string>>>(
    {},
  );
  useEffect(() => {
    if (!enabled) return;
    labelRequest ||= request("/care/labels");
    labelRequest.then(setLabels).catch(() => {
      labelRequest = undefined;
    });
  }, [enabled]);
  return (key: string) => labels[language]?.[key] || key;
}
const requested = new Map<string, Promise<unknown>>();
type CareSnapshot = {
  items: {
    text?: string;
    text_en?: string;
    texts?: Record<string, string>;
    source_language?: string;
  }[];
  doctor_notes?: string;
  notes_language?: string;
  notes_texts?: Record<string, string>;
  medications?: { dose: string; dose_texts?: Record<string, string> }[];
};
export function careText(
  item: CareSnapshot["items"][number],
  language: string,
) {
  return (
    item.texts?.[language] ||
    ((item.source_language || "en") === language
      ? item.text || item.text_en
      : undefined)
  );
}
export function careSnapshotReady(
  snapshot: CareSnapshot | null | undefined,
  language: string,
): boolean {
  if (!snapshot) return false;
  return (
    snapshot.items.every((item) => !!careText(item, language)) &&
    (!snapshot.doctor_notes ||
      !!snapshot.notes_texts?.[language] ||
      (snapshot.notes_language || "en") === language) &&
    (snapshot.medications || []).every(
      (med) =>
        !med.dose ||
        !!med.dose_texts?.[language] ||
        (language === "en" && !/[\u0900-\u0C7F]/u.test(med.dose)),
    )
  );
}
export function requestCareLanguage(
  patientId: string,
  kind: "draft" | "signed" | "preview",
  identity: string,
  revision: number,
  language: string,
  force = false,
) {
  const key = `${kind}:${identity}:${revision}:${language}`;
  if (force) requested.delete(key);
  if (!requested.has(key)) {
    const url =
      kind === "preview"
        ? `/care/patients/${identity}/translate-preview`
        : kind === "draft"
          ? `/care/visits/${identity}/translate`
          : `/care/pathways/${identity}/translate`;
    const promise = post(`${url}?language=${language}`, {})
      .then(() => notifyCareChanged(patientId))
      .catch((error) => {
        requested.delete(key);
        throw error;
      });
    requested.set(key, promise);
  }
  return requested.get(key)!;
}
export function useCareTranslation(
  patientId: string,
  kind: "draft" | "signed" | "preview",
  identity: string | undefined,
  revision: number,
  language: string,
) {
  useEffect(() => {
    if (identity)
      requestCareLanguage(patientId, kind, identity, revision, language).catch(
        () => {},
      );
  }, [patientId, kind, identity, revision, language]);
}
export function notifyCareChanged(patientId: string) {
  events.dispatchEvent(new CustomEvent("care", { detail: patientId }));
}
export function subscribeCare(patientId: string, callback: () => void) {
  const listener = (event: Event) => {
    if ((event as CustomEvent<string>).detail === patientId) callback();
  };
  events.addEventListener("care", listener);
  return () => events.removeEventListener("care", listener);
}
export function useCareLanguage(
  patientId: string,
): [string, (language: string) => void] {
  const [language, update] = useState(languages.get(patientId) || "en");
  useEffect(() => {
    const refresh = () => update(languages.get(patientId) || "en");
    refresh();
    events.addEventListener("language", refresh);
    return () => events.removeEventListener("language", refresh);
  }, [patientId]);
  return [
    language,
    (value) => {
      languages.set(patientId, value);
      events.dispatchEvent(new Event("language"));
    },
  ];
}
