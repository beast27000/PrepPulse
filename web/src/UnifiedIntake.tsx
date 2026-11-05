import { useEffect, useRef, useState } from "react";
import { FolderImportResult, Patient, User, post, request } from "./api";

export default function UnifiedIntake({
  patients,
  accounts,
  reload,
}: {
  patients: Patient[];
  accounts: User[];
  reload: () => void;
}) {
  const doctors = accounts.filter((x) => x.role === "doctor" && !x.disabled);
  const [target, setTarget] = useState("");
  const [name, setName] = useState("");
  const [dob, setDob] = useState("");
  const [age, setAge] = useState("");
  const [sex, setSex] = useState("");
  const [doctor, setDoctor] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [mode, setMode] = useState<"record" | "folder">("record");
  const [documentType, setDocumentType] = useState("consult");
  const [visitDate, setVisitDate] = useState(
    new Date().toLocaleDateString("en-CA"),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<FolderImportResult | null>(null);
  const [created, setCreated] = useState<Patient | null>(null);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (mode === "folder") input.current?.setAttribute("webkitdirectory", "");
    else input.current?.removeAttribute("webkitdirectory");
    setFiles([]);
  }, [mode]);
  useEffect(() => {
    if (!result?.job || !["running", "queued"].includes(result.job.status))
      return;
    const timer = setInterval(async () => {
      try {
        const row = await request<{ latest_job: FolderImportResult["job"] }>(
          `/admin/patients/${result.patient_id}/overview`,
        );
        setResult((current) =>
          current ? { ...current, job: row.latest_job } : current,
        );
      } catch (e) {
        setError((e as Error).message);
      }
    }, 3000);
    return () => clearInterval(timer);
  }, [result?.patient_id, result?.job?.status]);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const doctorId = doctor || doctors[0]?.user_id;
      if (target)
        await request(`/patients/${target}/demographics`, {
          method: "PATCH",
          body: JSON.stringify({
            name,
            dob: dob || null,
            age: age && !dob ? Number(age) : null,
            sex: sex || null,
            doctor_id: doctorId,
          }),
        });
      if (mode === "folder" && files.length) {
        const form = new FormData();
        form.append("doctor_id", doctorId);
        if (target || created)
          form.append("patient_id", target || created!.patient_id);
        for (const [k, v] of Object.entries({
          name,
          dob,
          age: dob ? "" : age,
          sex,
        }))
          if (v) form.append(k, v);
        files.forEach((f) => {
          form.append("files", f, f.name);
          form.append("paths", f.webkitRelativePath);
        });
        const imported = await request<FolderImportResult>(
          "/admin/import-folder",
          { method: "POST", body: form },
        );
        setResult(imported);
        setTarget(imported.patient_id);
        setCreated(null);
      } else {
        const patient = target
          ? patients.find((x) => x.patient_id === target)!
          : created ||
            (await post<Patient>("/patients", {
              name,
              dob: dob || null,
              age: age && !dob ? Number(age) : null,
              sex: sex || null,
              doctor_id: doctorId,
            }));
        setCreated(patient);
        if (files[0]) {
          const form = new FormData();
          form.append("file", files[0]);
          form.append("document_type", documentType);
          form.append("visit_date", visitDate);
          await request(`/patients/${patient.patient_id}/documents`, {
            method: "POST",
            body: form,
          });
        }
        setTarget(patient.patient_id);
      }
      setFiles([]);
      if (input.current) input.current.value = "";
      reload();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel admin-form">
      <div className="eyebrow teal">PATIENT INTAKE</div>
      <h3>Patient details and records</h3>
      <p>
        Register once, then append records across visits using the same
        PrepPulse ID. Folder IDs are stored as searchable aliases.
      </p>
      <label>
        Patient
        <select
          aria-label="Intake patient"
          value={target}
          onChange={(e) => {
            setTarget(e.target.value);
            setCreated(null);
            setResult(null);
            const p = patients.find((x) => x.patient_id === e.target.value);
            setName(p?.name || "");
            setDob(p?.dob || "");
            setAge(p?.age?.toString() || "");
            setSex(p?.sex || "");
          }}
        >
          <option value="">New patient</option>
          {patients.map((p) => (
            <option key={p.patient_id} value={p.patient_id}>
              {p.name} · {p.patient_id}
            </option>
          ))}
        </select>
      </label>
      <form onSubmit={submit}>
        <label>
          Full name
          <input
            aria-label="Patient full name"
            required={!target}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <div className="form-grid">
          <label>
            Date of birth
            <input
              type="date"
              value={dob}
              onChange={(e) => setDob(e.target.value)}
            />
          </label>
          <label>
            Age, if date of birth unknown
            <input
              aria-label="Patient age"
              type="number"
              min="0"
              max="130"
              disabled={!!dob}
              value={age}
              onChange={(e) => setAge(e.target.value)}
            />
          </label>
          <label>
            Sex
            <select value={sex} onChange={(e) => setSex(e.target.value)}>
              <option value="">Not provided</option>
              <option>Female</option>
              <option>Male</option>
              <option>Other</option>
            </select>
          </label>
        </div>
        <label>
          Assign doctor
          <select
            value={doctor || doctors[0]?.user_id || ""}
            onChange={(e) => setDoctor(e.target.value)}
            required
          >
            <option value="">Select doctor</option>
            {doctors.map((d) => (
              <option key={d.user_id} value={d.user_id}>
                {d.name}
              </option>
            ))}
          </select>
        </label>
        <div className="form-actions">
          <button
            type="button"
            className={mode === "record" ? "primary" : "secondary"}
            onClick={() => setMode("record")}
          >
            Upload record
          </button>
          <button
            type="button"
            className={mode === "folder" ? "primary" : "secondary"}
            onClick={() => setMode("folder")}
          >
            Upload patient folder
          </button>
        </div>
        <label>
          {mode === "folder"
            ? "Patient folder (ID_Patient_Name)"
            : "Initial or later visit record"}
          <input
            key={mode}
            ref={input}
            aria-label="Intake files"
            type="file"
            multiple={mode === "folder"}
            accept={mode === "record" ? ".pdf,.png,.jpg,.jpeg" : undefined}
            onChange={(e) => {
              const selected = Array.from(e.target.files || []);
              setFiles(selected);
              if (!name && !target && mode === "folder")
                setName(
                  selected[0]?.webkitRelativePath
                    .split("/")[0]
                    .split("_")
                    .slice(1)
                    .join(" ") || "",
                );
            }}
          />
        </label>
        {mode === "record" && (
          <div className="form-grid">
            <label>
              Document type
              <select
                value={documentType}
                onChange={(e) => setDocumentType(e.target.value)}
              >
                <option value="consult">Consultation</option>
                <option value="lab">Lab report</option>
                <option value="rx">Prescription</option>
                <option value="discharge">Discharge summary</option>
              </select>
            </label>
            <label>
              Visit date
              <input
                type="date"
                value={visitDate}
                onChange={(e) => setVisitDate(e.target.value)}
              />
            </label>
          </div>
        )}
        {!!files.length && (
          <p role="status">
            {files.length} files selected ·{" "}
            {(files.reduce((a, f) => a + f.size, 0) / 1048576).toFixed(1)} MB
          </p>
        )}
        {error && (
          <p role="alert" className="care-error">
            {error}
          </p>
        )}
        <button
          className="primary"
          disabled={
            busy || !doctors.length || (mode === "folder" && !files.length)
          }
        >
          {busy
            ? "Saving patient and records…"
            : target || created
              ? "Save details and append records"
              : files.length
                ? "Register and upload"
                : "Register patient"}
        </button>
      </form>
      {result && (
        <div className="folder-result" role="status">
          <strong>
            {result.patient_name} · {result.patient_id}
          </strong>
          <p>
            {result.external_id} · {result.files_saved} files saved ·{" "}
            {result.files_unchanged} unchanged · {result.documents_queued}{" "}
            documents queued
          </p>
          <p>
            {result.job?.stage || result.job?.status} ·{" "}
            {result.job?.documents_ready || 0}/
            {result.job?.documents_total || result.documents_queued} processed
            {result.job?.documents_failed
              ? ` · ${result.job.documents_failed} failed`
              : ""}
          </p>
          {result.job?.error && (
            <p className="care-error">{result.job.error}</p>
          )}
        </div>
      )}
      {target && !result && (
        <p role="status">
          Saved patient: {name} · {target}. You can append another record or
          folder.
        </p>
      )}
    </section>
  );
}
