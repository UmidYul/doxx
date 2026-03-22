from __future__ import annotations

"""Real CRM HTTP transport. When ``DEV_MODE`` + ``DEV_DRY_RUN_DISABLE_CRM_SEND`` are set,
use :func:`infrastructure.transports.factory.get_transport` — it selects
:class:`infrastructure.transports.dry_run.DryRunTransport` instead of this class (9B).
"""

import asyncio
import logging
from typing import Any
from urllib.parse import urljoin

import httpx
import orjson

from application.lifecycle.apply_result_classifier import (
    classify_batch_sync_response,
    classify_single_sync_response,
)
from config.settings import settings
from domain.crm_apply_result import CrmApplyResult, CrmBatchApplyResult, MalformedCrmBatchResponse
from domain.parser_event import ParserSyncEvent
from infrastructure.observability import message_codes as obs_mc
from infrastructure.observability.correlation import build_correlation_context
from infrastructure.observability.event_logger import log_sync_event
from infrastructure.security import security_logger as sec_log
from infrastructure.security.redaction import redact_exception_message, redact_headers, redact_mapping_for_logs
from infrastructure.security.request_signing import build_request_security_headers
from infrastructure.security.secret_loader import load_secret
from infrastructure.security.security_validator import (
    _parse_security_mode,
    validate_parser_key_length_after_load,
)
from infrastructure.security.startup_guard import run_startup_security_checks
from infrastructure.security import network_security_logger as net_log
from infrastructure.transports.base import BaseTransport
from infrastructure.security.outbound_policy import validate_outbound_url
from infrastructure.security.redirect_guard import can_follow_redirect

logger = logging.getLogger(__name__)


def _idempotency_headers_for(events: list[ParserSyncEvent]) -> dict[str, str]:
    if not settings.CRM_SEND_IDEMPOTENCY_KEY_HEADER or len(events) != 1:
        return {}
    key = (events[0].request_idempotency_key or "").strip()
    if not key:
        return {}
    return {"X-Idempotency-Key": key}


class CrmBusinessError(Exception):
    """Non-retryable CRM error (4xx except 429) after retry policy exhausted."""

    def __init__(self, status: int, body: str) -> None:
        self.status = status
        self.body = body
        super().__init__(f"CRM returned {status}: {body[:500]}")


def _apply_from_crm_business_error(event: ParserSyncEvent, exc: CrmBusinessError) -> CrmApplyResult:
    retryable = exc.status == 429 or exc.status >= 500
    st = "retryable_failure" if retryable else "rejected"
    if exc.status >= 500:
        st = "retryable_failure"
    return CrmApplyResult(
        event_id=event.event_id,
        entity_key=event.data.entity_key,
        payload_hash=event.data.payload_hash,
        success=False,
        status=st,
        http_status=exc.status,
        retryable=retryable,
        error_code=str(exc.status),
        error_message=exc.body[:500],
    )


