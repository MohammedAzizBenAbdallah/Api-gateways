/**
 * useMessageGuard.js
 * ─────────────────────────────────────────────────────────────────
 * Professional client-side pre-flight guard for AI chat messages.
 *
 * Checks performed BEFORE any network request is made:
 *   1. Empty / whitespace-only messages           → HARD BLOCK
 *   2. Message too long (>8000 chars)             → HARD BLOCK
 *   3. Script / HTML injection patterns           → HARD BLOCK
 *   4. SQL injection patterns                     → HARD BLOCK
 *   5. Client-side rate limiting (5 req / 10s)   → HARD BLOCK
 *   6. Detected API keys / tokens in message      → SOFT WARN
 *   7. Detected PII (email, phone, SSN, CC)       → SOFT WARN
 *
 * Returns: { guardCheck, registerSend }
 */

import { useRef } from "react";

// ── Hard-block patterns ──────────────────────────────────────────

const SCRIPT_INJECTION = /<\s*script[\s\S]*?>[\s\S]*?<\s*\/\s*script\s*>/i;
const HTML_TAG_INJECT  = /<\s*(iframe|object|embed|form|input|link|meta|style|base)[^>]*>/i;
const EVENT_HANDLER    = /\bon\w+\s*=\s*["'][^"']*["']/i;
const JAVASCRIPT_URI   = /javascript\s*:/i;
const DATA_URI         = /data\s*:\s*text\/html/i;

const SQL_PATTERNS = [
  /'\s*;\s*(drop|delete|truncate|alter|update|insert)\s+/i,
  /union\s+(all\s+)?select\s+/i,
  /\bexec\s*\(|execute\s*\(/i,
  /xp_cmdshell/i,
  /--\s*$/m,
];

// ── Soft-warn patterns (PII) ─────────────────────────────────────

const EMAIL_RE   = /[\w.+-]+@[\w-]+\.\w{2,}/;
const PHONE_RE   = /(\+?\d[\s.-]?)(\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4})/;
const SSN_RE     = /\b\d{3}-\d{2}-\d{4}\b/;
const CC_RE      = /\b(?:\d[ -]*?){13,19}\b/;
const IBAN_RE    = /\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b/i;

// ── Soft-warn patterns (credentials) ────────────────────────────

const AWS_KEY_RE    = /\bAKIA[0-9A-Z]{16}\b/;
const GOOGLE_KEY_RE = /\bAIza[0-9A-Za-z\-_]{35}\b/;
const GITHUB_PAT_RE = /\bghp_[A-Za-z0-9]{36}\b/;
const GENERIC_SECRET_RE = /(?:api[_-]?key|apikey|secret|token|password)\s*[:=]\s*["']?[A-Za-z0-9\-_.]{16,}["']?/i;
const JWT_RE = /\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b/;

// ── Luhn check for credit cards ──────────────────────────────────

function luhn(numStr) {
  const digits = numStr.replace(/\D/g, "");
  if (digits.length < 13 || digits.length > 19) return false;
  let sum = 0;
  for (let i = 0; i < digits.length; i++) {
    let d = parseInt(digits[digits.length - 1 - i]);
    if (i % 2 === 1) { d *= 2; if (d > 9) d -= 9; }
    sum += d;
  }
  return sum % 10 === 0;
}

// ── Rate limiter ─────────────────────────────────────────────────

const RATE_WINDOW_MS  = 10_000;
const RATE_MAX_SENDS  = 5;

// ── Main hook ────────────────────────────────────────────────────

export default function useMessageGuard() {
  const sendTimestamps = useRef([]);

  const guardCheck = (text) => {
    const t = text ?? "";

    // 1. Empty check
    if (!t.trim()) {
      return { blocked: true, warn: false, reason: "Empty message", details: [], category: "empty" };
    }

    // 2. Length check
    if (t.length > 8000) {
      return {
        blocked: true, warn: false,
        reason: "Message too long (" + t.length.toLocaleString() + " / 8,000 characters)",
        details: ["Reduce the length of your message."],
        category: "length",
      };
    }

    // 3. Script/HTML injection
    if (SCRIPT_INJECTION.test(t) || HTML_TAG_INJECT.test(t) || EVENT_HANDLER.test(t) || JAVASCRIPT_URI.test(t) || DATA_URI.test(t)) {
      return {
        blocked: true, warn: false,
        reason: "Script or HTML injection detected",
        details: ["Messages containing script tags or HTML event handlers are not allowed."],
        category: "injection",
      };
    }

    // 4. SQL injection
    for (const pattern of SQL_PATTERNS) {
      if (pattern.test(t)) {
        return {
          blocked: true, warn: false,
          reason: "SQL injection pattern detected",
          details: ["Your message contains patterns that match known SQL injection attacks."],
          category: "injection",
        };
      }
    }

    // 5. Rate limiting
    const now = Date.now();
    sendTimestamps.current = sendTimestamps.current.filter((ts) => now - ts < RATE_WINDOW_MS);
    if (sendTimestamps.current.length >= RATE_MAX_SENDS) {
      const oldest = sendTimestamps.current[0];
      const waitMs = RATE_WINDOW_MS - (now - oldest);
      return {
        blocked: true, warn: false,
        reason: "You are sending messages too quickly",
        details: ["Please wait " + Math.ceil(waitMs / 1000) + " seconds before sending another message."],
        category: "rate_limit",
      };
    }

    // 6. Credentials / API keys (soft warn)
    const credentialDetails = [];
    if (AWS_KEY_RE.test(t))         credentialDetails.push("AWS Access Key");
    if (GOOGLE_KEY_RE.test(t))      credentialDetails.push("Google API Key");
    if (GITHUB_PAT_RE.test(t))      credentialDetails.push("GitHub Personal Access Token");
    if (JWT_RE.test(t))             credentialDetails.push("JWT Token");
    if (GENERIC_SECRET_RE.test(t))  credentialDetails.push("API Key or Secret");

    if (credentialDetails.length > 0) {
      return {
        blocked: false, warn: true,
        reason: "Credential detected in message",
        details: credentialDetails,
        category: "credential",
      };
    }

    // 7. PII detection (soft warn)
    const piiDetails = [];
    if (EMAIL_RE.test(t))  piiDetails.push("Email address");
    if (PHONE_RE.test(t))  piiDetails.push("Phone number");
    if (SSN_RE.test(t))    piiDetails.push("Social Security Number (SSN)");
    if (IBAN_RE.test(t))   piiDetails.push("IBAN / Bank account number");

    const ccMatches = t.match(/\b(?:\d[ -]*?){13,19}\b/g) || [];
    if (ccMatches.some((m) => luhn(m))) piiDetails.push("Credit card number");

    if (piiDetails.length > 0) {
      return {
        blocked: false, warn: true,
        reason: "Personal data detected in message",
        details: piiDetails,
        category: "pii",
      };
    }

    // All checks passed
    return { blocked: false, warn: false, reason: null, details: [], category: null };
  };

  const registerSend = () => {
    sendTimestamps.current.push(Date.now());
  };

  return { guardCheck, registerSend };
}
