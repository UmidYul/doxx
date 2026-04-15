from __future__ import annotations

import json
import logging

from config.settings import settings
from infrastructure.access.access_metrics import access_metrics
from infrastructure.access.header_profiles import build_desktop_headers
from infrastructure.security import network_security_logger as net_log
from infrastructure.security.redirect_guard import can_follow_redirect

logger = logging.getLogger(__name__)


def _log(event: str, **fields) -> None:
    payload = {k: v for k, v in fields.items() if v is not None}
    logger.info("access_layer %s", json.dumps({"event": event, **payload}, default=str, ensure_ascii=False))


class MobileRedirectMiddleware:
    """One-shot desktop retry when origin redirects to ``m.`` host (uses header profile layer)."""

    @classmethod
    def from_crawler(cls, crawler):
        return cls()

    def process_response(self, request, response, spider):
        response_host = response.url.split("/")[2] if "/" in response.url else ""
        request_host = request.url.split("/")[2] if "/" in request.url else ""

        if response_host.startswith("m.") and not request_host.startswith("m."):
            if request.meta.get("_mobile_retry"):
                return response

            store = str(request.meta.get("store_name") or getattr(spider, "store_name", "") or spider.name)
            rd = can_follow_redirect(request.url, response.url, settings)
            if not rd.allowed:
                net_log.emit_redirect_blocked(
                    from_url=request.url,
                    to_url=response.url,
                    reason=rd.reason,
                    redirect_hops=1,
                    same_site=rd.same_site,
                    store_name=store,
                )
                logger.warning(
                    "[MOBILE_REDIRECT] blocked by network policy: %s → %s (%s)",
                    request.url,
                    response.url,
                    rd.reason,
                )
                return response
            net_log.emit_redirect_allowed(
                from_url=request.url,
                to_url=response.url,
                same_site=rd.same_site,
                store_name=store,
            )
            purpose = str(request.meta.get("access_purpose") or "listing")
            access_metrics.bump("mobile_redirect_hits_total")
            _log(
                "MOBILE_REDIRECT_RETRY",
                spider=spider.name,
                store=store,
                purpose=purpose,
                url=request.url,
                detected_signal="mobile_redirect",
                mode=request.meta.get("access_mode_selected"),
                retry_count=request.meta.get("prior_failures", 0),
                reason="desktop_replay",
            )
            logger.warning(
                "[MOBILE_REDIRECT] %s → %s, retrying with desktop header profile",
                request.url,
                response.url,
            )
            new_request = request.copy()
            referer = request.meta.get("from_listing") or request.meta.get("access_referer")
            headers = build_desktop_headers(
                store,
                purpose,
                referer=referer,
                request_url=new_request.url,
            )
            for k, v in headers.items():
                new_request.headers[k] = v
            new_request.meta["_mobile_retry"] = True
            new_request.dont_filter = True
            return new_request

        return response
