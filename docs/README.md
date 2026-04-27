# Documentation index

Entry point for the active Moscraper ingestion architecture: store scraping, scraper DB, outbox publication, and store knowledge. Repo root [`README.md`](../README.md) is the short operational entry; this file is the navigation index. Deep product context: [`PROJECT.md`](../PROJECT.md).

## Quick start

- [`onboarding.md`](onboarding.md) - first day setup and active runtime boundaries
- [`supabase_deployment.md`](supabase_deployment.md) - Supabase DSNs, managed RabbitMQ, cron-run scraper jobs, replay
- [`../DEV_WORKFLOW.md`](../DEV_WORKFLOW.md) - concrete commands, fixture checks, smoke runs

## Architecture

- [`new_scraper_architecture.md`](new_scraper_architecture.md) - stage-1 target architecture for `Scraper Service -> Scraper DB -> Publisher Service -> RabbitMQ`
- [`ingestion_architecture.md`](ingestion_architecture.md) - scraper DB, outbox, publisher, and RabbitMQ design
- [`final_ingestion_flow.md`](final_ingestion_flow.md) - final stage-6 runtime boundary and disabled legacy paths
- [`publisher_service.md`](publisher_service.md) - standalone publisher service
- [`scraper_db_schema.md`](scraper_db_schema.md) - scraper DB and outbox schema
- [`supabase_deployment.md`](supabase_deployment.md) - deployment bootstrap and cron-driven runtime
- [`../PROJECT.md`](../PROJECT.md) - broader project context and boundaries
- [`../ARCHITECTURE_MAP.md`](../ARCHITECTURE_MAP.md) - module map, if present
- [`adr/README.md`](adr/README.md) - ADR index

## Store development

- [`store_playbook_template.md`](store_playbook_template.md) - copy for new stores
- [`stores/mediapark.md`](stores/mediapark.md) - MediaPark playbook
- [`stores/mediapark_new.md`](stores/mediapark_new.md) - deeper MediaPark migration notes
- [`stores/texnomart.md`](stores/texnomart.md) - Texnomart playbook
- [`stores/uzum.md`](stores/uzum.md) - Uzum playbook
- [`stores/alifshop.md`](stores/alifshop.md) - Alifshop playbook
- [`store_migration_matrix.md`](store_migration_matrix.md) - cross-store migration and acceptance matrix
- Spiders: `infrastructure/spiders/`

## Delivery integration

- [`ingestion_architecture.md`](ingestion_architecture.md) - scraper-side delivery contract and outbox model
- [`final_ingestion_flow.md`](final_ingestion_flow.md) - final active contour
- [`crm_integration.md`](crm_integration.md) - legacy CRM-facing material kept only for migration context
- [`rabbitmq_crm_integration.md`](rabbitmq_crm_integration.md) - practical CRM consumer guide for RabbitMQ integration

## Lifecycle, observability, and release

- [`support_triage.md`](support_triage.md) - health, triage, runbooks, safe replay, safe exports
- [`release_process.md`](release_process.md) - gates, rollout, compatibility
- [`production_readiness.md`](production_readiness.md) - readiness domains and evidence
- [`fixtures_and_acceptance.md`](fixtures_and_acceptance.md) - regression fixtures and acceptance expectations
- [`adr/README.md`](adr/README.md) - architecture decision records

## Ownership

- [`../OWNERSHIP_MAP.md`](../OWNERSHIP_MAP.md) - ownership and escalation map
