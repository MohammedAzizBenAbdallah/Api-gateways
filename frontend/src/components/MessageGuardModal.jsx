/**
 * MessageGuardModal.jsx
 * ─────────────────────────────────────────────────────────────────
 * Premium security warning modal displayed when useMessageGuard
 * detects a potential issue with the user's message.
 *
 * Props:
 *  - guardResult  : { blocked, warn, reason, details, category }
 *  - onConfirm()  : user confirmed they want to send anyway (warn only)
 *  - onCancel()   : user acknowledged block / chose to edit
 */

import React, { useEffect } from "react";

const CATEGORY_CONFIG = {
  empty:      { icon: "\u270f\ufe0f",  color: "#94a3b8", label: "Empty Message" },
  length:     { icon: "\ud83d\udccf",  color: "#f59e0b", label: "Message Too Long" },
  injection:  { icon: "\ud83d\udee1\ufe0f",  color: "#ef4444", label: "Security Threat Blocked" },
  rate_limit: { icon: "\u23f1\ufe0f",  color: "#f59e0b", label: "Slow Down" },
  credential: { icon: "\ud83d\udd11",  color: "#ef4444", label: "Credential Exposure Risk" },
  pii:        { icon: "\ud83d\udd12",  color: "#f59e0b", label: "Personal Data Detected" },
  default:    { icon: "\u26a0\ufe0f",  color: "#f59e0b", label: "Warning" },
};

export default function MessageGuardModal({ guardResult, onConfirm, onCancel }) {
  if (!guardResult) return null;

  const { blocked, warn, reason, details, category } = guardResult;
  if (!blocked && !warn) return null;

  const cfg = CATEGORY_CONFIG[category] || CATEGORY_CONFIG.default;
  const accentColor = cfg.color;

  // Close on Escape key
  useEffect(() => {
    const handler = (e) => { if (e.key === "Escape") onCancel(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onCancel]);

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 9999,
        background: "rgba(0,0,0,0.65)",
        backdropFilter: "blur(6px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "1rem",
        animation: "guardFadeIn 0.15s ease",
      }}
      onClick={(e) => { if (e.target === e.currentTarget) onCancel(); }}
    >
      <div
        style={{
          background: "var(--bg-card, #1a1a2e)",
          border: "1px solid " + accentColor + "40",
          borderRadius: "20px",
          boxShadow: "0 0 40px " + accentColor + "30, 0 20px 60px rgba(0,0,0,0.5)",
          maxWidth: "480px",
          width: "100%",
          overflow: "hidden",
          animation: "guardSlideUp 0.2s ease",
        }}
      >
        {/* Header */}
        <div
          style={{
            background: "linear-gradient(135deg, " + accentColor + "20, " + accentColor + "05)",
            borderBottom: "1px solid " + accentColor + "30",
            padding: "1.5rem 1.75rem 1.25rem",
            display: "flex",
            alignItems: "center",
            gap: "0.85rem",
          }}
        >
          <span style={{ fontSize: "2rem", lineHeight: 1 }}>{cfg.icon}</span>
          <div>
            <div style={{ fontSize: "0.7rem", fontWeight: 700, letterSpacing: "0.12em", textTransform: "uppercase", color: accentColor, marginBottom: "0.2rem" }}>
              {blocked ? "Blocked" : "Warning"}
            </div>
            <h2 style={{ margin: 0, fontSize: "1.1rem", fontWeight: 700, color: "var(--text-header, #f1f5f9)" }}>
              {cfg.label}
            </h2>
          </div>
        </div>

        {/* Body */}
        <div style={{ padding: "1.5rem 1.75rem" }}>
          <p style={{ margin: "0 0 1rem", color: "var(--text-primary, #cbd5e1)", fontSize: "0.95rem", lineHeight: 1.6 }}>
            {reason}
          </p>

          {details.length > 0 && (
            <div
              style={{
                background: accentColor + "0d",
                border: "1px solid " + accentColor + "25",
                borderRadius: "12px",
                padding: "0.85rem 1rem",
              }}
            >
              {details.map((d, i) => (
                <div
                  key={i}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "0.6rem",
                    padding: "0.25rem 0",
                    color: "var(--text-primary, #cbd5e1)",
                    fontSize: "0.88rem",
                  }}
                >
                  <span style={{ color: accentColor, fontWeight: 700 }}>\u2192</span>
                  {d}
                </div>
              ))}
            </div>
          )}

          {/* Info note for warn cases */}
          {warn && !blocked && (
            <p style={{ margin: "1rem 0 0", fontSize: "0.8rem", color: "var(--text-dim, #64748b)", lineHeight: 1.5 }}>
              The backend security layer will also scan your message before sending it to the AI. This is an early warning to protect you.
            </p>
          )}
        </div>

        {/* Actions */}
        <div
          style={{
            padding: "1rem 1.75rem 1.5rem",
            display: "flex",
            gap: "0.75rem",
            justifyContent: "flex-end",
          }}
        >
          <button
            onClick={onCancel}
            style={{
              padding: "0.6rem 1.4rem",
              borderRadius: "10px",
              border: "1px solid var(--glass-border, #334155)",
              background: "transparent",
              color: "var(--text-primary, #cbd5e1)",
              fontSize: "0.875rem",
              fontWeight: 600,
              cursor: "pointer",
              transition: "all 0.15s ease",
            }}
            onMouseEnter={(e) => { e.target.style.background = "var(--glass-border, #334155)"; }}
            onMouseLeave={(e) => { e.target.style.background = "transparent"; }}
          >
            {blocked ? "Edit Message" : "Cancel"}
          </button>

          {warn && !blocked && (
            <button
              onClick={onConfirm}
              style={{
                padding: "0.6rem 1.4rem",
                borderRadius: "10px",
                border: "1px solid " + accentColor + "60",
                background: accentColor + "20",
                color: accentColor,
                fontSize: "0.875rem",
                fontWeight: 700,
                cursor: "pointer",
                transition: "all 0.15s ease",
              }}
              onMouseEnter={(e) => { e.target.style.background = accentColor + "35"; }}
              onMouseLeave={(e) => { e.target.style.background = accentColor + "20"; }}
            >
              Send Anyway
            </button>
          )}
        </div>
      </div>

      <style>{`
        @keyframes guardFadeIn  { from { opacity: 0 } to { opacity: 1 } }
        @keyframes guardSlideUp { from { transform: translateY(20px); opacity: 0 } to { transform: translateY(0); opacity: 1 } }
      `}</style>
    </div>
  );
}
