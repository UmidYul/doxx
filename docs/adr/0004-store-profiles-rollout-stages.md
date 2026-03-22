# ADR 0004: Store profiles and rollout stages

## Status

Accepted

## Context

Stores differ (HTTP vs browser, proxy needs, bans). Shipping one global behavior increases cost and incident rate.

## Decision

Encode per-store behavior in profiles (`infrastructure/access/store_profiles.py`) and gate risky behavior via rollout/feature flags (`application/release/`).

## Consequences

New store behavior is profile + flag driven, not scattered `if store ==` blocks in common layers.
