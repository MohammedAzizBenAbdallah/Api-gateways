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

    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()

logger = logging.getLogger(__name__)