class CrmHttpTransport(BaseTransport):
    """CRM HTTP transport: batch/single, transport retries, item-level apply classification."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._batch_supported: bool = True
        self._metrics: Any = None
        self._obs_run_id: str | None = None
        self._obs_store: str | None = None
        self._obs_batch_id: str | None = None
        self._obs_spider_name: str | None = None

    def attach_metrics(self, collector: object | None) -> None:
        self._metrics = collector

    def set_obs_batch_hint(
        self,
        *,
        run_id: str | None,
        store_name: str | None,
        batch_id: str | None,
        spider_name: str | None = None,
    ) -> None:
        self._obs_run_id = run_id
        self._obs_store = store_name
        self._obs_batch_id = batch_id
        self._obs_spider_name = spider_name

    def _emit_delivery_retry(self, details: dict[str, object]) -> None:
        rid = self._obs_run_id
        if not rid:
            return
        safe = dict(redact_mapping_for_logs(dict(details)))
        err = safe.get("error")
        if isinstance(err, str):
            safe["error"] = redact_exception_message(err)
        log_sync_event(
            "delivery_send",
            "warning",
            obs_mc.DELIVERY_RETRY,
            build_correlation_context(
                self._obs_spider_name or "crm_http",
                (self._obs_store or "").strip() or "*",
                run_id=rid,
                batch_id=self._obs_batch_id,
            ),
            details=safe,
            failure_domain="transport",
            failure_type="timeout",
        )

    async def _ensure_client(self) -> None:
        if self._client is not None:
            return

        res = run_startup_security_checks(settings)
        if not res.passed:
            raise RuntimeError("SECURITY: fix configuration before using CRM HTTP transport: " + "; ".join(res.errors))

        secret, desc = load_secret(
            settings.CRM_PARSER_KEY,
            (getattr(settings, "CRM_PARSER_KEY_FILE", "") or "").strip() or None,
            name="CRM_PARSER_KEY",
            enable_file_fallback=bool(getattr(settings, "ENABLE_SECRET_FILE_FALLBACK", True)),
        )
        mode = _parse_security_mode(getattr(settings, "SECURITY_MODE", "baseline"))
        e_post, w_post = validate_parser_key_length_after_load(secret, mode)
        for w in w_post:
            sec_log.emit_security_config_warning(message=w)
        if e_post:
            msg = "; ".join(e_post)
            for part in e_post:
                sec_log.emit_security_config_warning(message=part)
            if getattr(settings, "SECURITY_FAIL_FAST_ON_INVALID_CONFIG", True):
                raise RuntimeError(f"SECURITY: parser key rejected ({msg})")
        if not secret:
            raise RuntimeError("SECURITY: CRM_PARSER_KEY could not be resolved (env or file)")

        sec_log.emit_security_secret_loaded(
            secret_name="CRM_PARSER_KEY",
            secret_source=desc.source,
            configured=True,
        )

        base = (settings.CRM_BASE_URL or "").strip()
        if base:
            full = base if base.startswith(("http://", "https://")) else f"https://{base}"
            bd = validate_outbound_url(full, settings)
            if not bd.allowed:
                raise RuntimeError("NETWORK: CRM_BASE_URL failed outbound validation: " + (bd.reason or ""))
            if bd.target_type != "crm":
                raise RuntimeError("NETWORK: CRM_BASE_URL must resolve to an allowlisted CRM host")

        max_r = min(50, max(0, int(getattr(settings, "MAX_REDIRECT_HOPS", 5) or 5)))
        self._client = httpx.AsyncClient(
            base_url=settings.CRM_BASE_URL,
            timeout=httpx.Timeout(settings.CRM_HTTP_TIMEOUT_SECONDS),
            headers={
                "X-Parser-Key": secret,
                "Content-Type": "application/json",
            },
            follow_redirects=True,
            max_redirects=max_r,
        )

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    def _bump_transport_retry(self) -> None:
        if self._metrics is not None:
            self._metrics.transport_retries_total += 1

    def _absolute_crm_url(self, path_or_url: str) -> str:
        assert self._client is not None
        u = (path_or_url or "").strip()
        if u.startswith("http://") or u.startswith("https://"):
            return u
        base = str(self._client.base_url).rstrip("/")
        return urljoin(base + "/", u.lstrip("/"))

    def _validate_crm_http_response(self, request_path: str, resp: httpx.Response) -> None:
        """Ensure redirect chain and final URL stay on allowlisted CRM hosts."""
        initial = self._absolute_crm_url(request_path)
        prev = initial
        for h in resp.history:
            loc = h.headers.get("location")
            if not loc:
                continue
            ls = loc.decode() if isinstance(loc, bytes) else str(loc)
            from_u = str(h.request.url)
            nxt = urljoin(from_u, ls)
            dec = can_follow_redirect(prev, nxt, settings)
            if not dec.allowed:
                net_log.emit_redirect_blocked(
                    from_url=prev,
                    to_url=nxt,
                    reason=dec.reason,
                    redirect_hops=len(resp.history),
                    same_site=dec.same_site,
                )
                raise CrmBusinessError(400, f"redirect blocked: {dec.reason}")
            prev = nxt
        final_u = str(resp.url)
        if final_u != prev:
            dec = can_follow_redirect(prev, final_u, settings)
            if not dec.allowed:
                net_log.emit_redirect_blocked(
                    from_url=prev,
                    to_url=final_u,
                    reason=dec.reason,
                    redirect_hops=len(resp.history),
                    same_site=dec.same_site,
                )
                raise CrmBusinessError(400, f"redirect blocked: {dec.reason}")
        fin = validate_outbound_url(final_u, settings)
        if not fin.allowed or fin.target_type != "crm":
            net_log.emit_outbound_host_blocked(
                target_type=fin.target_type,
                url=final_u,
                host=fin.host,
                reason=fin.reason,
                matched_rule=fin.matched_rule,
            )
            raise CrmBusinessError(502, "CRM response host failed network policy")

    @staticmethod
    def _safe_parse_json(resp: httpx.Response) -> Any:
        try:
            return orjson.loads(resp.content)
        except Exception:
            return None

    async def send_one_event(self, event: ParserSyncEvent) -> CrmApplyResult:
        from infrastructure.performance.timing_profiler import finish_stage, start_stage

        await self._ensure_client()
        body = orjson.dumps(event.model_dump(mode="json"))
        sn = event.data.source_name
        tok_send = start_stage(
            "crm_send",
            store_name=sn,
            spider_name=self._obs_spider_name,
            batch_id=self._obs_batch_id,
        )
        try:
            try:
                resp = await self._request_with_retry("POST", settings.CRM_SYNC_ENDPOINT, body)
            finally:
                finish_stage(tok_send)
            parsed = self._safe_parse_json(resp)
            as_dict: dict[str, Any] | None
            if isinstance(parsed, dict):
                as_dict = parsed
            elif isinstance(parsed, list):
                as_dict = {"results": parsed}
            else:
                as_dict = None
            tok_cls = start_stage(
                "crm_apply_parse",
                store_name=sn,
                spider_name=self._obs_spider_name,
                batch_id=self._obs_batch_id,
            )
            try:
                return classify_single_sync_response(event, resp.status_code, as_dict)
            except CrmBusinessError as exc:
                return _apply_from_crm_business_error(event, exc)
            finally:
                finish_stage(tok_cls)
        except CrmBusinessError as exc:
            return _apply_from_crm_business_error(event, exc)

    async def _retry_retryable_items_in_batch(
        self,
        events: list[ParserSyncEvent],
        batch_res: CrmBatchApplyResult,
    ) -> CrmBatchApplyResult:
        if not settings.CRM_BATCH_RETRY_ONLY_RETRYABLE_ITEMS:
            return batch_res
        new_items = list(batch_res.items)
        for i, (ev, ar) in enumerate(zip(events, batch_res.items)):
            if ar.success or not ar.retryable:
                continue
            new_items[i] = await self.send_one_event(ev)
        return batch_res.model_copy(update={"items": new_items})

    async def send_batch_events(self, events: list[ParserSyncEvent]) -> CrmBatchApplyResult:
        if not events:
            return CrmBatchApplyResult(items=[], transport_ok=True, http_status=None)

        if not self._batch_supported:
            items = [await self.send_one_event(e) for e in events]
            return await self._retry_retryable_items_in_batch(
                events,
                CrmBatchApplyResult(
                    items=items,
                    transport_ok=all(i.success for i in items),
                    http_status=items[-1].http_status if items else None,
                ),
            )

        await self._ensure_client()
        body = orjson.dumps([e.model_dump(mode="json") for e in events])
        sn = events[0].data.source_name
        from infrastructure.performance.timing_profiler import finish_stage, start_stage

        tok_send = start_stage(
            "crm_send",
            store_name=sn,
            spider_name=self._obs_spider_name,
            batch_id=self._obs_batch_id,
        )
        try:
            try:
                resp = await self._request_with_retry(
                    "POST",
                    settings.CRM_SYNC_BATCH_ENDPOINT,
                    body,
                    extra_headers=_idempotency_headers_for(events),
                )
            finally:
                finish_stage(tok_send)
            parsed = self._safe_parse_json(resp)
            tok_cls = start_stage(
                "crm_apply_parse",
                store_name=sn,
                spider_name=self._obs_spider_name,
                batch_id=self._obs_batch_id,
            )
            try:
                batch_res = classify_batch_sync_response(events, resp.status_code, parsed)
            finally:
                finish_stage(tok_cls)
            return await self._retry_retryable_items_in_batch(events, batch_res)
        except MalformedCrmBatchResponse:
            raise
        except CrmBusinessError as exc:
            if exc.status in (404, 501):
                logger.warning(
                    "CRM batch endpoint returned %d — falling back to per-item sync",
                    exc.status,
                )
                self._batch_supported = False
                items = [await self.send_one_event(e) for e in events]
                return await self._retry_retryable_items_in_batch(
                    events,
                    CrmBatchApplyResult(
                        items=items,
                        transport_ok=all(i.success for i in items),
                        http_status=exc.status,
                        batch_error_code=str(exc.status),
                        batch_error_message=exc.body[:300],
                    ),
                )
            retryable = exc.status == 429 or exc.status >= 500
            st = "retryable_failure" if retryable else "rejected"
            if exc.status >= 500:
                st = "retryable_failure"
            items = [
                CrmApplyResult(
                    event_id=e.event_id,
                    entity_key=e.data.entity_key,
                    payload_hash=e.data.payload_hash,
                    success=False,
                    status=st,
                    http_status=exc.status,
                    retryable=retryable,
                    error_code=str(exc.status),
                    error_message=exc.body[:300],
                )
                for e in events
            ]
            return CrmBatchApplyResult(
                items=items,
                transport_ok=False,
                http_status=exc.status,
                batch_error_code=str(exc.status),
                batch_error_message=exc.body[:300],
            )

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        body: bytes,
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        assert self._client is not None
        max_attempts = settings.CRM_HTTP_RETRY_ATTEMPTS + 1
        backoff = settings.CRM_HTTP_RETRY_BACKOFF_SECONDS
        last_exc: Exception | None = None
        req_headers = dict(extra_headers or {})

        for attempt in range(max_attempts):
            try:
                sign_headers = build_request_security_headers(method, url, body, settings)
                merged_headers = {**sign_headers, **req_headers}
                signed = bool(sign_headers)
                if signed:
                    integrity_mode = (getattr(settings, "CRM_REQUEST_INTEGRITY_MODE", "none") or "none").strip().lower()
                    sec_log.emit_security_request_signed(integrity_mode=integrity_mode, signed=True)

                if logger.isEnabledFor(logging.DEBUG):
                    dbg = redact_headers({str(k): v for k, v in merged_headers.items()})
                    logger.debug(
                        "CRM HTTP %s %s signing=%s header_keys=%s",
                        method,
                        url,
                        signed,
                        list(dbg.keys()),
                    )

                resp = await self._client.request(
                    method, url, content=body, headers=merged_headers or None
                )

                if resp.status_code < 400:
                    self._validate_crm_http_response(url, resp)
                    return resp

                if resp.status_code == 429:
                    retry_after = float(resp.headers.get("Retry-After", str(backoff)))
                    if attempt < max_attempts - 1:
                        self._bump_transport_retry()
                        self._emit_delivery_retry(
                            {
                                "http_status": 429,
                                "attempt": attempt + 1,
                                "max_attempts": max_attempts,
                                "kind": "rate_limit",
                            }
                        )
                        logger.warning(
                            "CRM 429 rate-limited, retry %d/%d after %.1fs",
                            attempt + 1,
                            max_attempts - 1,
                            retry_after,
                            extra={
                                "attempt": attempt + 1,
                                "http_status": 429,
                                "result": "retry",
                            },
                        )
                        await asyncio.sleep(retry_after)
                        continue
                    raise CrmBusinessError(429, resp.text)

                if resp.status_code >= 500:
                    if attempt < max_attempts - 1:
                        wait = backoff * (2**attempt)
                        self._bump_transport_retry()
                        self._emit_delivery_retry(
                            {
                                "http_status": resp.status_code,
                                "attempt": attempt + 1,
                                "max_attempts": max_attempts,
                                "kind": "server_error",
                            }
                        )
                        logger.warning(
                            "CRM %d server error, retry %d/%d after %.1fs",
                            resp.status_code,
                            attempt + 1,
                            max_attempts - 1,
                            wait,
                            extra={
                                "attempt": attempt + 1,
                                "http_status": resp.status_code,
                                "result": "retry",
                            },
                        )
                        await asyncio.sleep(wait)
                        continue
                    raise CrmBusinessError(resp.status_code, resp.text)

                raise CrmBusinessError(resp.status_code, resp.text)

            except httpx.TransportError as exc:
                last_exc = exc
                if attempt < max_attempts - 1:
                    wait = backoff * (2**attempt)
                    self._bump_transport_retry()
                    self._emit_delivery_retry(
                        {
                            "attempt": attempt + 1,
                            "max_attempts": max_attempts,
                            "kind": "transport_error",
                            "error": str(exc)[:300],
                        }
                    )
                    logger.warning(
                        "CRM transport error: %s, retry %d/%d after %.1fs",
                        exc,
                        attempt + 1,
                        max_attempts - 1,
                        wait,
                        extra={"attempt": attempt + 1, "result": "transport_retry"},
                    )
                    await asyncio.sleep(wait)
                    continue
                raise

        raise last_exc  # type: ignore[misc]
