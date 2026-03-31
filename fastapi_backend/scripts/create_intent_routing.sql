-- Migration: Create intent_routing and intent_mapping_audit_logs tables
-- Date: 2026-03-27

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Update or recreate intent_routing table
DROP TABLE IF EXISTS intent_routing CASCADE;
CREATE TABLE intent_routing (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    intent_name VARCHAR UNIQUE NOT NULL,
    service_id VARCHAR NOT NULL REFERENCES ai_services(service_id),
    is_active BOOLEAN DEFAULT TRUE,
    taxonomy_version VARCHAR NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_by VARCHAR NOT NULL
);

CREATE INDEX idx_intent_routing_intent_name ON intent_routing(intent_name);

-- Create intent_mapping_audit_logs table
CREATE TABLE IF NOT EXISTS intent_mapping_audit_logs (
    id SERIAL PRIMARY KEY,
    action VARCHAR NOT NULL,
    performed_by VARCHAR NOT NULL,
    entity_id VARCHAR NOT NULL,
    old_value JSONB,
    new_value JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Trigger for updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_intent_routing_updated_at
BEFORE UPDATE ON intent_routing
FOR EACH ROW
EXECUTE PROCEDURE update_updated_at_column();

