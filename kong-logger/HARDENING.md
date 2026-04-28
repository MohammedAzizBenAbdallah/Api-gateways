# kong-logger hardening - deferred work

This file tracks reliability/performance improvements that have been
*deliberately deferred* until traffic justifies the added complexity.
The current shape is appropriate for the volumes we run today
(low double-digit RPS against `kong-dp`); revisit when the triggers
below are met.

## 1. Micro-batched Postgres inserts

**Current state.** `kong-logger/sinks/postgres.js` writes one row per
request via a parameterized `INSERT`, capped at concurrency 5 by a
`BoundedQueue`. This is fine at the present rate but will saturate
`platform-db` IOPS under sustained load.

**Trigger to implement.** Either of:

- Sustained `> 200` requests/sec against `kong-dp` (visible in
  `kong_http_requests_total` rate in Prometheus).
- Visible IOPS pressure on `platform-db` (CPU > 60%, or
  `pg_stat_statements` showing `INSERT INTO api_usage_records` as the
  top time consumer).

**Implementation sketch.** Replace the per-record worker with a
batcher:

- Accumulate records into an in-memory array up to `BATCH_SIZE` (e.g.
  500) or `BATCH_MS` (e.g. 1000 ms), whichever comes first.
- Flush via `INSERT INTO api_usage_records (...) SELECT * FROM UNNEST(
  $1::text[], $2::timestamptz[], ...)` for low-overhead bulk insert.
- For real volume (10x our current ceiling), switch to `pg-copy-streams`
  and `COPY ... FROM STDIN BINARY`.

Keep the bounded queue in front; it now buffers *batches* rather than
individual records.

## 2. Materialized `api_usage_hourly`

**Current state.** `api_usage_hourly` is a regular view in
`backend/scripts/init-platform-db-usage.sql`; every dashboard query
re-aggregates the underlying table.

**Trigger to implement.** Either of:

- A user-facing billing dashboard ships and queries this view on every
  page load.
- `api_usage_records` exceeds ~1M rows and the dashboard query
  noticeably exceeds 500 ms.

**Implementation options.**

- *Plain Postgres path.* Convert to `MATERIALIZED VIEW` and refresh on
  a schedule via `pg_cron`:

  ```sql
  CREATE MATERIALIZED VIEW api_usage_hourly AS ... ;
  CREATE UNIQUE INDEX ON api_usage_hourly (bucket_hour, api_id, stage, consumer_id);
  -- refresh every 5 minutes
  SELECT cron.schedule('refresh-api-usage-hourly', '*/5 * * * *',
    $$REFRESH MATERIALIZED VIEW CONCURRENTLY api_usage_hourly$$);
  ```

- *TimescaleDB path.* Convert `api_usage_records` to a hypertable on
  `request_time`, then declare `api_usage_hourly` as a continuous
  aggregate. Best long-term option once we are in the millions of rows.

## 3. Notes on what is *not* deferred

The following findings from the principal review are addressed in the
current code; this section is the rationale for not revisiting them:

- **Backpressure on file sink.** `sinks/file.js` honours `drain`.
- **mkdirSync crash on EACCES.** `sinks/file.js` traps and emits
  `FATAL` then exits, so Docker `restart: on-failure` surfaces it.
- **Body-limit DoS surface.** Reduced from 5 MB to 256 kB with explicit
  413 handling in `server.js`.
- **/health observability.** `server.js` surfaces `pg-sink` queue stats
  so external monitors can detect sustained pressure.
- **"Rollover race" on day boundary.** Single-threaded JS + atomic
  reference swap in `_ensureStream` is sufficient; no mutex needed.
