# Anti-Ban Safe Rollout (Phase 7)

This document defines the production-safe rollout strategy for anti-ban improvements introduced in phases 1-6.

## Feature bundle

- `access_delay_jitter`
- `header_profile_rotation`
- `proxy_policy_hardening`
- `captcha_hooks`
- `honeypot_link_filter`
- `ban_signal_monitoring`

Each feature is gated by:

1. rollout feature flag (`is_feature_enabled(...)`)
2. runtime settings gate (`SCRAPY_*_ENABLED`)

## Staged rollout

1. `local`
2. `staging`
3. `pilot_1_store`
4. `pilot_10_percent_stores`
5. `full_rollout`

Default canary expansion percentage follows `ROLLOUT_CANARY_PERCENTAGE`.

## Readiness checklist signals

Required before production expansion when anti-ban runtime gates are enabled:

- feature flags registered for all anti-ban capabilities
- rollout preflight completed (`local`, `staging`, rollout plan reviewed)
- rollback drill completed

Progress tracking (non-blocking for first cutover):

- 1 store pilot evidence captured
- 10% stores pilot evidence captured

## Rollback strategy

1. Disable anti-ban runtime gates (`SCRAPY_*_ENABLED=false`).
2. Move anti-ban feature flags to `disabled` (or `canary`) stage.
3. Disable affected stores via `ROLLOUT_DISABLED_STORES`.
4. Revert rollout commit if runtime rollback is insufficient.
5. Run focused smoke crawl before re-enable.
