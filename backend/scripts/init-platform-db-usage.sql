-- API usage records emitted by the kong-logger receiver, one row per
-- request handled by the Kong data plane. Schema mirrors the AWS API
-- Gateway access-log $context.* fields plus a per-request `billing`
-- block. The full AWS-shaped JSON is preserved in `raw` (JSONB) so the
-- billing layer can evolve without re-emitting historical records.

CREATE TABLE IF NOT EXISTS api_usage_records (
    id                       BIGSERIAL PRIMARY KEY,

    -- Request identity & timing
    request_id               TEXT,
    request_time             TIMESTAMPTZ NOT NULL,

    -- API surface
    api_id                   TEXT,
    stage                    TEXT,
    http_method              TEXT,
    path                     TEXT,
    resource_path            TEXT,

    -- Outcome
    status                   INTEGER,
    request_length           INTEGER,
    response_length          INTEGER,
    response_latency_ms      INTEGER,
    integration_latency_ms   INTEGER,

    -- Caller identity
    source_ip                INET,
    user_agent               TEXT,
    consumer_id              TEXT,
    consumer_username        TEXT,
    principal_id             TEXT,
    api_key_id               TEXT,

    -- Billing-relevant aggregates (denormalized for fast SQL aggregation)
    cache_hit                BOOLEAN     DEFAULT FALSE,
    data_processed_bytes     BIGINT      DEFAULT 0,

    -- Full original record for forward-compat / forensics
    raw                      JSONB       NOT NULL,

    created_at               TIMESTAMPTZ DEFAULT NOW()
);

-- Common billing query shapes:
--   GROUP BY consumer_id, date_trunc('hour', request_time)
--   GROUP BY api_id,      date_trunc('day',  request_time)
CREATE INDEX IF NOT EXISTS idx_aur_api_time
    ON api_usage_records (api_id, request_time);

CREATE INDEX IF NOT EXISTS idx_aur_consumer_time
    ON api_usage_records (consumer_id, request_time);

CREATE INDEX IF NOT EXISTS idx_aur_request_id
    ON api_usage_records (request_id);

-- Convenience view: AWS-style hourly usage rollup per consumer + api,
-- shaped to slot directly into a metered-billing pipeline.
CREATE OR REPLACE VIEW api_usage_hourly AS
SELECT
    date_trunc('hour', request_time) AS bucket_hour,
    api_id,
    stage,
    consumer_id,
    consumer_username,
    COUNT(*)                                    AS request_count,
    SUM(data_processed_bytes)                   AS data_processed_bytes,
    SUM(CASE WHEN status >= 400 THEN 1 ELSE 0 END) AS error_count,
    SUM(CASE WHEN cache_hit THEN 1 ELSE 0 END)  AS cache_hit_count,
    AVG(response_latency_ms)::INTEGER           AS avg_latency_ms
FROM api_usage_records
GROUP BY 1, 2, 3, 4, 5;
