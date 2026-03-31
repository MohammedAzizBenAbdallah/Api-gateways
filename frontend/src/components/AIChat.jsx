import React, { useState, useRef, useEffect } from "react";
import useAuth from "../hooks/useAuth";

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
  fetchNextora,
  loading,
  error,
  systemInfo,
  documents,
}) => {
  const { token } = useAuth();

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
  const messagesEndRef = useRef(null);
  const textareaRef = useRef(null);

  // ── Intent definitions ────────────────────────────────────────────────────
  const INTENTS = [
    { value: "code_generation", label: "Code Generation" },
    { value: "general_chat", label: "General Chat" },
    { value: "summarization", label: "Summarization" },
  ];

  const [selectedIntent, setSelectedIntent] = useState(INTENTS[0].value);
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

    const userMessage = {
      role: "user",
      content: input.trim(),
      timestamp: new Date().toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
      }),
    };

    const conversationHistory = [...messages, userMessage];

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsLoading(true); // show typing dots while waiting for first token

    try {
      const response = await fetch("/api/ai/request", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
          "kong-header": "true",
          Accept: "text/event-stream",
        },
        body: JSON.stringify({
          intent: selectedIntent,
          payload: {
            messages: conversationHistory.map((m) => ({
              role: m.role,
              content: m.content,
            })),
          },
          metadata: {
            sensitivity: "LOW",
            environment: "dev",
          },
        }),
      });

      // ── Pre-stream error (auth failure, 422, 403) ─────────────────────
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        let errMsg = "Sorry, I'm having trouble connecting to the AI service.";

        if (response.status === 400) {
          errMsg = "Message blocked by AI Prompt Guard.";
        } else if (errData.detail) {
          // FastAPI/Pydantic validation errors (422) return a list of objects in 'detail'
          errMsg =
            typeof errData.detail === "string"
              ? errData.detail
              : JSON.stringify(errData.detail);
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
            if (data.resolved_service)
              setResolvedService(data.resolved_service);
            setMessages((prev) => {
              const updated = [...prev];
              updated[updated.length - 1] = {
                ...updated[updated.length - 1],
                isStreaming: false,
                requestId: data.request_id || null,
                resolvedService: data.resolved_service || null,
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
    } finally {
      setIsLoading(false);
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
                    background: "rgba(255,255,255,0.08)",
                    border: "1px solid rgba(255,255,255,0.15)",
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

        <div style={{ display: "flex", gap: "0.8rem" }}>
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
            onClick={fetchNextora}
            disabled={loading}
            style={{ borderColor: "rgba(16, 185, 129, 0.4)", color: "#34d399", background: "rgba(16, 185, 129, 0.05)" }}
          >
            {loading ? "..." : "Nextora Portal"}
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

        {systemInfo && (
          <div className="message-wrapper ai" style={{ alignSelf: "center" }}>
            <div
              className="message-bubble"
              style={{
                borderColor: "rgba(16, 185, 129, 0.4)",
                color: "#6ee7b7",
                background: "rgba(16, 185, 129, 0.05)"
              }}
            >
              {systemInfo}
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
              style={{ width: "100%", background: "rgba(255,255,255,0.03)" }}
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
                      background: "rgba(0,0,0,0.2)",
                      borderRadius: "8px",
                      fontSize: "0.85rem",
                      border: "1px solid var(--glass-border)",
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
              <div className="message-bubble">
                {/* Content + blinking cursor while streaming */}
                <span style={{ whiteSpace: "pre-wrap" }}>{m.content}</span>
                {m.isStreaming && (
                  <span className="ai-cursor" aria-hidden="true" />
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
            <select
              className="model-select-dropdown"
              value={selectedIntent}
              onChange={(e) => {
                setSelectedIntent(e.target.value);
                setResolvedService(null);
              }}
              disabled={isActive}
            >
              {INTENTS.map((intent) => (
                <option key={intent.value} value={intent.value}>
                  {intent.label}
                </option>
              ))}
            </select>
            <button
              className="send-btn-pill"
              onClick={handleSend}
              disabled={isActive || !input.trim()}
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
          </div>
        </div>
      </div>
    </div>
  );
};

export default AIChat;
