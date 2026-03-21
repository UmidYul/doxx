"""CloudEvents v1.0 listing message types for Moscraper → RabbitMQ.

The envelope matches the `CloudEvents <https://github.com/cloudevents/spec/blob/v1.0.2/spec.md>`_
attribute set used in production: ``specversion``, ``type``, ``source``, ``id``, ``time``,
``datacontenttype``, optional ``subject``, and JSON ``data``.

Moscraper is stateless: payloads are validated here and published to the broker (see PROJECT.md).
Event type is fixed to ``com.moscraper.listing.scraped``; ``data`` follows ``ListingScrapedData``
(CRM contract: ``entity_key``, ``payload_hash``, pricing fields, etc.).

Serialize for the wire with Pydantic JSON mode and ``orjson``, e.g.
``orjson.dumps(event.model_dump(mode="json"))``.
"""

from __future__ import annotations

from domain.messages import CloudEventListingScraped, ListingScrapedData

CloudEvent = CloudEventListingScraped
ProductData = ListingScrapedData

__all__ = ["CloudEvent", "ProductData", "CloudEventListingScraped", "ListingScrapedData"]
