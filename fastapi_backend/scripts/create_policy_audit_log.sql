-- scripts/create_policy_audit_log.sql
-- Create the policy_evaluation_audit_logs table for persistent governance tracking.

CREATE TABLE IF NOT EXISTS policy_evaluation_audit_logs (
    id SERIAL PRIMARY KEY,
    request_id VARCHAR(255) NOT NULL, -- References ai_requests.request_id
    policy_id VARCHAR(255) NOT NULL,
    effect VARCHAR(50) NOT NULL,      -- allow_onprem_only, deny_cloud, etc.
    decision VARCHAR(50) NOT NULL,    -- ALLOW, DENY, SKIP
    context JSONB,                    -- JSON snapshot of context (sensitivity, tenant, etc.)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Add index for faster auditing by request
CREATE INDEX IF NOT EXISTS idx_policy_audit_request_id ON policy_evaluation_audit_logs(request_id);
