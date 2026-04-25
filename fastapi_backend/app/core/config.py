# app/core/config.py
"""Application settings using pydantic-settings BaseSettings."""

from __future__ import annotations

import logging
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven application settings."""

    database_url: str = Field(alias="PLATFORM_DB_URL")
    keycloak_url: str = Field(alias="KEYCLOAK_URL")
    keycloak_realm: str = Field(alias="KEYCLOAK_REALM")
    cors_origin: str = Field(alias="CORS_ORIGIN")
    kong_header_value: str = Field(default="true", alias="KONG_HEADER_VALUE")
    environment: str = Field(default="development", alias="ENVIRONMENT")
    policy_file_path: str = Field(default="policies.yaml", alias="POLICY_FILE_PATH")
    port: int = Field(default=3000, alias="PORT")
    redis_url: str = Field(default="redis://redis:6379/0", alias="REDIS_URL")
    quotas_file_path: str = Field(default="quotas.yaml", alias="QUOTAS_FILE_PATH")

    opa_enabled: bool = Field(default=True, alias="OPA_ENABLED")
    opa_url: str = Field(default="http://opa:8181", alias="OPA_URL")
    opa_policy_path: str = Field(
        default="/v1/data/orchestrator", alias="OPA_POLICY_PATH"
    )
    opa_data_path: str = Field(default="/v1/data/policies", alias="OPA_DATA_PATH")
    opa_timeout_seconds: float = Field(default=2.0, alias="OPA_TIMEOUT_SECONDS")

    # Reliability / consistency controls.
    # OPA_STRICT_SYNC: when true, a failed push of policies to OPA raises so the
    # caller (startup, admin reload, admin CRUD) surfaces the error instead of
    # silently leaving OPA on stale data.
    opa_strict_sync: bool = Field(default=True, alias="OPA_STRICT_SYNC")
    # OPA_ALLOW_LOCAL_FALLBACK: when true, runtime evaluation may fall back to
    # the embedded Python evaluator if OPA returns an error or is unreachable.
    # When false, runtime errors propagate as policy errors (fail-closed-friendly).
    opa_allow_local_fallback: bool = Field(
        default=True, alias="OPA_ALLOW_LOCAL_FALLBACK"
    )
    # OPA_FAIL_CLOSED: when true, a hash/version mismatch between the locally
    # cached policy set and the value pushed to OPA raises a PolicyEvaluationError
    # at runtime (fail-closed) instead of allowing potentially stale decisions.
    opa_fail_closed: bool = Field(default=False, alias="OPA_FAIL_CLOSED")

    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()

logger = logging.getLogger(__name__)

