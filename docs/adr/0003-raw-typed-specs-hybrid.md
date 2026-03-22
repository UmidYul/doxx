# ADR 0003: `raw_specs` + `typed_specs` hybrid

## Status

Accepted

## Context

Stores expose heterogeneous spec text; CRM needs both opaque fidelity and structured fields where we can map reliably.

## Decision

Keep `raw_specs` as lossless-ish carrier; add `typed_specs` / extractor output only where mapping is deterministic and tested.

## Consequences

Partial coverage is acceptable; do not invent typed fields without registry coverage.
