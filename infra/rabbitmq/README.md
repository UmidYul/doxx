# RabbitMQ Topology

RabbitMQ is the final boundary of responsibility for the scraper contour.

## Ownership

The scraper side owns:

- exchange declaration
- queue declaration for the scraper-owned publication lane
- routing key contract
- durable publish semantics
- outbox-driven retries until publish succeeds or a row becomes terminally failed

The scraper side does not own:

- downstream consumer logic beyond the scraper publication queue
- CRM transformations
- final normalization
- product merge logic after RabbitMQ

See `topology.json` for the target topology blueprint.
