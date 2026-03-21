from __future__ import annotations

import hashlib
import json
import logging

from application.extractors.unit_normalizer import normalize_field_value

logger = logging.getLogger(__name__)

_EXCLUDED_META = frozenset({"extraction_method", "completeness_score", "raw_fields"})


class LLMExtractor:
    """Last-resort enrichment via Claude Haiku with Redis caching."""

    def __init__(self) -> None:
        from config.settings import settings

        self.enabled: bool = settings.LLM_EXTRACTION_ENABLED
        self.cache_ttl: int = settings.LLM_CACHE_TTL_DAYS * 86400
        self.api_key: str = settings.ANTHROPIC_API_KEY
        self.redis_url: str = settings.REDIS_URL

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def enrich(
        self,
        specs: object,
        text: str,
        schema_class: type,
    ) -> object:
        if not self.enabled or not self.api_key:
            return specs

        cache_key = self._cache_key(schema_class.__name__, text)

        try:
            cached = await self._get_cache(cache_key)
            if cached is not None:
                logger.info("[LLM_CACHE_HIT] %s", cache_key[:16])
                return self._merge_result(specs, cached, schema_class)
        except Exception:
            logger.debug("Redis cache unavailable for LLM extractor")

        try:
            import anthropic

            client = anthropic.AsyncAnthropic(api_key=self.api_key)

            schema_fields = sorted(
                set(schema_class.model_fields.keys()) - _EXCLUDED_META
            )
            prompt = (
                "Extract tech product specifications from the text below.\n"
                "Return ONLY a valid JSON object with field names as keys "
                "and extracted raw values.\n"
                "Only include fields you can confidently extract. "
                "Omit uncertain fields.\n\n"
                f"Fields to extract: {', '.join(schema_fields)}\n\n"
                f"Text:\n{text[:2000]}\n\n"
                "Return ONLY valid JSON. No markdown fences, no explanation."
            )

            message = await client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=512,
                temperature=0,
                messages=[{"role": "user", "content": prompt}],
            )

            result_text = message.content[0].text
            result: dict = json.loads(result_text)

            try:
                await self._set_cache(cache_key, result)
            except Exception:
                logger.debug("Failed to write LLM result to Redis cache")

            logger.info("[LLM_EXTRACTION] Got %d fields", len(result))
            return self._merge_result(specs, result, schema_class)

        except Exception:
            logger.exception("[LLM_EXTRACTION] Failed, returning original specs")
            return specs

    # ------------------------------------------------------------------
    # Caching
    # ------------------------------------------------------------------

    @staticmethod
    def _cache_key(schema_name: str, text: str) -> str:
        content = f"{schema_name}:{text[:500]}"
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    async def _get_cache(self, key: str) -> dict | None:
        import redis.asyncio as aioredis

        r = aioredis.from_url(self.redis_url, decode_responses=True)
        try:
            data = await r.get(f"llm_cache:{key}")
            if data:
                return json.loads(data)
            return None
        finally:
            await r.aclose()

    async def _set_cache(self, key: str, value: dict) -> None:
        import redis.asyncio as aioredis

        r = aioredis.from_url(self.redis_url, decode_responses=True)
        try:
            await r.setex(
                f"llm_cache:{key}",
                self.cache_ttl,
                json.dumps(value, ensure_ascii=False),
            )
        finally:
            await r.aclose()

    # ------------------------------------------------------------------
    # Merge
    # ------------------------------------------------------------------

    @staticmethod
    def _merge_result(
        specs: object,
        result: dict,
        schema_class: type,
    ) -> object:
        schema_fields = set(schema_class.model_fields.keys()) - _EXCLUDED_META
        for field, value in result.items():
            if field not in schema_fields:
                continue
            if getattr(specs, field, None) is not None:
                continue
            normalized = normalize_field_value(field, str(value))
            if normalized is not None:
                setattr(specs, field, normalized)

        if specs.extraction_method == "unknown":  # type: ignore[attr-defined]
            specs.extraction_method = "llm"  # type: ignore[attr-defined]
        specs.compute_score()  # type: ignore[attr-defined]
        return specs
