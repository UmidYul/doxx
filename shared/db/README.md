# Shared Scraper DB Blueprint

This directory contains the target relational schema for the scraper-side database.

## Files

- `schema.sql`
  Current schema snapshot for the scraper-side SQLite database.
- `migrations/0001_scraper_persistence_foundation.sql`
  First durable migration for the stage-2 scraper persistence and outbox foundation.

## Notes

- The schema is intentionally scraper-centric, not CRM-centric.
- It is designed for replay, debugging, audit, field-coverage checks, and XLSX export.
- It separates product core data from images/specs and publication state.
