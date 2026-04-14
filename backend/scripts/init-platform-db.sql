-- Schema for Tenant Service Permissions and AI Orchestration Platform

-- 1. AI Services Table
CREATE TABLE IF NOT EXISTS ai_services (
    service_id    VARCHAR(255) PRIMARY KEY,
    model_name    VARCHAR(255) NOT NULL,
    provider_url  VARCHAR(255) NOT NULL,
    provider_type VARCHAR(255) DEFAULT 'ollama',
    description   TEXT,
    service_type  VARCHAR(255) DEFAULT 'on-prem'
);

-- 2. Intent Routing Table
CREATE TABLE IF NOT EXISTS intent_routing (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    intent_name       VARCHAR(255) UNIQUE NOT NULL,
    service_id        VARCHAR(255) NOT NULL REFERENCES ai_services(service_id),
    is_active         BOOLEAN DEFAULT TRUE,
    taxonomy_version  VARCHAR(255) NOT NULL,
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    updated_at        TIMESTAMPTZ DEFAULT NOW(),
    created_by        VARCHAR(255) NOT NULL
);

-- 3. AI Request Tracking
CREATE TABLE IF NOT EXISTS ai_requests (
    request_id           VARCHAR(255) PRIMARY KEY,
    tenant_id            VARCHAR(255) NOT NULL,
    intent               VARCHAR(255) NOT NULL,
    resolved_service_id  VARCHAR(255) REFERENCES ai_services(service_id),
    sensitivity          VARCHAR(255) NOT NULL DEFAULT 'LOW',
    resolved_sensitivity VARCHAR(255),
    environment          VARCHAR(255) NOT NULL DEFAULT 'dev',
    status               VARCHAR(255) NOT NULL DEFAULT 'received',
    started_at           TIMESTAMP NOT NULL,
    completed_at         TIMESTAMP,
    error_detail         TEXT
);

-- 4. Tenant Service Permissions
CREATE TABLE IF NOT EXISTS tenant_service_permissions (
    tenant_id  VARCHAR(255),
    service_id VARCHAR(255),
    allowed    BOOLEAN DEFAULT TRUE,
    granted_by VARCHAR(255),
    granted_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (tenant_id, service_id)
);

-- 5. Audit Logs
CREATE TABLE IF NOT EXISTS permission_audit_logs (
    id           SERIAL PRIMARY KEY,
    tenant_id    VARCHAR(255),
    service_id   VARCHAR(255),
    action       VARCHAR(255),
    performed_by VARCHAR(255),
    performed_at TIMESTAMPTZ DEFAULT NOW(),
    reason       TEXT,
    intent       VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS intent_mapping_audit_logs (
    id           SERIAL PRIMARY KEY,
    action       VARCHAR(255) NOT NULL,
    performed_by VARCHAR(255) NOT NULL,
    entity_id    VARCHAR(255) NOT NULL,
    old_value    JSONB,
    new_value    JSONB,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS policy_evaluation_audit_logs (
    id          SERIAL PRIMARY KEY,
    request_id  VARCHAR(255) NOT NULL,
    policy_id   VARCHAR(255) NOT NULL,
    effect      VARCHAR(255) NOT NULL,
    decision    VARCHAR(255) NOT NULL,
    context     JSONB,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- 8. Token Usage Logs
CREATE TABLE IF NOT EXISTS usage_token_logs (
    id                SERIAL PRIMARY KEY,
    request_id        VARCHAR(255) NOT NULL,
    tenant_id         VARCHAR(255) NOT NULL,
    service_id        VARCHAR(255) NOT NULL,
    model_name        VARCHAR(255),
    input_tokens      INTEGER DEFAULT 0,
    output_tokens     INTEGER DEFAULT 0,
    total_tokens      INTEGER DEFAULT 0,
    cost_estimate     DECIMAL(10, 5) DEFAULT 0,
    created_at        TIMESTAMPTZ DEFAULT NOW()
);

-- 9. Security Events (Prompt Injection Blocks, PII Redactions)
CREATE TABLE IF NOT EXISTS security_events (
    id                SERIAL PRIMARY KEY,
    event_type        VARCHAR(50) NOT NULL,
    tenant_id         VARCHAR(255) NOT NULL,
    request_id        VARCHAR(255),
    prompt_hash       VARCHAR(64),
    matched_patterns  TEXT,
    score             DECIMAL(5, 2),
    decision          VARCHAR(20) NOT NULL,
    redacted_types    TEXT,
    redaction_count   INTEGER DEFAULT 0,
    metadata_extra    TEXT,
    created_at        TIMESTAMPTZ DEFAULT NOW()
);

-- Seed Initial Data
INSERT INTO ai_services (service_id, model_name, provider_url, provider_type, description, service_type)
VALUES 
    ('ollama-llama3', 'llama3', 'http://host.docker.internal:11434/api/chat', 'ollama', 'Local Llama 3 Instance', 'on-prem')
ON CONFLICT (service_id) DO NOTHING;

INSERT INTO intent_routing (intent_name, service_id, taxonomy_version, created_by)
VALUES 
    ('general_chat', 'ollama-llama3', '1.0', 'admin'),
    ('code_generation', 'ollama-llama3', '1.0', 'admin'),
    ('summarization', 'ollama-llama3', '1.0', 'admin')
ON CONFLICT (intent_name) DO NOTHING;

INSERT INTO tenant_service_permissions (tenant_id, service_id, allowed, granted_by)
VALUES 
    ('tenant-a', 'ollama-llama3', TRUE, 'admin'),
    ('acme-corp', 'ollama-llama3', TRUE, 'admin'),
    ('globex', 'ollama-llama3', TRUE, 'admin')
ON CONFLICT DO NOTHING;
