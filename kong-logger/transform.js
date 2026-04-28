// transform.js
//
// Pure transformation: take a Kong `http-log` plugin payload and return an
// AWS API Gateway-style access log record. Same field names and overall
// shape AWS uses for `$context.*` access-log variables, so a downstream
// billing system can be built against the same schema we'd hit if we were
// reading CloudWatch access logs directly.
//
// Reference (AWS access log $context fields):
//   requestId, extendedRequestId, apiId, stage, httpMethod, resourcePath,
//   path, protocol, status, responseLength, requestLength, responseLatency,
//   requestTime / requestTimeEpoch, identity.{sourceIp,userAgent,caller,
//   user,principalId,apiKeyId}, authorizer.claims, integration.{latency,
//   status,error}, error.{message,responseType}, waf.action.
//
// We additionally attach a `billing` block aggregating per-request counters
// (requests, dataProcessedBytes, cacheHit) so the billing job can do its
// math directly from the log record.

"use strict";

const MONTHS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

function pad(n, width = 2) {
  const s = String(n);
  return s.length >= width ? s : "0".repeat(width - s.length) + s;
}

function formatApacheClf(epochMs) {
  // 28/Apr/2026:11:00:00 +0000 (UTC; matches AWS API Gateway requestTime).
  if (!epochMs || Number.isNaN(epochMs)) return null;
  const d = new Date(epochMs);
  const day = pad(d.getUTCDate());
  const month = MONTHS[d.getUTCMonth()];
  const year = d.getUTCFullYear();
  const hh = pad(d.getUTCHours());
  const mm = pad(d.getUTCMinutes());
  const ss = pad(d.getUTCSeconds());
  return `${day}/${month}/${year}:${hh}:${mm}:${ss} +0000`;
}

function deriveProtocol(request) {
  if (!request) return "HTTP/1.1";
  const url = request.url || "";
  if (url.startsWith("https://")) return "HTTPS/1.1";
  return "HTTP/1.1";
}

function classifyError(status) {
  if (status >= 500) return { responseType: "SERVER_ERROR" };
  if (status >= 400) return { responseType: "CLIENT_ERROR" };
  return null;
}

function lowercaseHeaders(headers) {
  const out = {};
  if (!headers || typeof headers !== "object") return out;
  for (const k of Object.keys(headers)) {
    out[k.toLowerCase()] = headers[k];
  }
  return out;
}

function safeNumber(v) {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

function toAccessLog(payload) {
  const req = payload?.request || {};
  const res = payload?.response || {};
  const latencies = payload?.latencies || {};
  const route = payload?.route || {};
  const service = payload?.service || {};
  const consumer = payload?.consumer || null;

  const reqHeaders = lowercaseHeaders(req.headers);
  const resHeaders = lowercaseHeaders(res.headers);

  const status = safeNumber(res.status);
  const startedAt = safeNumber(payload?.started_at);
  const requestLength = safeNumber(req.size);
  const responseLength = safeNumber(res.size);

  const errClass = classifyError(status);

  return {
    requestId:
      reqHeaders["x-request-id"] || reqHeaders["x-correlation-id"] || null,
    requestTime: formatApacheClf(startedAt),
    requestTimeEpoch: startedAt || null,
    apiId: service.name || service.id || null,
    stage: route.name || null,
    httpMethod: req.method || null,
    resourcePath: Array.isArray(route.paths) ? route.paths[0] || null : null,
    path: req.uri || null,
    protocol: deriveProtocol(req),
    status,
    requestLength,
    responseLength,
    responseLatency: safeNumber(latencies.request),
    identity: {
      sourceIp: payload?.client_ip || null,
      userAgent: reqHeaders["user-agent"] || null,
      caller: consumer?.id || null,
      user: consumer?.username || null,
      principalId: consumer?.custom_id || reqHeaders["x-userinfo-sub"] || null,
      apiKeyId: reqHeaders["apikey"] ? String(reqHeaders["apikey"]) : null,
    },
    authorizer: {
      claims: {
        sub: reqHeaders["x-userinfo-sub"] || null,
        email: reqHeaders["x-userinfo-email"] || null,
        tenant:
          reqHeaders["x-userinfo-tenant"] ||
          reqHeaders["x-tenant-id"] ||
          null,
      },
    },
    integration: {
      latency: safeNumber(latencies.proxy),
      status,
      error: status >= 500 ? "UPSTREAM_ERROR" : null,
    },
    error: {
      message: errClass ? `HTTP ${status}` : null,
      responseType: errClass ? errClass.responseType : null,
    },
    waf: {
      action: reqHeaders["x-waf-action"] || "ALLOW",
    },
    billing: {
      requests: 1,
      dataProcessedBytes: requestLength + responseLength,
      cacheHit:
        (resHeaders["x-cache-status"] || "").toString().toLowerCase() === "hit",
    },
  };
}

module.exports = { toAccessLog, formatApacheClf };
