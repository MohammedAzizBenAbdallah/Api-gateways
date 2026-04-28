// server.js
//
// HTTP receiver for the Kong `http-log` plugin. For every incoming Kong
// log payload we:
//   1. Transform it to an AWS API Gateway-style access log record.
//   2. Fan it out to a daily-rotated JSONL file (archive) and a Postgres
//      table (`api_usage_records`) that the billing layer can aggregate.
//
// Reliability:
//   - The Postgres sink is bounded via an in-memory queue (BoundedQueue)
//     so a slow DB cannot pile up unbounded promises and OOM us.
//   - The file sink honours stream backpressure (drain).
//   - Body size is capped tightly (256kb) with explicit 413 handling so a
//     misconfigured upstream cannot exhaust the heap.
//   - /health exposes pg-sink queue stats so external monitors can detect
//     sustained pressure without grepping logs.

"use strict";

const express = require("express");
const path = require("path");

const { toAccessLog } = require("./transform");
const { FileSink } = require("./sinks/file");
const { PostgresSink } = require("./sinks/postgres");

const PORT = parseInt(process.env.PORT || "9999", 10);
const LOGS_DIR = process.env.LOGS_DIR || path.join(__dirname, "logs");
const PLATFORM_DB_URL = process.env.PLATFORM_DB_URL || "";
const BODY_LIMIT = process.env.BODY_LIMIT || "256kb";

const app = express();
app.use(express.json({ limit: BODY_LIMIT, strict: true }));

// Express error handler for body-parser failures. We intentionally return
// a small status-only response (no body) so we never echo any portion of
// the rejected payload back into logs.
app.use((err, _req, res, next) => {
  if (!err) return next();
  if (err.type === "entity.too.large") {
    return res.status(413).end();
  }
  if (err.type === "entity.parse.failed" || err instanceof SyntaxError) {
    return res.status(400).end();
  }
  return res.status(400).end();
});

const fileSink = new FileSink({ dir: LOGS_DIR });
const pgSink = new PostgresSink({ connectionString: PLATFORM_DB_URL });

app.get("/health", (_req, res) => {
  res.json({
    status: "ok",
    pg: pgSink.stats(),
  });
});

app.post("/logs", async (req, res) => {
  // Acknowledge fast so Kong's http-log queue never stalls on us. Any
  // sink failure after this point is logged on our side and surfaced via
  // the /health stats counters; we never propagate sink errors to Kong.
  res.sendStatus(200);

  let record;
  try {
    record = toAccessLog(req.body);
  } catch (err) {
    console.error("[server] transform failed:", err.message);
    return;
  }

  if (process.env.LOG_VERBOSE === "1") {
    console.log(
      `[access] ${record.httpMethod || "-"} ${record.path || "-"} ` +
        `status=${record.status} latency=${record.responseLatency}ms ` +
        `apiId=${record.apiId || "-"} reqId=${record.requestId || "-"}`,
    );
  }

  // File sink is awaited (sub-millisecond on healthy disk) so we honour
  // backpressure deterministically. Postgres sink is fire-and-forget
  // through a bounded queue, which gives us the same behaviour without
  // blocking the request handler on DB latency.
  await fileSink.write(record);
  pgSink.write(record);
});

const server = app.listen(PORT, "0.0.0.0", () => {
  console.log(`Kong access log receiver listening on http://0.0.0.0:${PORT}`);
  console.log(`  body limit  -> ${BODY_LIMIT}`);
  console.log(`  file sink   -> ${LOGS_DIR}/access-YYYYMMDD.jsonl`);
  console.log(
    `  pg sink     -> ${PLATFORM_DB_URL ? "enabled" : "disabled (no PLATFORM_DB_URL)"}`,
  );
});

async function shutdown(signal) {
  console.log(`[server] received ${signal}, shutting down...`);
  server.close(async () => {
    try {
      await fileSink.close();
      await pgSink.close();
    } catch (err) {
      console.error("[server] error during shutdown:", err.message);
    }
    process.exit(0);
  });
  setTimeout(() => process.exit(1), 10000).unref();
}

process.on("SIGINT", () => shutdown("SIGINT"));
process.on("SIGTERM", () => shutdown("SIGTERM"));
