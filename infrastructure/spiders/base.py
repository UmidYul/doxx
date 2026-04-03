from __future__ import annotations

import hashlib
import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Iterator, Literal
from urllib.parse import urlparse

import scrapy
import scrapy.http

from config.settings import settings
from domain.raw_product import as_scrapy_item_dict
from infrastructure.access import ban_detector
from infrastructure.access.store_profiles import get_store_profile
from infrastructure.spiders import edge_cases
from infrastructure.spiders.field_policy import (
    is_partial_product_item,
    is_usable_product_item,
    missing_recommended_fields,
    missing_required_fields,
)
from infrastructure.spiders.runtime_crawl_registry import CrawlRuntimeRegistry
from infrastructure.spiders.qa_report import build_store_qa_report, crawl_snapshot_to_qa_metrics
from infrastructure.spiders.store_acceptance import get_store_acceptance_profile
from infrastructure.spiders.url_tools import canonicalize_url, canonicalize_product_url as default_canonicalize_product

logger = logging.getLogger(__name__)

SoftStatus = Literal["ok", "partial", "drop"]


class BaseProductSpider(scrapy.Spider, ABC):
    """Framework spider: category → listing pages → PDP, crawl-layer dedupe, pagination guards."""

    store_name: str = ""

    custom_settings = {
        "DOWNLOAD_DELAY": 1.0,
    }

    _crawl_registry_ref: CrawlRuntimeRegistry | None = None

    # --- StoreSpiderContract ---
    @abstractmethod
    def start_category_urls(self) -> list[str] | tuple[str, ...]:
        """Entry listing/category URLs for this store."""

    # --- ListingTraversalContract ---
    @abstractmethod
    def is_product_page(self, response: scrapy.http.Response) -> bool:
        """True if response is a product detail page."""

    @abstractmethod
    def extract_listing_product_urls(self, response: scrapy.http.Response) -> list[str]:
        """Product URLs (relative or absolute) from a listing page."""

    @abstractmethod
    def extract_next_page_url(self, response: scrapy.http.Response) -> str | None:
        """Next listing page URL, or None."""

    def extract_listing_category_urls(self, response: scrapy.http.Response) -> list[str]:
        """Optional subcategory/listing URLs discovered on a listing page."""
        return []

    # --- ProductExtractionContract ---
    def canonicalize_product_url(self, url: str) -> str:
        """Override per store if path/query rules differ."""
        return default_canonicalize_product(url)

    @abstractmethod
    def extract_source_id_from_url(self, url: str) -> str | None:
        """Stable id from PDP URL when payload lacks source_id."""

    def extract_category_hint(
        self,
        response_or_url: scrapy.http.Response | str,
        title: str | None = None,
    ) -> str | None:
        """Override to set spider-level category hints (not raw_specs)."""
        return None

    @abstractmethod
    def full_parse_item(self, response: scrapy.http.Response) -> dict[str, Any] | None:
        """Parse PDP into a dict for :func:`as_scrapy_item_dict`."""

    def request_meta_extra(self) -> dict[str, Any]:
        """Merged into every Request meta (e.g. ``playwright: True`` for Uzum)."""
        return {}

    @property
    def crawl_registry(self) -> CrawlRuntimeRegistry:
        if self._crawl_registry_ref is None:
            self._crawl_registry_ref = CrawlRuntimeRegistry(store=self.store_name or self.name)
        return self._crawl_registry_ref

    def _crawl_event(self, event: str, **fields: Any) -> None:
        payload = {"event": event, "spider": self.name, **{k: v for k, v in fields.items() if v is not None}}
        logger.info("crawl_framework %s", json.dumps(payload, default=str, ensure_ascii=False))

    def open_spider(self) -> None:
        """Anchor one scrape run id for crawl correlation and scraper DB persistence."""
        from infrastructure.observability.correlation import build_run_id

        self._parser_run_id = build_run_id(self.name)
        self._scrape_run_id = self._parser_run_id

    def _obs_corr_crawl(self, **kwargs: Any):
        from infrastructure.observability.correlation import build_correlation_context

        return build_correlation_context(
            self.name,
            self.store_name or self.name,
            run_id=getattr(self, "_parser_run_id", None),
            **kwargs,
        )

    def _supports_playwright(self) -> bool:
        s = getattr(self, "settings", None)
        if s is None:
            return False
        h = s.get("DOWNLOAD_HANDLERS") or {}
        v = str(h.get("https") or h.get("http") or "")
        return "playwright" in v.lower()

    def schedule_safe_request(
        self,
        url: str,
        *,
        callback,
        meta: dict[str, Any] | None = None,
        purpose: str = "listing",
        priority: int = 0,
    ) -> scrapy.Request | None:
        from infrastructure.access.header_profiles import build_desktop_headers
        from infrastructure.access.request_strategy import build_request_meta
        from infrastructure.security import network_security_logger as net_log
        from infrastructure.security.browser_navigation_guard import can_open_new_page
        from infrastructure.security.outbound_policy import validate_store_crawl_url
        from infrastructure.security.ssrf_guard import reject_if_suspicious_url

        m: dict[str, Any] = dict(meta or {})
        store = self.store_name or self.name
        if reject_if_suspicious_url(url):
            net_log.emit_ssrf_guard_blocked(url=url, reason="suspicious_or_malformed", store_name=store)
            self._crawl_event("NETWORK_URL_BLOCKED", url=url, reason="ssrf_suspicious")
            return None
        st = validate_store_crawl_url(url, store, settings)
        if not st.allowed:
            net_log.emit_outbound_host_blocked(
                target_type=st.target_type,
                url=url,
                host=st.host,
                reason=st.reason,
                matched_rule=st.matched_rule,
                store_name=store,
            )
            self._crawl_event("NETWORK_URL_BLOCKED", url=url, reason=st.reason or "outbound_policy")
            return None
        parent = m.get("from_listing") or m.get("access_referer")
        parent_s = str(parent) if isinstance(parent, str) else None
        nav = can_open_new_page(url, parent_s, settings)
        if not nav.allowed:
            net_log.emit_browser_nav_blocked(url=url, reason=nav.reason, store_name=store)
            self._crawl_event("NETWORK_URL_BLOCKED", url=url, reason=nav.reason or "browser_nav")
            return None
        prior = int(m.get("prior_failures", 0))
        access_part = build_request_meta(
            store_name=store,
            purpose=purpose,
            prior_failures=prior,
            force_browser=bool(m.get("force_browser", False)),
            force_proxy=bool(m.get("force_proxy", False)),
            detected_signal=m.get("access_last_signal"),
            spider_supports_browser=self._supports_playwright(),
            target_url=url,
        )
        m.update(access_part)
        m.update(self.request_meta_extra())
        from infrastructure.access.resource_governance import (
            apply_governance_to_request_meta,
            record_request_scheduled_governance,
        )

        m, admitted = apply_governance_to_request_meta(store, purpose, m)
        if not admitted:
            self._crawl_event("RESOURCE_GOVERNANCE_BLOCKED", url=url, purpose=purpose)
            return None
        record_request_scheduled_governance(store, purpose, m)
        referer = m.get("from_listing") or m.get("access_referer")
        headers = build_desktop_headers(store, purpose, referer=referer)
        return scrapy.Request(
            url,
            callback=callback,
            errback=self.errback_default,
            meta=m,
            headers=headers,
            priority=priority,
        )

    def start_requests(self) -> Iterator[scrapy.Request]:
        for url in self.start_category_urls():
            self.crawl_registry.categories_started_total += 1
            self._crawl_event("CATEGORY_START", category_url=url, page=1)
            req = self.schedule_safe_request(
                url,
                callback=self.parse,
                purpose="listing",
                meta={
                    "category_url": url,
                    "page": 1,
                    "empty_streak": 0,
                    "dup_sig_streak": 0,
                },
            )
            if req is not None:
                yield req

    def parse(self, response: scrapy.http.Response):
        from domain.performance import StageTimingRecord, utcnow
        from infrastructure.access.resource_governance import release_request_governance_counters
        from infrastructure.performance.perf_collector import increment_counter
        from infrastructure.performance.timing_profiler import record_timing
        from infrastructure.security.download_guard import should_download_response
        from infrastructure.security import network_security_logger as net_log

        store = self.store_name or self.name
        release_request_governance_counters(dict(response.meta or {}), store)
        increment_counter("requests", 1, store_name=store)
        elapsed = getattr(response, "elapsed", None)
        if elapsed is not None and getattr(settings, "ENABLE_PERFORMANCE_PROFILING", True):
            ms = elapsed.total_seconds() * 1000.0
            record_timing(
                StageTimingRecord(
                    stage="crawl_request",
                    started_at=utcnow(),
                    finished_at=utcnow(),
                    duration_ms=ms,
                    store_name=store,
                    spider_name=self.name,
                )
            )

        if not should_download_response(response):
            net_log.emit_download_guard_blocked(
                url=response.url,
                reason="unexpected_content_type_or_attachment",
                store_name=self.store_name or self.name,
            )
            self._crawl_event("DOWNLOAD_GUARD_BLOCKED", url=response.url)
            return
        if self.is_product_page(response):
            yield from self.parse_product(response)
            return
        yield from self.parse_listing(response)

    def build_listing_signature(
        self,
        response: scrapy.http.Response,
        canonical_product_urls: list[str],
        page: int,
    ) -> str:
        n = settings.SCRAPY_LISTING_SIGNATURE_N
        head = sorted(canonical_product_urls[:n])
        path = urlparse(response.url).path or ""
        blob = {
            "path": path,
            "page": page,
            "head_urls": head,
            "total_links": len(canonical_product_urls),
        }
        return hashlib.sha256(
            json.dumps(blob, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def should_skip_product_url(self, canonical_url: str) -> bool:
        reg = self.crawl_registry
        if reg.has_product_url(canonical_url):
            return True
        sid = self.extract_source_id_from_url(canonical_url)
        if sid and reg.has_source_id(sid):
            return True
        return False

    def should_stop_pagination(
        self,
        *,
        next_url: str | None,
        page: int,
        empty_streak: int,
        dup_sig_streak: int,
    ) -> tuple[bool, str]:
        if not next_url:
            return True, "no_next_url"
        if page >= settings.SCRAPY_MAX_PAGES_PER_CATEGORY:
            return True, "max_pages"
        if empty_streak >= settings.SCRAPY_MAX_EMPTY_LISTING_REPEATS:
            return True, "empty_repeats"
        if dup_sig_streak >= settings.SCRAPY_MAX_DUPLICATE_LISTING_REPEATS:
            return True, "duplicate_listing_repeats"
        return False, ""

    def log_empty_listing_page(
        self,
        response: scrapy.http.Response,
        *,
        category_url: str,
        page: int,
        extracted_count: int,
    ) -> None:
        self._crawl_event(
            "LISTING_PAGE",
            category_url=category_url,
            page=page,
            extracted_count=extracted_count,
            canonical_url=canonicalize_url(response.url),
            reason="zero_products" if extracted_count == 0 else None,
        )

    def parse_listing(self, response: scrapy.http.Response) -> Iterator[scrapy.Request]:
        from infrastructure.performance.timing_profiler import timed_stage

        store_key = self.store_name or self.name
        with timed_stage(
            "listing_parse",
            store_name=store_key,
            spider_name=self.name,
        ):
            yield from self._parse_listing_inner(response)

    def _parse_listing_inner(self, response: scrapy.http.Response) -> Iterator[scrapy.Request]:
        reg = self.crawl_registry
        meta = response.meta
        category_url = str(meta.get("category_url") or response.url)
        page = int(meta.get("page") or 1)

        listing_canon = canonicalize_url(response.url)
        reg.remember_listing_page_url(listing_canon)
        reg.listing_pages_seen_total += 1

        raw_urls = self.extract_listing_product_urls(response)
        raw_category_urls = self.extract_listing_category_urls(response)

        from infrastructure.observability import message_codes as obs_mc
        from infrastructure.observability.event_logger import log_sync_event

        log_sync_event(
            "crawl",
            "info",
            obs_mc.CRAWL_LISTING_SEEN,
            self._obs_corr_crawl(category_url=category_url, source_url=listing_canon),
            metrics={"page": page, "product_links": len(raw_urls)},
        )
        abs_urls = [response.urljoin(u.strip()) for u in raw_urls if u and str(u).strip()]
        abs_category_urls = [
            response.urljoin(u.strip()) for u in raw_category_urls if u and str(u).strip()
        ]
        canon_products = [self.canonicalize_product_url(u) for u in abs_urls]

        sig = self.build_listing_signature(response, canon_products, page)

        listing_sig_duplicate = reg.has_listing_signature(sig)
        if listing_sig_duplicate:
            reg.listing_pages_duplicated_total += 1
            dup_sig_streak = int(meta.get("dup_sig_streak") or 0) + 1
            self._crawl_event(
                "LISTING_DUPLICATE",
                category_url=category_url,
                page=page,
                listing_signature=sig,
                extracted_count=len(canon_products),
                canonical_url=listing_canon,
            )
        else:
            reg.remember_listing_signature(sig)
            dup_sig_streak = 0

        store_key = self.store_name or self.name
        access_prof = get_store_profile(store_key)
        ban_sig = ban_detector.detect_ban_signal(
            response,
            request=response.request,
            empty_body_threshold=access_prof.empty_body_threshold,
        )
        if ban_sig:
            reg.note_banned_response()
            from infrastructure.observability.event_logger import log_sync_event
            from infrastructure.observability import message_codes as obs_mc
            from infrastructure.observability.metrics_collector import (
                BLOCK_PAGES_TOTAL,
                get_observability_metrics,
            )

            get_observability_metrics().inc(BLOCK_PAGES_TOTAL)
            log_sync_event(
                "crawl",
                "warning",
                obs_mc.CRAWL_FAILURE,
                self._obs_corr_crawl(category_url=category_url, source_url=listing_canon),
                details={"ban_signal": ban_sig, "kind": "listing"},
                failure_domain="anti_bot",
                failure_type="block_page",
            )

        acc_prof = get_store_acceptance_profile(store_key)
        le_tags = edge_cases.classify_listing_edge_case(
            response,
            abs_urls,
            empty_body_threshold=access_prof.empty_body_threshold,
            listing_signature_duplicate=listing_sig_duplicate,
            pagination_exhausted_suspect=(
                dup_sig_streak >= settings.SCRAPY_MAX_DUPLICATE_LISTING_REPEATS
            ),
        )
        reg.note_edge_cases(le_tags)
        for t in le_tags:
            self._crawl_event(
                "LISTING_EDGE_CASE",
                store=store_key,
                spider=self.name,
                url=response.url,
                category_url=category_url,
                edge_case=t,
            )

        extracted_count = len(canon_products)
        if extracted_count == 0:
            empty_streak = int(meta.get("empty_streak") or 0) + 1
            if page == 1:
                reg.record_zero_result_category(category_url)
        else:
            empty_streak = 0

        self.log_empty_listing_page(
            response,
            category_url=category_url,
            page=page,
            extracted_count=extracted_count,
        )
        reg.record_listing_stats(listing_url=response.url, product_urls_found=extracted_count)

        for u in abs_urls:
            c = self.canonicalize_product_url(u)
            reg.product_urls_seen_total += 1
            if self.should_skip_product_url(c):
                reg.product_urls_deduped_total += 1
                self._crawl_event(
                    "PRODUCT_DEDUPED",
                    category_url=category_url,
                    page=page,
                    canonical_url=c,
                    reason="url_or_source_id_seen",
                )
                continue
            reg.remember_product_url(c)
            sid = self.extract_source_id_from_url(c)
            if sid:
                reg.remember_source_id(sid)
            pr = self.schedule_product_request(
                u,
                response=response,
                meta=dict(meta),
            )
            if pr is not None:
                yield pr

        # Schedule discovered nested listing/category pages (e.g. brand/category menus).
        for cu in abs_category_urls:
            ccu = canonicalize_url(cu)
            if reg.has_listing_page_url(ccu):
                continue
            reg.remember_listing_page_url(ccu)
            self._crawl_event(
                "CATEGORY_DISCOVERED",
                parent_category_url=category_url,
                discovered_category_url=ccu,
                page=1,
            )
            req = self.schedule_safe_request(
                cu,
                callback=self.parse,
                purpose="listing",
                meta={
                    "category_url": cu,
                    "page": 1,
                    "empty_streak": 0,
                    "dup_sig_streak": 0,
                },
            )
            if req is not None:
                yield req

        next_url = self.extract_next_page_url(response)
        stop, reason = self.should_stop_pagination(
            next_url=next_url,
            page=page,
            empty_streak=empty_streak,
            dup_sig_streak=dup_sig_streak,
        )
        if stop:
            if reason == "duplicate_listing_repeats":
                reg.note_pagination_loop()
            self._crawl_event(
                "PAGINATION_STOP",
                category_url=category_url,
                page=page,
                reason=reason,
                empty_streak=empty_streak,
                dup_sig_streak=dup_sig_streak,
            )
            return

        next_abs = response.urljoin(next_url)
        next_canon = canonicalize_url(next_abs)
        if reg.has_listing_page_url(next_canon):
            reg.note_pagination_loop()
            self._crawl_event(
                "PAGINATION_STOP",
                category_url=category_url,
                page=page,
                reason="listing_url_revisit",
                canonical_url=next_canon,
            )
            return

        nreq = self.schedule_safe_request(
            next_abs,
            callback=self.parse,
            purpose="listing",
            meta={
                **meta,
                "page": page + 1,
                "empty_streak": empty_streak,
                "dup_sig_streak": dup_sig_streak,
            },
        )
        if nreq is not None:
            yield nreq

    def schedule_product_request(
        self,
        url: str,
        *,
        response: scrapy.http.Response,
        meta: dict[str, Any],
    ) -> scrapy.Request | None:
        abs_url = response.urljoin(url.strip())
        canon = self.canonicalize_product_url(abs_url)
        pm = {
            **meta,
            "from_listing": response.url,
        }
        return self.schedule_safe_request(canon, callback=self.parse, purpose="product", meta=pm)

    def apply_soft_product_policy(
        self,
        raw: dict[str, Any],
        response: scrapy.http.Response,
    ) -> tuple[dict[str, Any] | None, SoftStatus]:
        """Normalize minimal fields, then apply :mod:`field_policy` usable/partial rules."""
        raw.setdefault("source", self.store_name or self.name)
        raw.setdefault("url", response.url)
        title = (raw.get("title") or raw.get("name") or "").strip()
        source_id = (raw.get("source_id") or raw.get("external_id") or "").strip() or None
        url_sid = self.extract_source_id_from_url(response.url)
        usable_id = source_id or (url_sid or "").strip() or None

        if not title and not usable_id:
            self._crawl_event(
                "PRODUCT_PARSE_FAILED",
                canonical_url=canonicalize_url(response.url),
                reason="no_title_no_identity",
            )
            return None, "drop"

        partial_reasons: list[str] = []
        if not title and usable_id:
            raw["title"] = f"Product {usable_id}"
            partial_reasons.append("missing_title_filled")

        if usable_id and not raw.get("source_id") and not raw.get("external_id"):
            raw["source_id"] = usable_id

        miss_req = missing_required_fields(raw)
        if miss_req:
            self._crawl_event(
                "PRODUCT_PARSE_FAILED",
                canonical_url=canonicalize_url(response.url),
                reason="missing_required:" + ",".join(miss_req),
            )
            return None, "drop"

        if is_partial_product_item(raw):
            partial_reasons.extend(missing_recommended_fields(raw))

        if partial_reasons:
            return raw, "partial"

        return raw, "ok"

    def parse_product(self, response: scrapy.http.Response):
        from infrastructure.performance.timing_profiler import timed_stage

        store_key = self.store_name or self.name
        with timed_stage(
            "product_parse",
            store_name=store_key,
            spider_name=self.name,
        ):
            yield from self._parse_product_inner(response)

    def _parse_product_inner(self, response: scrapy.http.Response):
        self.crawl_registry.product_pages_seen_total += 1
        raw = self.full_parse_item(response)
        if raw is None:
            self.crawl_registry.product_parse_failed_total += 1
            self._crawl_event(
                "PRODUCT_PARSE_FAILED",
                canonical_url=canonicalize_url(response.url),
                reason="full_parse_none",
            )
            return

        raw.setdefault("source", self.store_name)
        raw.setdefault("url", response.url)

        title = (raw.get("title") or raw.get("name") or "").strip() or None
        if raw.get("category_hint") is None:
            hint = self.extract_category_hint(response, title)
            if hint is not None:
                raw["category_hint"] = hint

        item, status = self.apply_soft_product_policy(raw, response)
        if item is None:
            self.crawl_registry.product_parse_failed_total += 1
            return

        if not is_usable_product_item(item):
            self.crawl_registry.product_parse_failed_total += 1
            self.crawl_registry.required_field_presence_misses += 1
            self._crawl_event(
                "PRODUCT_BROKEN",
                store=self.store_name or self.name,
                spider=self.name,
                url=response.url,
                category_url=str(response.meta.get("category_url") or ""),
                required_missing=missing_required_fields(item),
            )
            return

        self.crawl_registry.required_field_presence_hits += 1
        self.crawl_registry.note_product_asset_coverage(
            has_specs=bool(item.get("raw_specs")),
            has_images=bool(item.get("image_urls")),
        )

        acc_prof = get_store_acceptance_profile(self.store_name or self.name)
        pe_tags = edge_cases.classify_product_edge_case(
            item,
            response,
            expected_category_hints=acc_prof.expected_category_hints,
        )
        self.crawl_registry.note_edge_cases(pe_tags)
        rec_miss = missing_recommended_fields(item)
        for t in pe_tags:
            self._crawl_event(
                "PRODUCT_EDGE_CASE",
                store=self.store_name or self.name,
                spider=self.name,
                url=response.url,
                category_url=str(response.meta.get("category_url") or ""),
                edge_case=t,
                recommended_missing=rec_miss,
            )

        is_partial = (status == "partial") or is_partial_product_item(item)
        if is_partial:
            self.crawl_registry.product_parse_partial_total += 1
            self._crawl_event(
                "PRODUCT_PARTIAL",
                store=self.store_name or self.name,
                spider=self.name,
                url=response.url,
                category_url=str(response.meta.get("category_url") or ""),
                recommended_missing=rec_miss,
                result=status,
            )
            from infrastructure.observability import message_codes as obs_mc
            from infrastructure.observability.event_logger import log_sync_event

            log_sync_event(
                "crawl",
                "warning",
                obs_mc.CRAWL_PRODUCT_PARTIAL,
                self._obs_corr_crawl(
                    category_url=str(response.meta.get("category_url") or None),
                    source_url=response.url,
                    source_id=str(item.get("source_id") or item.get("external_id") or "") or None,
                ),
                details={"recommended_missing": rec_miss, "soft_status": status},
                failure_domain="parsing",
                failure_type="partial_product",
            )

        self.crawl_registry.product_items_yielded_total += 1
        self._crawl_event(
            "PRODUCT_PARSED",
            canonical_url=canonicalize_url(response.url),
            source_id=item.get("source_id") or item.get("external_id"),
            result="partial" if is_partial else "ok",
        )
        from infrastructure.observability import message_codes as obs_mc
        from infrastructure.observability.event_logger import log_sync_event

        log_sync_event(
            "crawl",
            "info",
            obs_mc.CRAWL_PRODUCT_PARSED,
            self._obs_corr_crawl(
                category_url=str(response.meta.get("category_url") or None),
                source_url=response.url,
                source_id=str(item.get("source_id") or item.get("external_id") or "") or None,
            ),
            metrics={"partial": bool(is_partial)},
        )
        from infrastructure.performance.perf_collector import increment_counter

        increment_counter("products", 1, store_name=self.store_name or self.name)
        yield as_scrapy_item_dict(item)

    def errback_default(self, failure):
        self.logger.error("[SPIDER_ERROR] %s: %s", failure.request.url, failure.getErrorMessage())
        try:
            from infrastructure.access.resource_governance import release_request_governance_counters

            st = self.store_name or self.name
            meta = getattr(failure.request, "meta", {}) or {}
            release_request_governance_counters(dict(meta), st)
        except Exception:
            logger.debug("resource governance release on errback failed", exc_info=True)
        try:
            from infrastructure.observability import message_codes as obs_mc
            from infrastructure.observability.event_logger import log_sync_event
            from infrastructure.observability.failure_classifier import classify_exception

            exc = failure.value
            fd, ft = classify_exception(exc) if isinstance(exc, BaseException) else ("crawl", "parse_failed")
            meta = getattr(failure.request, "meta", {}) or {}
            log_sync_event(
                "crawl",
                "error",
                obs_mc.CRAWL_FAILURE,
                self._obs_corr_crawl(
                    category_url=str(meta.get("category_url") or "") or None,
                    source_url=getattr(failure.request, "url", None),
                ),
                details={"error_message": failure.getErrorMessage()},
                failure_domain=fd,
                failure_type=ft,
            )
        except Exception:
            logger.debug("observability errback log failed", exc_info=True)
        try:
            import sentry_sdk

            sentry_sdk.capture_exception(failure.value)
        except ImportError:
            pass

    def closed(self, reason: str) -> None:  # Scrapy calls spider.closed(reason) on shutdown
        snap = self.crawl_registry.snapshot_metrics()
        logger.info("crawl_metrics_final %s", json.dumps(snap, default=str))
        store_key = self.store_name or self.name
        prof = get_store_acceptance_profile(store_key)
        edge_counts = dict(snap.get("edge_case_counts") or {})
        qa = build_store_qa_report(
            store_key,
            crawl_snapshot_to_qa_metrics(snap),
            edge_counts,
            prof,
        )
        logger.info(
            "crawl_framework %s",
            json.dumps(
                {
                    "event": "QA_REPORT_BUILT",
                    "store": store_key,
                    "spider": self.name,
                    "quality_gate_passed": qa.get("quality_gate_passed"),
                    "summary": qa.get("derived"),
                },
                default=str,
                ensure_ascii=False,
            ),
        )
