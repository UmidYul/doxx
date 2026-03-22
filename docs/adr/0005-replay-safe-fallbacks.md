# ADR 0005: Replay-safe semantics prefer fallback over blind delta resend

## Status

Accepted

## Context

Ambiguous CRM responses and missing IDs happen; blind “resend everything” risks duplicates or unsafe writes.

## Decision

Use reconciliation paths, idempotency keys, and explicit resend policies (`application/lifecycle/`) instead of unbounded delta replay from the parser.

## Consequences

Parser emphasizes deterministic payloads + keys; CRM remains authoritative for merge semantics.
