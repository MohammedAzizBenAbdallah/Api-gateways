// sinks/postgres.js
//
// Inserts one row per access log into the `api_usage_records` table on
// platform-db. Schema lives in backend/scripts/init-platform-db-usage.sql.
//
// Reliability model:
//   - Writes are pushed into a BoundedQueue (concurrency matches pg.Pool max,
//     so we never overdrive the pool).
//   - Buffer cap protects us from OOM during a Postgres outage; on overflow
//     records are dropped and the counter is exposed via stats() for /health.
//   - Worker errors are logged inside _insert; the queue treats the worker
//     as best-effort and never deadlocks.

"use strict";

const { Pool } = require("pg");
const { BoundedQueue } = require("../util/bounded_queue");

const POOL_MAX = 5;
const QUEUE_MAX = 5000;

const INSERT_SQL = `
  INSERT INTO api_usage_records (
    request_id,
    request_time,
    api_id,
    stage,
    http_method,
    path,
    resource_path,
    status,
    request_length,
    response_length,
    response_latency_ms,
    integration_latency_ms,
    source_ip,
    user_agent,
    consumer_id,
    consumer_username,
    principal_id,
    api_key_id,
    cache_hit,
    data_processed_bytes,
    raw
  ) VALUES (
    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
    $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21
  )
`;

class PostgresSink {
  constructor({ connectionString }) {
    this.enabled = Boolean(connectionString);
    if (!this.enabled) {
      console.warn(
        "[pg-sink] PLATFORM_DB_URL not set; postgres sink disabled.",
      );
      this.queue = null;
      return;
    }
    this.pool = new Pool({
      connectionString,
      max: POOL_MAX,
      idleTimeoutMillis: 30000,
      connectionTimeoutMillis: 5000,
    });
    this.pool.on("error", (err) => {
      console.error("[pg-sink] idle client error:", err.message);
    });

    this.queue = new BoundedQueue({
      name: "pg-sink",
      concurrency: POOL_MAX,
      maxSize: QUEUE_MAX,
      worker: (record) => this._insert(record),
    });
  }

  write(record) {
    if (!this.enabled) return;
    this.queue.push(record);
  }

  async _insert(record) {
    const requestTime = record.requestTimeEpoch
      ? new Date(record.requestTimeEpoch)
      : new Date();

    const params = [
      record.requestId,
      requestTime,
      record.apiId,
      record.stage,
      record.httpMethod,
      record.path,
      record.resourcePath,
      record.status,
      record.requestLength,
      record.responseLength,
      record.responseLatency,
      record.integration?.latency,
      // Handle invalid/missing IPs gracefully: Postgres `inet` would reject "".
      record.identity?.sourceIp || null,
      record.identity?.userAgent,
      record.identity?.caller,
      record.identity?.user,
      record.identity?.principalId,
      record.identity?.apiKeyId,
      Boolean(record.billing?.cacheHit),
      record.billing?.dataProcessedBytes ?? 0,
      record,
    ];

    try {
      await this.pool.query(INSERT_SQL, params);
    } catch (err) {
      console.error("[pg-sink] insert failed:", err.message);
    }
  }

  stats() {
    if (!this.enabled || !this.queue) {
      return { enabled: false, depth: 0, inFlight: 0, droppedTotal: 0 };
    }
    return { enabled: true, ...this.queue.stats() };
  }

  async close() {
    if (this.queue) {
      await this.queue.drainAndWait(5000);
    }
    if (this.pool) {
      await this.pool.end();
    }
  }
}

module.exports = { PostgresSink };
