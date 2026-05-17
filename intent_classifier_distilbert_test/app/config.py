"""Environment-driven settings for the DistilBERT test classifier."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    port: int = Field(default=3011, alias="PORT")
    redis_url: str = Field(default="", alias="REDIS_URL")
    redis_enabled: bool = Field(default=False, alias="REDIS_ENABLED")
    taxonomy_path: str = Field(
        default="../intent_taxonomy/intent_labels_v1.yaml",
        alias="INTENT_TAXONOMY_PATH",
    )
    hf_zero_shot_model: str = Field(
        default="typeform/distilbert-base-uncased-mnli",
        alias="HF_ZERO_SHOT_MODEL",
    )
    cache_ttl_seconds: int = Field(default=3600, alias="INTENT_CLASSIFIER_CACHE_TTL_SECONDS")
    cache_max_entries: int = Field(default=10_000, alias="INTENT_CLASSIFIER_LRU_MAX")
    hypothesis_template: str = Field(
        default="This is related to {}.",
        alias="HYPOTHESIS_TEMPLATE",
    )
    confidence_threshold: float = Field(
        default=0.30,
        alias="INTENT_CONFIDENCE_THRESHOLD",
        description="NLI scores are lower than LLM; default 0.30 vs taxonomy 0.32",
    )

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
