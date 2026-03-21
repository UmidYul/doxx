from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from domain.messages import CloudEventListingScraped


class MessagePublisher(ABC):
    @abstractmethod
    async def publish_listing_scraped(self, event: CloudEventListingScraped) -> None:
        """Publish one validated CloudEvent to the broker."""

    async def close(self) -> None:
        """Release broker resources."""
