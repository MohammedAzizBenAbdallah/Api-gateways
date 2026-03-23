-- Schema for Tenant Service Permissions and AI Orchestrator

CREATE TABLE IF NOT EXISTS tenant_service_permissions (
    tenant_id VARCHAR(255) NOT NULL,
    service_id VARCHAR(255) NOT NULL,
    allowed BOOLEAN DEFAULT TRUE,
    granted_by VARCHAR(255),
    granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, service_id)
);

CREATE TABLE IF NOT EXISTS ai_services (
    service_id VARCHAR(255) PRIMARY KEY,
    model_name VARCHAR(255) NOT NULL,
    provider_url TEXT NOT NULL,
    provider_type VARCHAR(50) DEFAULT 'ollama', -- 'ollama', 'openai', etc.
    description TEXT
);

CREATE TABLE IF NOT EXISTS permission_audit_logs (
    id SERIAL PRIMARY KEY,
    tenant_id VARCHAR(255),
    service_id VARCHAR(255),
    action VARCHAR(50), -- 'GRANT', 'REVOKE', 'DENY', 'ALLOW'
    performed_by VARCHAR(255),
    performed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reason TEXT,
    intent VARCHAR(255)  -- unified endpoint: tracks which intent triggered this log
);

-- Intent-based routing table: maps logical intents to concrete AI services
CREATE TABLE IF NOT EXISTS intent_routing (
    intent      VARCHAR(255) PRIMARY KEY,
    service_id  VARCHAR(255) NOT NULL REFERENCES ai_services(service_id),
    description TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Initial Seed Data
INSERT INTO ai_services (service_id, model_name, provider_url, provider_type, description) VALUES
('ollama_deep_seek_coder', 'deepseek-coder:latest','http://host.docker.internal:11434/api/chat', 'ollama', 'Local Ollama Instance'),
('ollama_llama3.2', 'llama3.2','http://host.docker.internal:11434/api/chat', 'ollama', 'Local Ollama Instance');


-- Acme Corp has access to Ollama but NOT DeepSeek Cloud initially
INSERT INTO tenant_service_permissions (tenant_id, service_id, allowed, granted_by) VALUES
('acme-corp', 'ollama_deep_seek_coder', true, 'admin'),
('acme-corp', 'ollama_llama3.2', false, 'admin');

-- Globex has access to both
INSERT INTO tenant_service_permissions (tenant_id, service_id, allowed, granted_by) VALUES
('globex', 'ollama_deep_seek_coder', true, 'admin'),
('globex', 'ollama_llama3.2', true, 'admin');

-- Intent routing seed data
INSERT INTO intent_routing (intent, service_id, description) VALUES
('code_generation', 'ollama_deep_seek_coder', 'Routes code-related prompts to DeepSeek Coder'),
('general_chat',    'ollama_llama3.2',        'Routes general conversation to Llama 3.2'),
('summarization',   'ollama_llama3.2',        'Routes summarization tasks to Llama 3.2')
ON CONFLICT DO NOTHING;

-- Request tracking table — lifecycle: received → streaming → completed / failed
CREATE TABLE IF NOT EXISTS ai_requests (
    request_id          VARCHAR(255) PRIMARY KEY,
    tenant_id           VARCHAR(255) NOT NULL,
    intent              VARCHAR(255) NOT NULL,
    resolved_service_id VARCHAR(255) REFERENCES ai_services(service_id),
    sensitivity         VARCHAR(10)  NOT NULL DEFAULT 'LOW',
    environment         VARCHAR(10)  NOT NULL DEFAULT 'dev',
    status              VARCHAR(20)  NOT NULL DEFAULT 'received',
    started_at          TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at        TIMESTAMP,
    error_detail        TEXT
);

CREATE INDEX IF NOT EXISTS idx_ai_requests_tenant_id  ON ai_requests(tenant_id);
CREATE INDEX IF NOT EXISTS idx_ai_requests_started_at ON ai_requests(started_at);

