import { useEffect, useState } from "react";

const events = new EventTarget();
const languages = new Map<string, string>();
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
