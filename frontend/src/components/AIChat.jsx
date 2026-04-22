import React, { useState, useRef, useEffect } from "react";
import useAuth from "../hooks/useAuth";
import useIntent from "../hooks/useIntent";
import mapIntents from "../../services/mapIntents";
import QuotaStatus from "./QuotaStatus";

// ── Blinking cursor keyframe injected once at module level ────────────────
const CURSOR_STYLE = `
@keyframes ai-blink {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0; }
}
.ai-cursor {
  display: inline-block;
  width: 2px;
  height: 0.9em;
  background: var(--accent-primary, #7c3aed);
  margin-left: 2px;
  border-radius: 1px;
  vertical-align: text-bottom;
  animation: ai-blink 0.9s step-end infinite;
}
`;

const AIChat = ({
  logout,
  fetchAdmin,
  fetchDocuments,
  loading,
  error,
  documents,
  isAdmin,
  onOpenAdmin,
}) => {
  const { token } = useAuth();
  
  const [isDarkMode, setIsDarkMode] = useState(() => !document.body.classList.contains("light-theme"));

  useEffect(() => {
    if (isDarkMode) {
      document.body.classList.remove("light-theme");
    } else {
      document.body.classList.add("light-theme");
    }
  }, [isDarkMode]);

  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content: "Hello! I am your AI assistant. How can I help you today?",
      timestamp: new Date().toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
      }),
    },
  ]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false); // true = waiting for first token
  const [showDocs, setShowDocs] = useState(false);
  const [quotaRefreshTrigger, setQuotaRefreshTrigger] = useState(0);
  const [pushedQuota, setPushedQuota] = useState(null);
  const messagesEndRef = useRef(null);
  const textareaRef = useRef(null);
  const abortControllerRef = useRef(null);

  // ── Intent definitions ────────────────────────────────────────────────────
  const { intents } = useIntent();
  const INTENTS = mapIntents(intents);
  // ── Sensitivity levels ───────────────────────────────────────────────────
  const SENSITIVITY_LEVELS = [
    { value: "LOW", label: "🟢 Low", color: "#4ade80" },
    { value: "MEDIUM", label: "🟡 Medium", color: "#facc15" },
    { value: "HIGH", label: "🔴 High", color: "#f87171" },
  ];

  const [selectedIntent, setSelectedIntent] = useState("");

  // Update selectedIntent when INTENTS are loaded
  useEffect(() => {
    if (INTENTS.length > 0 && !selectedIntent) {
      setSelectedIntent(INTENTS[0].value);
    }
  }, [INTENTS, selectedIntent, intents]);
  const [selectedSensitivity, setSelectedSensitivity] = useState("LOW");
  const [resolvedService, setResolvedService] = useState(null);

  // ── Auto-scroll ───────────────────────────────────────────────────────────
  const scrollToBottom = () =>
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading]);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  }, [input]);

  useEffect(() => {
    if (documents?.length > 0) setShowDocs(true);
  }, [documents]);

  // ── Send handler (SSE streaming via native fetch) ─────────────────────────
  const handleSend = async (e) => {
    if (e) e.preventDefault();
    if (!input.trim() || isLoading) return;

    const MAX_HISTORY = 6;
    // Sliding window — prevents context overflow and avoids
    // re-scanning old PII in backend content inspector

    const userMessage = {
      role: "user",
      content: input.trim(),
      timestamp: new Date().toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
      }),
    };

    const conversationHistory = [...messages, userMessage].slice(-MAX_HISTORY);

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsLoading(true);

    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const response = await fetch("/api/ai/request", {
        signal: controller.signal,
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
          "kong-header": "true",
          Accept: "text/event-stream",
        },
        body: JSON.stringify({
          intent: selectedIntent || "general_chat",
          payload: {
            messages: conversationHistory.map((m) => ({
              role: m.role,
              content: m.content,
            })),
          },
          metadata: {
            sensitivity: selectedSensitivity,
            environment: "dev",
          },
        }),
      });

      // ── Pre-stream error (auth failure, 422, 403) ─────────────────────
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        let errMsg = "Sorry, I'm having trouble connecting to the AI service.";

        let detectedPiiTypes = null;
        let piiCount = 0;

        if (response.status === 400) {
          errMsg = "Message blocked by AI Prompt Guard.";
        } else if (errData.detail) {
          if (typeof errData.detail === "object") {
            // Handle structured error from the backend (403 blocks)
            errMsg = errData.detail.message || JSON.stringify(errData.detail);
            detectedPiiTypes = errData.detail.detected_pii_types || null;
            piiCount = errData.detail.pii_count || 0;
            
            // Enhance the message if it's a policy/security block
            if (errData.detail.description) {
              errMsg = `Access Denied: ${errData.detail.description}`;
            }
          } else {
            errMsg = errData.detail;
          }
        }

        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: errMsg,
            timestamp: new Date().toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
            }),
            isError: true,
            detectedPiiTypes,
            piiCount,
          },
        ]);
        return;
      }

      // ── Stream reading ────────────────────────────────────────────────
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let placeholderAdded = false;

      const addPlaceholder = () => {
        if (placeholderAdded) return;
        placeholderAdded = true;
        setIsLoading(false); // hide typing dots
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: "",
            timestamp: new Date().toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
            }),
            isStreaming: true,
          },
        ]);
      };

      // eslint-disable-next-line no-constant-condition
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // SSE events are separated by \n\n
        const events = buffer.split("\n\n");
        buffer = events.pop(); // keep any incomplete trailing event

        for (const event of events) {
          const dataLine = event
            .split("\n")
            .find((l) => l.startsWith("data: "));
          if (!dataLine) continue;

          let data;
          try {
            data = JSON.parse(dataLine.slice(6));
          } catch {
            continue;
          }

          // ── Error event from server mid-stream ──────────────────────
          if (data.error) {
            addPlaceholder();
            setMessages((prev) => {
              const updated = [...prev];
              updated[updated.length - 1] = {
                ...updated[updated.length - 1],
                content: "Sorry, the stream was interrupted.",
                isStreaming: false,
                isError: true,
              };
              return updated;
            });
            return;
          }

          // ── First token: inject the placeholder bubble ───────────────
          if (!placeholderAdded && data.token !== undefined) {
            addPlaceholder();
          }

          // ── Append token to the last message ────────────────────────
          if (data.token && !data.done) {
            setMessages((prev) => {
              const updated = [...prev];
              updated[updated.length - 1] = {
                ...updated[updated.length - 1],
                content: updated[updated.length - 1].content + data.token,
              };
              return updated;
            });
          }

          // ── Final event: seal the message ────────────────────────────
          if (data.done) {
            setQuotaRefreshTrigger((prev) => prev + 1);
            if (data.quota) setPushedQuota(data.quota);
            if (data.resolved_service)
              setResolvedService(data.resolved_service);
            setMessages((prev) => {
              const updated = [...prev];
              updated[updated.length - 1] = {
                ...updated[updated.length - 1],
                isStreaming: false,
                requestId: data.request_id || null,
                resolvedService: data.resolved_service || null,
                resolvedSensitivity: data.resolved_sensitivity || null,
                detectedPiiTypes: Array.isArray(data.detected_pii_types)
                  ? data.detected_pii_types
                  : null,
                piiCount: data.pii_count || 0,
                // Streaming latency comes from X-Request-ID header only;
                // no per-message upstream latency available in SSE mode
                metrics: {
                  proxyLatency: response.headers.get("x-kong-proxy-latency"),
                  upstreamLatency: response.headers.get(
                    "x-kong-upstream-latency",
                  ),
                  debug: response.headers.get("x-ai-debug"),
                },
              };
              return updated;
            });
          }
        }
      }
    } catch (err) {
      if (err.name === "AbortError") {
        setMessages((prev) => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last?.role === "assistant" && last?.isStreaming) {
            updated[updated.length - 1] = {
              ...last,
              isStreaming: false,
              isCancelled: true,
            };
          } else {
            updated.push({
              role: "assistant",
              content: "",
              timestamp: new Date().toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
              }),
              isCancelled: true,
            });
          }
          return updated;
        });
      } else {
        console.error("AI Chat Error:", err);
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: "Sorry, I'm having trouble connecting to the AI service.",
            timestamp: new Date().toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
            }),
            isError: true,
          },
        ]);
      }
    } finally {
      abortControllerRef.current = null;
      setIsLoading(false);
    }
  };

  const handleCancel = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const isActive = isLoading || messages.some((m) => m.isStreaming);
  const selectedIntentLabel =
    INTENTS.find((i) => i.value === selectedIntent)?.label ?? selectedIntent;

  return (
    <div className="chat-window">
      {/* Inject blinking cursor styles once */}
      <style>{CURSOR_STYLE}</style>

      {/* ── Header ───────────────────────────────────────────────────────── */}
      <div className="chat-header">
        <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
          <div className="avatar ai">AI</div>
          <div>
            <h3
              style={{
                fontSize: "1rem",
                fontWeight: 600,
                display: "flex",
                alignItems: "center",
                gap: "0.5rem",
              }}
            >
              {selectedIntentLabel}
              {resolvedService && (
                <span
                  style={{
                    fontSize: "0.65rem",
                    fontWeight: 500,
                    padding: "2px 8px",
                    borderRadius: "999px",
                    background: "var(--glass-border)",
                    border: "1px solid var(--glass-border)",
                    color: "var(--text-dim)",
                    letterSpacing: "0.02em",
                  }}
                >
                  {resolvedService}
                </span>
              )}
            </h3>
            <span style={{ fontSize: "0.75rem", color: "var(--text-dim)" }}>
              Intent-based AI Routing
            </span>
          </div>
        </div>

        <div style={{ display: "flex", gap: "1.5rem", alignItems: "center" }}>
        <QuotaStatus 
            token={token} 
            trigger={quotaRefreshTrigger} 
            pushedData={pushedQuota}
          />
          <div style={{ display: "flex", gap: "0.8rem", alignItems: "center" }}>
          <button
            onClick={() => setIsDarkMode(!isDarkMode)}
            style={{
              background: "rgba(128, 128, 128, 0.2)",
              border: "1px solid var(--glass-border)",
              color: isDarkMode ? "#fbbf24" : "#4f46e5",
              cursor: "pointer",
              fontSize: "1.2rem",
              padding: "0.3rem 0.5rem",
              borderRadius: "8px",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
            title={isDarkMode ? "Switch to Light Mode" : "Switch to Dark Mode"}
          >
            {isDarkMode ? "☀️" : "🌙"}
          </button>
          {isAdmin && (
            <button
              className="dashboard-btn"
              onClick={onOpenAdmin}
              style={{
                borderColor: "var(--accent-primary)",
                background: isDarkMode ? "rgba(59, 130, 246, 0.1)" : "rgba(79, 70, 229, 0.08)",
                fontWeight: 600,
              }}
            >
              Intent Admin
            </button>
          )}
          <button
            className="dashboard-btn"
            onClick={fetchDocuments}
            disabled={loading}
          >
            {loading ? "..." : "Docs"}
          </button>
          <button
            className="dashboard-btn"
            onClick={fetchAdmin}
            disabled={loading}
          >
            {loading ? "..." : "Admin"}
          </button>
          <button
            className="dashboard-btn"
            onClick={logout}
            style={{ borderColor: "rgba(239, 68, 68, 0.3)", color: "#f87171" }}
          >
            Logout
          </button>
        </div>
        </div>
      </div>

      {/* ── Messages ─────────────────────────────────────────────────────── */}
      <div className="chat-messages-container">
        {error && (
          <div className="message-wrapper ai" style={{ alignSelf: "center" }}>
            <div
              className="message-bubble"
              style={{
                borderColor: "rgba(239, 68, 68, 0.4)",
                color: "#fca5a5",
              }}
            >
              System Alert: {error}
            </div>
          </div>
        )}

        {showDocs && documents?.length > 0 && (
          <div
            className="message-wrapper ai"
            style={{ alignSelf: "center", width: "100%", maxWidth: "900px" }}
          >
            <div
              className="message-bubble"
              style={{ width: "100%", background: "var(--bg-deep)" }}
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  marginBottom: "1rem",
                }}
              >
                <h4 style={{ color: "var(--accent-primary)" }}>
                  Fetched Resources
                </h4>
                <button
                  onClick={() => setShowDocs(false)}
                  style={{
                    background: "none",
                    border: "none",
                    color: "var(--text-dim)",
                    cursor: "pointer",
                  }}
                >
                  ✕
                </button>
              </div>
              <ul
                style={{
                  listStyle: "none",
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))",
                  gap: "0.5rem",
                }}
              >
                {documents.map((doc) => (
                  <li
                    key={doc.id}
                    style={{
                      padding: "0.5rem",
                      background: "var(--bg-card)",
                      borderRadius: "8px",
                      fontSize: "0.85rem",
                      border: "1px solid var(--glass-border)",
                      color: "var(--text-main)",
                    }}
                  >
                    ▹ {doc.name}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}

        {messages.map((m, i) => (
          <div
            key={i}
            className={`message-wrapper ${m.role} ${m.isError ? "error" : ""}`}
          >
            <div className={`avatar ${m.role === "user" ? "user" : "ai"}`}>
              {m.role === "user" ? "ME" : "AI"}
            </div>
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                width: "100%",
              }}
            >
              <div className={`message-bubble ${m.isCancelled ? "cancelled-bubble" : ""}`}>
                {m.isCancelled ? (
                  <div className="cancelled-message">
                    {m.content && (
                      <span style={{ whiteSpace: "pre-wrap", display: "block", marginBottom: "0.5rem" }}>
                        {m.content}
                      </span>
                    )}
                    <span className="cancelled-label">User cancelled response</span>
                  </div>
                ) : (
                  <>
                    <span style={{ whiteSpace: "pre-wrap" }}>{m.content}</span>
                    {m.isStreaming && (
                      <span className="ai-cursor" aria-hidden="true" />
                    )}
                  </>
                )}

                {/* Kong Metrics */}
                {m.metrics && (
                  <div
                    style={{
                      marginTop: "0.8rem",
                      paddingTop: "0.8rem",
                      borderTop: "1px solid rgba(255,255,255,0.1)",
                      display: "flex",
                      flexWrap: "wrap",
                      gap: "1rem",
                      fontSize: "0.75rem",
                      color: "var(--text-dim)",
                    }}
                  >
                    <div title="Full Kong path latency">
                      ⏱{" "}
                      <span style={{ color: "var(--accent-primary)" }}>
                        {m.metrics.proxyLatency}ms
                      </span>{" "}
                      Proxy
                    </div>
                    <div title="Target (Ollama) latency">
                      🚀{" "}
                      <span style={{ color: "var(--accent-primary)" }}>
                        {m.metrics.upstreamLatency}ms
                      </span>{" "}
                      Upstream
                    </div>
                    {m.metrics.debug && (
                      <div style={{ fontStyle: "italic", opacity: 0.8 }}>
                        ⚙ {m.metrics.debug}
                      </div>
                    )}
                  </div>
                )}

                {/* PII indicator (server-side inspection summary) */}
                {Array.isArray(m.detectedPiiTypes) &&
                  m.detectedPiiTypes.length > 0 && (
                    <div
                      style={{
                        marginTop: "1rem",
                        padding: "0.75rem 1rem",
                        background: "rgba(239, 68, 68, 0.1)",
                        border: "1px solid rgba(239, 68, 68, 0.3)",
                        borderRadius: "12px",
                        fontSize: "0.8rem",
                        color: "#f87171",
                        display: "flex",
                        flexDirection: "column",
                        gap: "0.4rem",
                        boxShadow: "0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)",
                        backdropFilter: "blur(4px)",
                        maxWidth: "100%",
                      }}
                      title="Server-side PII Detection Summary"
                    >
                      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                        <span style={{ 
                          background: "#ef4444", 
                          color: "white", 
                          padding: "2px 8px", 
                          borderRadius: "999px", 
                          fontWeight: 700,
                          fontSize: "0.7rem",
                          letterSpacing: "0.02em",
                          whiteSpace: "nowrap"
                        }}>
                          {m.piiCount || m.detectedPiiTypes.length} DETECTED
                        </span>
                        <span style={{ fontWeight: 600, fontSize: "0.85rem" }}>PII Scan Result</span>
                      </div>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>
                        {m.detectedPiiTypes.map(type => (
                          <span key={type} style={{
                            background: "rgba(239, 68, 68, 0.2)",
                            padding: "1px 6px",
                            borderRadius: "4px",
                            fontSize: "0.7rem",
                            border: "1px solid rgba(239, 68, 68, 0.2)"
                          }}>
                            {type}
                          </span>
                        ))}
                      </div>
                      {m.resolvedSensitivity && (
                        <div style={{ 
                          marginTop: "0.2rem", 
                          fontSize: "0.7rem", 
                          opacity: 0.8,
                          borderTop: "1px solid rgba(239, 68, 68, 0.1)",
                          paddingTop: "0.4rem"
                        }}>
                          Resolved Sensitivity: <span style={{ fontWeight: 700, color: "#fca5a5" }}>{m.resolvedSensitivity}</span>
                        </div>
                      )}
                    </div>
                  )}
              </div>

              {/* Request ID below AI bubble */}
              {m.role === "assistant" && m.requestId && (
                <div
                  style={{
                    marginTop: "0.25rem",
                    fontSize: "0.7rem",
                    color: "var(--text-dim)",
                    opacity: 0.6,
                    paddingLeft: "0.2rem",
                  }}
                >
                  Request ID: {m.requestId.slice(0, 8)}-…
                </div>
              )}

              <div className="timestamp">{m.timestamp}</div>
            </div>
          </div>
        ))}

        {/* Typing dots — while waiting for first token */}
        {isLoading && (
          <div className="message-wrapper ai">
            <div className="avatar ai">AI</div>
            <div className="message-bubble" style={{ padding: "0.5rem 1rem" }}>
              <div className="typing-dots">
                <div className="dot"></div>
                <div className="dot"></div>
                <div className="dot"></div>
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* ── Input bar ────────────────────────────────────────────────────── */}
      <div className="input-section">
        <div className="input-container-pill">
          <textarea
            ref={textareaRef}
            className="type-area"
            placeholder="Ask anything or request docs..."
            rows="1"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isActive}
          />
          <div className="input-actions-group">
            {/* Sensitivity selector */}
            <select
              className="model-select-dropdown"
              value={selectedSensitivity}
              onChange={(e) => setSelectedSensitivity(e.target.value)}
              disabled={isActive}
              title="Declare payload sensitivity"
              style={{
                borderColor:
                  selectedSensitivity === "HIGH"
                    ? "rgba(248, 113, 113, 0.5)"
                    : selectedSensitivity === "MEDIUM"
                      ? "rgba(250, 204, 21, 0.5)"
                      : "rgba(74, 222, 128, 0.4)",
                color:
                  selectedSensitivity === "HIGH"
                    ? "#f87171"
                    : selectedSensitivity === "MEDIUM"
                      ? "#facc15"
                      : "#4ade80",
              }}
            >
              {SENSITIVITY_LEVELS.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>

            {/* Intent selector */}
            <select
              className="model-select-dropdown"
              value={selectedIntent || ""}
              onChange={(e) => {
                setSelectedIntent(e.target.value);
                setResolvedService(null);
              }}
              disabled={isActive}
            >
              {INTENTS ? (
                INTENTS.map((intent) => (
                  <option key={intent.value} value={intent.value}>
                    {intent.label}
                  </option>
                ))
              ) : (
                <option>Loading intents...</option>
              )}
            </select>
            {isActive ? (
              <button
                className="send-btn-pill stop-btn"
                onClick={handleCancel}
                title="Cancel response"
              >
                <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                  <rect x="4" y="4" width="16" height="16" rx="2" />
                </svg>
              </button>
            ) : (
              <button
                className="send-btn-pill"
                onClick={handleSend}
                disabled={!input.trim()}
              >
                <svg
                  viewBox="0 0 24 24"
                  width="20"
                  height="20"
                  fill="currentColor"
                >
                  <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" />
                </svg>
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default AIChat;
