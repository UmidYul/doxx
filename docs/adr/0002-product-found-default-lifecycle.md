# ADR 0002: `product_found` as safe default lifecycle event

## Status

Accepted

## Context

We need a conservative default when classification is ambiguous so CRM can apply idempotently without inventing destructive semantics.

## Decision

Prefer `product_found` (and related safe modes) as the default happy-path selection where policy does not mandate a stricter event.

## Consequences

Stricter events require explicit lifecycle policy; spiders should not silently emit destructive types.
