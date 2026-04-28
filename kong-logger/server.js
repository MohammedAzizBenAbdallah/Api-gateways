// server.js
//
// HTTP receiver for the Kong `http-log` plugin. For every incoming Kong
// log payload we:
//   1. Transform it to an AWS API Gateway-style access log record.
//   2. Fan it out to a daily-rotated JSONL file (archive) and a Postgres
//      table (`api_usage_records`) that the billing layer can aggregate.
//
// The HTTP response is decoupled from sink durability: we always return
// 200 quickly so a transient DB outage does not stall Kong's log queue.
// File and Postgres writes happen in the background.

"use strict";

const express = require("express");
const path = require("path");

const { toAccessLog } = require("./transform");
const { FileSink } = require("./sinks/file");
const { PostgresSink } = require("./sinks/postgres");

const PORT = parseInt(process.env.PORT || "9999", 10);
const LOGS_DIR = process.env.LOGS_DIR || path.join(__dirname, "logs");
const PLATFORM_DB_URL = process.env.PLATFORM_DB_URL || "";

const app = express();
app.use(express.json({ limit: "5mb" }));

const fileSink = new FileSink({ dir: LOGS_DIR });
const pgSink = new PostgresSink({ connectionString: PLATFORM_DB_URL });

app.get("/health", (_req, res) => {
  res.json({ status: "ok" });
});

app.post("/logs", (req, res) => {
  const payload = req.body;
  res.sendStatus(200);

  let record;
  try {
    record = toAccessLog(payload);
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

  fileSink.write(record);
  pgSink.write(record).catch((err) => {
    console.error("[pg-sink] unexpected error:", err.message);
  });
});

const server = app.listen(PORT, "0.0.0.0", () => {
  console.log(`Kong access log receiver listening on http://0.0.0.0:${PORT}`);
  console.log(`  file sink   -> ${LOGS_DIR}/access-YYYYMMDD.jsonl`);
  console.log(
    `  pg sink     -> ${PLATFORM_DB_URL ? "enabled" : "disabled (no PLATFORM_DB_URL)"}`,
  );
});

async function shutdown(signal) {
  console.log(`[server] received ${signal}, shutting down...`);
  server.close(async () => {
    await fileSink.close();
    await pgSink.close();
    process.exit(0);
  });
  setTimeout(() => process.exit(1), 10000).unref();
}

process.on("SIGINT", () => shutdown("SIGINT"));
process.on("SIGTERM", () => shutdown("SIGTERM"));
