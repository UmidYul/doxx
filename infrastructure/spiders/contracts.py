from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import scrapy.http


@runtime_checkable
class StoreSpiderContract(Protocol):
    """Store identity and category entry points."""

    store_name: str

    def start_category_urls(self) -> list[str] | tuple[str, ...]:
        """Seed URLs for listing/category traversal (not PDP)."""
        ...


@runtime_checkable
class ListingTraversalContract(Protocol):
    """Listing page → product URLs + pagination."""

    def is_product_page(self, response: scrapy.http.Response) -> bool:
        """True if this response should be parsed as a PDP."""
        ...

    def extract_listing_product_urls(self, response: scrapy.http.Response) -> list[str]:
        """Absolute or relative product URLs from a category/listing page."""
        ...

    def extract_next_page_url(self, response: scrapy.http.Response) -> str | None:
        """Next listing page URL, or None if unknown / end."""
        ...


@runtime_checkable
class ProductExtractionContract(Protocol):
    """PDP URL canonicalization and product payload."""

    def canonicalize_product_url(self, url: str) -> str:
        """Deterministic product URL for dedupe and entity keys."""
        ...

    def extract_source_id_from_url(self, url: str) -> str | None:
        """Stable store-specific id when not present in parsed payload."""
        ...

    def extract_category_hint(
        self,
        response_or_url: scrapy.http.Response | str,
        title: str | None = None,
    ) -> str | None:
        """High-level category hint (not buried in raw_specs)."""
        ...

    def full_parse_item(self, response: scrapy.http.Response) -> dict[str, Any] | None:
        """Parse PDP HTML into a raw item dict (pre-:func:`as_scrapy_item_dict`)."""
        ...
