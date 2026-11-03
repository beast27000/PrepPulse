import { useEffect, useState } from "react";
import { post, request } from "./api";

const events = new EventTarget();
const languages = new Map<string, string>();
let labelRequest: Promise<Record<string, Record<string, string>>> | undefined;
export function useCareLabels(language: string) {
  const [labels, setLabels] = useState<Record<string, Record<string, string>>>(
    {},
  );
  useEffect(() => {
    labelRequest ||= request("/care/labels");
    labelRequest.then(setLabels).catch(() => {
      labelRequest = undefined;
    });
  }, []);
  return (key: string) => labels[language]?.[key] || key;
}
const requested = new Map<string, Promise<unknown>>();
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
