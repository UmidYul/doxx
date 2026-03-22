# ADR 0001: Parser is stateless

## Status

Accepted

## Context

Downstream CRM owns dedup, images, DB, retries, DLQ. A parser-owned database or backlog would duplicate truth and complicate operations.

## Decision

No scraper-owned durable store for listings; outbound path is broker messages only (see `PROJECT.md`). Tests may disable publish.

## Consequences

Runs are repeatable one-shots; “delta vs last crawl” is a CRM concern, not Moscraper’s.
