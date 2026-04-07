-- Migration: Add service_type to ai_services
-- Date: 2026-04-06

-- 1. Add the column with a default value
ALTER TABLE ai_services ADD COLUMN IF NOT EXISTS service_type VARCHAR(50) DEFAULT 'on-prem';

-- 2. Update specific services to be 'cloud' (as requested)
UPDATE ai_services SET service_type = 'cloud' WHERE service_id = 'ollama_deep_seek_coder';

-- 3. Ensure other services are 'on-prem' (though already default)
UPDATE ai_services SET service_type = 'on-prem' WHERE service_id != 'ollama_deep_seek_coder';
