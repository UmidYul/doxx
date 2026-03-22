from __future__ import annotations

from collections import OrderedDict, defaultdict
from typing import Iterable

from config.settings import settings


class CrawlRuntimeRegistry:
    """In-memory crawl-layer dedupe + lightweight metrics for one spider run (no disk/DB)."""

    def __init__(self, *, store: str) -> None:
        self.store = store
        self._seen_canonical_product_urls: OrderedDict[str, bool] = OrderedDict()
        self._seen_source_ids: OrderedDict[str, bool] = OrderedDict()
        self._seen_listing_signatures: OrderedDict[str, bool] = OrderedDict()
        self._seen_canonical_listing_urls: OrderedDict[str, bool] = OrderedDict()
        self._zero_result_categories: set[str] = set()
        self._listing_to_product_counts: OrderedDict[str, int] = OrderedDict()

        # Metrics (also logged via spider structured events)
        self.categories_started_total: int = 0
        self.categories_zero_result_total: int = 0
        self.listing_pages_seen_total: int = 0
        self.listing_pages_duplicated_total: int = 0
        self.product_urls_seen_total: int = 0
        self.product_urls_deduped_total: int = 0
        self.product_pages_seen_total: int = 0
        self.product_parse_partial_total: int = 0
        self.product_parse_failed_total: int = 0
        self.product_items_yielded_total: int = 0

        self._edge_case_counts: defaultdict[str, int] = defaultdict(int)
        self.banned_responses_total: int = 0
        self.pagination_loops_detected: int = 0
        self.required_field_presence_hits: int = 0
        self.required_field_presence_misses: int = 0

    def note_edge_cases(self, tags: Iterable[str]) -> None:
        for t in tags:
            if t:
                self._edge_case_counts[t] += 1

    def note_banned_response(self) -> None:
        self.banned_responses_total += 1

    def note_pagination_loop(self) -> None:
        self.pagination_loops_detected += 1

    def _max_entries(self) -> int:
        return int(settings.SCRAPY_CRAWL_REGISTRY_MAX_ENTRIES)

    def _trim_ordered(self, od: OrderedDict[str, bool]) -> None:
        max_n = self._max_entries()
        if max_n <= 0:
            return
        while len(od) > max_n:
            od.popitem(last=False)

    def remember_product_url(self, canonical_url: str) -> None:
        u = canonical_url
        if u in self._seen_canonical_product_urls:
            self._seen_canonical_product_urls.move_to_end(u)
        else:
            self._seen_canonical_product_urls[u] = True
        self._trim_ordered(self._seen_canonical_product_urls)

    def has_product_url(self, canonical_url: str) -> bool:
        return canonical_url in self._seen_canonical_product_urls

    def remember_source_id(self, source_id: str) -> None:
        if not source_id:
            return
        k = f"{self.store}:{source_id}"
        if k in self._seen_source_ids:
            self._seen_source_ids.move_to_end(k)
        else:
            self._seen_source_ids[k] = True
        self._trim_ordered(self._seen_source_ids)

    def has_source_id(self, source_id: str) -> bool:
        if not source_id:
            return False
        return f"{self.store}:{source_id}" in self._seen_source_ids

    def remember_listing_signature(self, signature: str) -> None:
        if signature in self._seen_listing_signatures:
            self._seen_listing_signatures.move_to_end(signature)
        else:
            self._seen_listing_signatures[signature] = True
        self._trim_ordered(self._seen_listing_signatures)

    def has_listing_signature(self, signature: str) -> bool:
        return signature in self._seen_listing_signatures

    def remember_listing_page_url(self, canonical_listing_url: str) -> None:
        u = canonical_listing_url
        if u in self._seen_canonical_listing_urls:
            self._seen_canonical_listing_urls.move_to_end(u)
        else:
            self._seen_canonical_listing_urls[u] = True
        self._trim_ordered(self._seen_canonical_listing_urls)

    def has_listing_page_url(self, canonical_listing_url: str) -> bool:
        return canonical_listing_url in self._seen_canonical_listing_urls

    def record_zero_result_category(self, category_url: str) -> None:
        self._zero_result_categories.add(category_url)
        self.categories_zero_result_total += 1

    def record_listing_stats(self, *, listing_url: str, product_urls_found: int) -> None:
        self._listing_to_product_counts[listing_url] = product_urls_found
        self._listing_to_product_counts.move_to_end(listing_url)
        max_n = self._max_entries()
        if max_n > 0:
            while len(self._listing_to_product_counts) > max_n:
                self._listing_to_product_counts.popitem(last=False)

    def snapshot_metrics(self) -> dict[str, int | str]:
        return {
            "store": self.store,
            "categories_started_total": self.categories_started_total,
            "categories_zero_result_total": self.categories_zero_result_total,
            "listing_pages_seen_total": self.listing_pages_seen_total,
            "listing_pages_duplicated_total": self.listing_pages_duplicated_total,
            "product_urls_seen_total": self.product_urls_seen_total,
            "product_urls_deduped_total": self.product_urls_deduped_total,
            "product_pages_seen_total": self.product_pages_seen_total,
            "product_parse_partial_total": self.product_parse_partial_total,
            "product_parse_failed_total": self.product_parse_failed_total,
            "product_items_yielded_total": self.product_items_yielded_total,
            "zero_result_categories_count": len(self._zero_result_categories),
            "edge_case_counts": dict(self._edge_case_counts),
            "banned_responses_total": self.banned_responses_total,
            "pagination_loops_detected": self.pagination_loops_detected,
            "required_field_presence_hits": self.required_field_presence_hits,
            "required_field_presence_misses": self.required_field_presence_misses,
        }
