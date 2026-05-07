"""Environment-driven settings for the intent classifier service."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    port: int = Field(default=3010, alias="PORT")
    redis_url: str = Field(default="redis://redis:6379/1", alias="REDIS_URL")
    taxonomy_path: str = Field(
        default="/app/intent_taxonomy/intent_labels_v1.yaml",
        alias="INTENT_TAXONOMY_PATH",
    )
    llm_base_url: str = Field(
        default="http://host.docker.internal:11434/api/chat",
        alias="LLM_BASE_URL",
    )
    llm_model: str = Field(default="llama3.2", alias="LLM_MODEL")
    llm_timeout_seconds: float = Field(default=8.0, alias="LLM_TIMEOUT_SECONDS")
    cache_ttl_seconds: int = Field(default=3600, alias="INTENT_CLASSIFIER_CACHE_TTL_SECONDS")
    cache_max_entries: int = Field(default=10_000, alias="INTENT_CLASSIFIER_LRU_MAX")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
