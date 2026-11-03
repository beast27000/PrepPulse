import { lazy, Suspense, useEffect, useRef, useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  ChevronDown,
  ChevronUp,
  Maximize2,
  Mic,
  Plus,
  Send,
  Sparkles,
  Volume2,
  X,
} from "lucide-react";
import {
  ChatBundle,
  ChatSession,
  ChatTurn,
  ChartArtifact,
  Citation,
  Patient,
  post,
  postAudio,
  request,
  SavedChatMessage,
} from "./api";
import { Preferences } from "./preferences";
import ProcessBubble from "./ProcessBubble";
import "./conversation.css";
const ChartArtifactView = lazy(() => import("./ChartArtifactView"));

export function citationMarkdown(text: string) {
  return text
    .replace(/^```(?:markdown|md)?\s*\n([\s\S]*?)\n```\s*$/i, "$1")
    .replace(/\[(\d+(?:\s*,\s*\d+)*)\](?!\()/g, (_, numbers: string) =>
      numbers
        .split(",")
        .map((number) => `[${number.trim()}](#source-${number.trim()})`)
        .join(" "),
    );
}

export function RichReply({
  message,
  onCitation,
  onChart,
}: {
  message: SavedChatMessage;
  onCitation: (citation: Citation) => void;
  onChart: (id: string) => void;
}) {
  return (
    <div className="reply-markdown">
      <Markdown
        remarkPlugins={[remarkGfm]}
        skipHtml
        components={{
          a: ({ href, children }) => {
            if (href?.startsWith("#source-")) {
              const number = Number(href.slice(8));
              const citation = message.citations?.[number - 1];
              return (
                <button
                  className="inline-citation"
                  title={citation?.document_title || "Source unavailable"}
                  disabled={!citation}
                  onClick={() => citation && onCitation(citation)}
                >
                  [{number}]
                </button>
              );
            }
            if (href?.startsWith("#chart-"))
              return (
                <button
                  className="inline-chart-link"
                  onClick={() => onChart(href.slice(7))}
                >
                  {children} ↗
                </button>
              );
            return <span>{children}</span>;
          },
          table: ({ children }) => (
            <div className="reply-table">
              <table>{children}</table>
            </div>
          ),
        }}
      >
        {citationMarkdown(message.text)}
      </Markdown>
    </div>
  );
}

function SourceDock({
  patient,
  citation,
  onClose,
  onExpand,
}: {
  patient: Patient;
  citation: Citation;
  onClose: () => void;
  onExpand: () => void;
}) {
  const [failed, setFailed] = useState(false);
  const previewRef = useRef<HTMLDivElement | null>(null);
  const imageRef = useRef<HTMLImageElement | null>(null);
  useEffect(
    () => setFailed(false),
    [citation.document_id, citation.page_number],
  );
  const b = citation.bbox;
  const precise =
    citation.source_verified &&
    b?.length === 4 &&
    (b[2] - b[0]) * (b[3] - b[1]) <= 100000;
  function centerEvidence() {
    if (precise && previewRef.current && imageRef.current)
      previewRef.current.scrollTop = Math.max(
        0,
        ((b[1] + b[3]) / 2000) * imageRef.current.clientHeight -
          previewRef.current.clientHeight / 2,
      );
  }
  useEffect(centerEvidence, [
    citation.document_id,
    citation.page_number,
    b?.join(","),
  ]);
  return (
    <aside className="conversation-source panel">
      <header>
        <div>
          <span className="eyebrow teal">SOURCE PROOF</span>
          <h3>{citation.document_title || "Selected evidence"}</h3>
          <small>Page {citation.page_number}</small>
        </div>
        <button
          className="icon-button"
          aria-label="Close source proof"
          onClick={onClose}
        >
          <X size={17} />
        </button>
      </header>
      <button className="secondary source-open-full" onClick={onExpand}>
        <Maximize2 size={15} />
        Open full record workspace
      </button>
      {citation.document_id && !failed ? (
        <div className="source-dock-scroll" ref={previewRef}>
          <div className="source-dock-image">
            <img
              ref={imageRef}
              onLoad={centerEvidence}
              alt={`Source page ${citation.page_number}`}
              src={`/api/patients/${patient.patient_id}/documents/${citation.document_id}/page/${citation.page_number}`}
              onError={() => setFailed(true)}
            />
            {precise && (
              <span
                className="proof-highlight"
                style={{
                  left: `${b[0] / 10}%`,
                  top: `${b[1] / 10}%`,
                  width: `${(b[2] - b[0]) / 10}%`,
                  height: `${(b[3] - b[1]) / 10}%`,
                }}
              />
            )}
          </div>
        </div>
      ) : (
        <p>Original source page unavailable.</p>
      )}
      {!precise && (
        <p className="source-verification-note">
          An exact OCR span could not be verified for this excerpt. Inspect the
          original record.
        </p>
      )}
      <details className="source-excerpt">
        <summary>OCR excerpt</summary>
        <blockquote>{citation.snippet || citation.extracted_text}</blockquote>
      </details>
    </aside>
  );
}

export default function PatientConversation({
  patient,
  userId,
  preferences,
  full = false,
  onExpand,
  onOpenRecord,
}: {
  patient: Patient | null;
  userId: string;
  preferences: Preferences;
  full?: boolean;
  onExpand?: () => void;
  onOpenRecord?: (citation: Citation) => void;
}) {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [sessionId, setSessionId] = useState("");
  const [messages, setMessages] = useState<SavedChatMessage[]>([]);
  const [artifacts, setArtifacts] = useState<ChartArtifact[]>([]);
  const [turn, setTurn] = useState<ChatTurn | null>(null);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [activeArtifact, setActiveArtifact] = useState<string | null>(null);
  const [chartCollapsed, setChartCollapsed] = useState(false);
  const [chatCollapsed, setChatCollapsed] = useState(false);
  const [activeSource, setActiveSource] = useState<Citation | null>(null);
  const [recording, setRecording] = useState(false);
  const [voiceBusy, setVoiceBusy] = useState(false);
  const [ttsReady, setTtsReady] = useState(false);
  const [playing, setPlaying] = useState<string | null>(null);
  const [showSavedCharts, setShowSavedCharts] = useState(false);
  const sessionRef = useRef("");
  const messagesRef = useRef<HTMLDivElement | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const audio = useRef<HTMLAudioElement | null>(null);
  const busy = turn?.status === "queued" || turn?.status === "running";
  const storageKey = `preppulse.chat.${userId}.${patient?.patient_id}`;
  const artifact = artifacts.find(
    (item) => item.artifact_id === activeArtifact,
  );

  function focusChart(id: string) {
    if (!full && onExpand) {
      localStorage.setItem(
        `${storageKey}.focus`,
        JSON.stringify({ chart: id }),
      );
      onExpand();
      return;
    }
    setActiveArtifact(id);
    setChartCollapsed(false);
    setActiveSource(null);
  }
  function focusSource(citation: Citation) {
    if (!full && onExpand) {
      localStorage.setItem(
        `${storageKey}.focus`,
        JSON.stringify({ source: citation }),
      );
      onExpand();
      return;
    }
    setActiveSource(citation);
    setChartCollapsed(true);
    setChatCollapsed(false);
  }
  async function loadBundle(id: string, openResponse = false) {
    const bundle = await request<ChatBundle>(`/chat/sessions/${id}`);
    if (sessionRef.current !== id) return;
    setMessages(bundle.messages);
    setArtifacts(bundle.artifacts);
    setTurn(bundle.active_turn);
    setSessions((items) =>
      items.map((item) => (item.session_id === id ? bundle.session : item)),
    );
    if (openResponse) {
      const last = bundle.messages
        .filter((item) => item.role === "assistant")
        .at(-1);
      if (last?.presentation?.show_chart && last.artifact_ids?.length)
        focusChart(last.artifact_ids[0]);
      if (last?.presentation?.show_source) {
        const source =
          last.citations?.[(last.presentation.source_index || 1) - 1];
        if (source) focusSource(source);
      }
    }
  }
  async function chooseSession(id: string) {
    sessionRef.current = id;
    setSessionId(id);
    setError("");
    setActiveSource(null);
    setActiveArtifact(null);
    setChatCollapsed(false);
    setTurn(null);
    setMessages([]);
    setArtifacts([]);
    localStorage.setItem(storageKey, id);
    try {
      await loadBundle(id);
    } catch (err) {
      setError((err as Error).message);
    }
  }
  async function newSession() {
    if (!patient) return null;
    const next = await post<ChatSession>("/chat/sessions", {
      patient_id: patient.patient_id,
    });
    setSessions((items) => [next, ...items]);
    await chooseSession(next.session_id);
    return next.session_id;
  }
  useEffect(() => {
    let active = true;
    setLoading(true);
    setMessages([]);
    setArtifacts([]);
    setError("");
    setActiveSource(null);
    setActiveArtifact(null);
    setTurn(null);
    setSessionId("");
    sessionRef.current = "";
    if (!patient) {
      setLoading(false);
      return;
    }
    request<ChatSession[]>(`/chat/sessions?patient_id=${patient.patient_id}`)
      .then(async (items) => {
        if (!active || sessionRef.current) return;
        setSessions(items);
        const saved = localStorage.getItem(storageKey);
        const id =
          items.find((item) => item.session_id === saved)?.session_id ||
          items[0]?.session_id;
        if (id) await chooseSession(id);
        const focus = JSON.parse(
          localStorage.getItem(`${storageKey}.focus`) || "null",
        );
        if (full && focus) {
          if (focus.chart) {
            setActiveArtifact(focus.chart);
            setChartCollapsed(false);
          }
          if (focus.source) setActiveSource(focus.source);
          localStorage.removeItem(`${storageKey}.focus`);
        }
      })
      .catch((err) => active && setError((err as Error).message))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [patient?.patient_id, userId]);
  useEffect(() => {
    if (!busy || !turn || !sessionId) return;
    let active = true;
    const id = turn.turn_id;
    const timer = setInterval(async () => {
      try {
        const next = await request<ChatTurn>(`/chat/turns/${id}`);
        if (!active) return;
        setTurn(next);
        if (next.status === "complete") {
          await loadBundle(sessionId, true);
          const list = await request<ChatSession[]>(
            `/chat/sessions?patient_id=${patient!.patient_id}`,
          );
          if (active) setSessions(list);
        }
        if (next.status === "failed")
          setError(next.error || "Response failed. Retry your request.");
      } catch (err) {
        if (active) setError((err as Error).message);
      }
    }, 900);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [turn?.turn_id, busy, sessionId]);
  useEffect(() => {
    if (messagesRef.current)
      messagesRef.current.scrollTop = messagesRef.current.scrollHeight;
  }, [messages.length, busy]);
  useEffect(() => {
    request<{ tts_ready: boolean }>("/voice/capabilities")
      .then((result) => setTtsReady(result.tts_ready))
      .catch(() => {});
    return () => {
      audio.current?.pause();
      recorder.current?.stream.getTracks().forEach((track) => track.stop());
    };
  }, []);
  async function send(event?: React.FormEvent) {
    event?.preventDefault();
    const question = input.trim();
    if (!patient || !question || busy || voiceBusy || recording) return;
    setError("");
    setInput("");
    try {
      const id = sessionId || (await newSession());
      if (!id) return;
      const next = await post<ChatTurn>(`/chat/sessions/${id}/turns`, {
        query: question,
      });
      await loadBundle(id);
      setTurn(next);
    } catch (err) {
      setError((err as Error).message);
      setInput(question);
    }
  }
  async function dictate() {
    if (recording) {
      recorder.current?.stop();
      setRecording(false);
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const parts: Blob[] = [];
      const rec = new MediaRecorder(stream);
      recorder.current = rec;
      rec.ondataavailable = (event) => {
        if (event.data.size) parts.push(event.data);
      };
      rec.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop());
        setVoiceBusy(true);
        const form = new FormData();
        form.append(
          "file",
          new Blob(parts, { type: rec.mimeType }),
          "dictation.webm",
        );
        if (preferences.dictationLanguage !== "auto")
          form.append("language", preferences.dictationLanguage);
        try {
          const result = await request<{ transcript: string }>(
            "/voice/transcribe",
            { method: "POST", body: form },
          );
          setInput(result.transcript);
        } catch (err) {
          setError((err as Error).message);
        } finally {
          setVoiceBusy(false);
        }
      };
      rec.start();
      setRecording(true);
    } catch (err) {
      setError((err as Error).message);
    }
  }
  async function readAloud(message: SavedChatMessage) {
    if (!patient) return;
    if (playing === message.message_id) {
      audio.current?.pause();
      setPlaying(null);
      return;
    }
    try {
      audio.current?.pause();
      const blob = await postAudio("/voice/speak", {
        patient_id: patient.patient_id,
        text: message.text.replace(/[#*|\[\]]/g, "").slice(0, 1200),
      });
      const url = URL.createObjectURL(blob);
      const player = new Audio(url);
      audio.current = player;
      player.onended = () => {
        setPlaying(null);
        URL.revokeObjectURL(url);
      };
      await player.play();
      setPlaying(message.message_id);
    } catch (err) {
      setError((err as Error).message);
    }
  }
  return (
    <section
      className={`patient-conversation ${full ? "is-workspace" : "is-compact"}`}
    >
      <header className="conversation-toolbar">
        <div className="conversation-title">
          <Sparkles size={19} />
          <div>
            <strong>PrepPulse Assistant</strong>
            <small>{patient?.name || "Select a patient"}</small>
          </div>
        </div>
        <div className="conversation-tools">
          {full &&
            (activeSource ||
              (artifact && !chartCollapsed) ||
              chatCollapsed) && (
              <button
                className="secondary"
                onClick={() => setChatCollapsed(!chatCollapsed)}
              >
                {chatCollapsed ? "Show chat" : "Collapse chat"}
              </button>
            )}
          {full && artifact && chartCollapsed && (
            <button
              className="secondary"
              aria-label="Expand chart"
              onClick={() => focusChart(artifact.artifact_id)}
            >
              Show chart
            </button>
          )}
          {full && (
            <select
              aria-label="Chat session"
              value={sessionId}
              onChange={(event) => chooseSession(event.target.value)}
            >
              <option value="">New conversation</option>
              {sessions.map((item) => (
                <option key={item.session_id} value={item.session_id}>
                  {item.title}
                </option>
              ))}
            </select>
          )}
          <button
            className="icon-button"
            title="New chat session"
            aria-label="New chat session"
            disabled={!patient || loading}
            onClick={() => newSession().catch((err) => setError(err.message))}
          >
            <Plus size={17} />
          </button>
          {onExpand && !full && (
            <button
              className="icon-button"
              aria-label="Open full chat workspace"
              onClick={onExpand}
            >
              <Maximize2 size={17} />
            </button>
          )}
          {full && artifacts.length > 0 && (
            <button
              className="secondary"
              onClick={() => setShowSavedCharts(!showSavedCharts)}
            >
              Session charts · {artifacts.length}
            </button>
          )}
        </div>
      </header>
      {showSavedCharts && (
        <div className="session-artifacts">
          {artifacts.map((item) => (
            <button
              key={item.artifact_id}
              onClick={() => {
                focusChart(item.artifact_id);
                setShowSavedCharts(false);
              }}
            >
              {item.title}
              <small>
                {new Date(item.created_at).toLocaleTimeString([], {
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </small>
            </button>
          ))}
        </div>
      )}
      <div
        className={`conversation-body ${activeSource || (artifact && !chartCollapsed) ? "with-inspector" : ""} ${chatCollapsed ? "only-inspector" : ""}`}
      >
        {artifact && !chartCollapsed && (
          <section
            className={`conversation-chart panel ${chartCollapsed ? "collapsed" : ""}`}
          >
            <header>
              <div>
                <span className="eyebrow teal">SAVED SESSION CHART</span>
                <h2>{artifact.title}</h2>
              </div>
              <div>
                <button
                  className="icon-button"
                  aria-label={
                    chartCollapsed ? "Expand chart" : "Collapse chart"
                  }
                  onClick={() => {
                    setChartCollapsed(true);
                    setChatCollapsed(false);
                  }}
                >
                  {chartCollapsed ? (
                    <ChevronDown size={17} />
                  ) : (
                    <ChevronUp size={17} />
                  )}
                </button>
                <button
                  className="icon-button"
                  aria-label="Close chart"
                  onClick={() => {
                    setActiveArtifact(null);
                    setChatCollapsed(false);
                  }}
                >
                  <X size={17} />
                </button>
              </div>
            </header>
            {!chartCollapsed && (
              <div className="conversation-chart-scroll">
                <Suspense fallback={<p>Opening saved chart…</p>}>
                  <ChartArtifactView
                    artifact={artifact}
                    onCitation={focusSource}
                  />
                </Suspense>
              </div>
            )}
          </section>
        )}
        <div
          className="conversation-thread panel"
          style={chatCollapsed ? { display: "none" } : undefined}
        >
          <div
            className="conversation-messages"
            ref={messagesRef}
            aria-live="polite"
          >
            {loading ? (
              <p>Opening conversation…</p>
            ) : !messages.length ? (
              <div className="conversation-empty">
                <Sparkles size={27} />
                <h2>Explore this patient's record</h2>
                <p>
                  Ask a clinical question, create a chart, or compare earlier
                  visits.
                </p>
                <div>
                  {[
                    "Chart the diabetes journey over the past 10 years",
                    "Summarize admissions and procedures",
                    "Compare the latest and earliest HbA1c results",
                  ].map((question) => (
                    <button key={question} onClick={() => setInput(question)}>
                      {question}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              messages.map((message) => (
                <article
                  key={message.message_id}
                  className={`conversation-message ${message.role}`}
                >
                  {message.role === "user" ? (
                    <p>{message.text}</p>
                  ) : (
                    <>
                      <RichReply
                        message={message}
                        onCitation={focusSource}
                        onChart={focusChart}
                      />
                      {!!message.artifact_ids?.length && (
                        <div className="message-artifacts">
                          {message.artifact_ids.map((id) => (
                            <button key={id} onClick={() => focusChart(id)}>
                              <Sparkles size={14} />
                              {artifacts.find((item) => item.artifact_id === id)
                                ?.title || "Open generated chart"}{" "}
                              ↗
                            </button>
                          ))}
                        </div>
                      )}
                      {!!message.citations?.length && (
                        <details className="response-sources">
                          <summary>
                            {message.citations.length} linked source excerpts
                          </summary>
                          <div>
                            {message.citations.map((source, index) => (
                              <button
                                key={index}
                                onClick={() => focusSource(source)}
                              >
                                <span>[{index + 1}]</span>
                                {source.document_title} · p.{" "}
                                {source.page_number}
                                {!source.source_verified && (
                                  <small>Exact span unavailable</small>
                                )}
                              </button>
                            ))}
                          </div>
                        </details>
                      )}
                      {preferences.showReadAloud && (
                        <button
                          className="text-button"
                          disabled={!ttsReady}
                          title={
                            ttsReady
                              ? "Read this reply aloud"
                              : "A compatible local audio server is required"
                          }
                          onClick={() => readAloud(message)}
                        >
                          <Volume2 size={14} />
                          {playing === message.message_id
                            ? "Stop playback"
                            : "Read aloud"}
                        </button>
                      )}
                    </>
                  )}
                </article>
              ))
            )}
            {busy && (
              <div className="conversation-working">
                <span className="process-orbit" />
                {turn?.stage}
                <span className="process-dots">
                  <i />
                  <i />
                  <i />
                </span>
              </div>
            )}
          </div>
          {error && (
            <div className="conversation-error" role="alert">
              {error}
              {turn?.status === "failed" && (
                <button
                  onClick={() => {
                    setInput(turn.query);
                    setError("");
                  }}
                >
                  Restore request to retry
                </button>
              )}
            </div>
          )}
          {(recording || voiceBusy) && (
            <div className="dictation-status" role="status" aria-live="polite">
              <Mic size={14} />
              <span>
                {recording
                  ? "Listening · click the microphone to stop"
                  : "Transcribing · your text will appear for review"}
              </span>
              <span className="process-dots" aria-hidden="true">
                <i />
                <i />
                <i />
              </span>
            </div>
          )}
          <form className="conversation-composer" onSubmit={send}>
            <button
              type="button"
              className={`icon-button ${recording ? "recording" : ""}`}
              aria-label={recording ? "Stop dictation" : "Dictate request"}
              aria-pressed={recording}
              disabled={!patient || busy || voiceBusy}
              onClick={dictate}
            >
              <Mic size={18} />
            </button>
            <textarea
              aria-label="Message PrepPulse"
              placeholder={
                voiceBusy
                  ? "Transcribing for review…"
                  : recording
                    ? "Listening…"
                    : "Ask about the record, a chart, or an earlier visit…"
              }
              rows={2}
              value={input}
              disabled={!patient || busy || voiceBusy}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  send();
                }
              }}
            />
            <button
              className="send-button"
              aria-label="Send message"
              disabled={
                !input.trim() || !patient || busy || voiceBusy || recording
              }
            >
              <Send size={19} />
            </button>
          </form>
          <small className="conversation-input-note">
            Enter to send · Shift+Enter for a new line · Dictation is reviewed
            before sending
          </small>
        </div>
        {activeSource && patient && (
          <SourceDock
            patient={patient}
            citation={activeSource}
            onClose={() => {
              setActiveSource(null);
              setChatCollapsed(false);
            }}
            onExpand={() => onOpenRecord?.(activeSource)}
          />
        )}
      </div>
      {busy && (
        <ProcessBubble
          label={turn?.stage || "Preparing response"}
          detail={`${turn?.steps?.length || 0} processing steps · conversation saved`}
        />
      )}
    </section>
  );
}
