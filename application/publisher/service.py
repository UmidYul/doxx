from __future__ import annotations

from infrastructure.persistence.sqlite_store import SQLiteScraperStore
from services.publisher.config import PublisherServiceConfig
from services.publisher.outbox_reader import SQLiteOutboxReader
from services.publisher.publication_worker import PublicationWorker
from services.publisher.rabbit_publisher import RabbitMQPublisher


class OutboxPublisherService(PublicationWorker):
    def __init__(
        self,
        *,
        store: SQLiteScraperStore | None = None,
        publisher: RabbitMQPublisher | None = None,
        publisher_id: str | None = None,
    ) -> None:
        config = PublisherServiceConfig.from_settings()
        if publisher_id is not None:
            config = config.model_copy(update={"publisher_service_name": publisher_id})
        outbox_reader = SQLiteOutboxReader(store=store, config=config)
        rabbit_publisher = publisher or RabbitMQPublisher(config=config)
        super().__init__(
            config=config,
            outbox_reader=outbox_reader,
            rabbit_publisher=rabbit_publisher,
        )


__all__ = ["OutboxPublisherService"]
