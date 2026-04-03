# Shared Contracts

This directory defines the scraper-owned contract at the RabbitMQ boundary.

## Files

- `scraper_product_event.schema.json`
  Defines the target message contract for `scraper.product.scraped.v1`.
- `scraper_product_event.example.json`
  Concrete example payload for contract consumers and acceptance checks.

## Ownership rule

Anything downstream from this contract is outside the scraper project boundary.

