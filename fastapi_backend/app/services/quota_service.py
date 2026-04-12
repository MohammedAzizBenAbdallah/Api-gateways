# app/services/quota_service.py
from __future__ import annotations
import logging
import yaml
import redis.asyncio as redis
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class QuotaService:
    """Handles professional tenant token governance via Redis."""

    def __init__(self, quotas_file: str, redis_url: str):
        self.quotas_file = quotas_file
        self.redis_url = redis_url
        self._quotas: Dict[str, Any] = {}
        self._load_quotas()
        self._redis = redis.from_url(redis_url, decode_responses=True)

    def _load_quotas(self):
        """Load quotas from the 'Source of Truth' YAML file."""
        try:
            with open(self.quotas_file, "r") as f:
                config = yaml.safe_load(f)
                self._quotas = {t["id"]: t for t in config.get("tenants", [])}
                self._default_quota = config.get("defaults", {"max_tokens": 10000})
            logger.info("Loaded quotas for %d tenants from %s", len(self._quotas), self.quotas_file)
        except Exception as exc:
            logger.error("Failed to load quotas from YAML: %s", exc)
            self._quotas = {}
            self._default_quota = {"max_tokens": 0}

    def get_tenant_config(self, tenant_id: str) -> Dict[str, Any]:
        """Get quota config for a tenant, falling back to defaults."""
        return self._quotas.get(tenant_id, self._default_quota)

    async def check_quota(self, tenant_id: str) -> bool:
        """
        Check if the tenant has sufficient token quota in Redis.
        Returns True if allowed, False if limit exceeded.
        """
        config = self.get_tenant_config(tenant_id)
        max_tokens = config.get("max_tokens", 0)
        
        if max_tokens <= 0:
            return False

        # Redis key format: quota:tenant:{tenant_id}:{date}
        today = datetime.utcnow().strftime("%Y-%m-%d")
        key = f"quota:tenant:{tenant_id}:{today}"
        
        current_usage = await self._redis.get(key)
        if current_usage is None:
            return True
            
        return int(current_usage) < max_tokens

    async def increment_usage(self, tenant_id: str, tokens: int):
        """Increment the daily token usage counter in Redis."""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        key = f"quota:tenant:{tenant_id}:{today}"
        
        # Increment and set TTL if new key
        pipe = self._redis.pipeline()
        pipe.incrby(key, tokens)
        pipe.expire(key, 86400 + 3600)  # 25 hours TTL
        await pipe.execute()
        
        logger.debug("Incremented token usage for %s by %d", tenant_id, tokens)

    async def get_quota_status(self, tenant_id: str) -> Dict[str, Any]:
        """Fetch current usage and max quota for a tenant."""
        config = self.get_tenant_config(tenant_id)
        max_tokens = config.get("max_tokens", 0)
        
        today = datetime.utcnow().strftime("%Y-%m-%d")
        key = f"quota:tenant:{tenant_id}:{today}"
        
        current_usage_raw = await self._redis.get(key)
        current_usage = int(current_usage_raw) if current_usage_raw else 0
        
        remaining = max(0, max_tokens - current_usage)
        percent_used = (current_usage / max_tokens * 100) if max_tokens > 0 else 100
        
        return {
            "tenant_id": tenant_id,
            "max_tokens": max_tokens,
            "used_tokens": current_usage,
            "remaining_tokens": remaining,
            "percent_used": round(percent_used, 2),
            "reset_period": config.get("reset_period", "daily")
        }
