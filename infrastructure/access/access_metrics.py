from __future__ import annotations

import threading
from dataclasses import dataclass, field


@dataclass
class AccessLayerMetrics:
    """In-process counters for the access layer (no Prometheus in 2B)."""

    requests_plain_http_total: int = 0
    requests_proxy_total: int = 0
    requests_browser_total: int = 0
    browser_escalations_total: int = 0
    proxy_escalations_total: int = 0
    ban_signals_total: int = 0
    captcha_hits_total: int = 0
    empty_shell_hits_total: int = 0
    mobile_redirect_hits_total: int = 0
    retry_transport_total: int = 0
    retry_ban_total: int = 0
    request_jitter_applied_total: int = 0
    captcha_hook_detected_total: int = 0
    captcha_solver_attempt_total: int = 0
    captcha_solver_handled_total: int = 0
    captcha_solver_noop_total: int = 0
    empty_body_anomalies_total: int = 0
    http_403_total: int = 0
    http_429_total: int = 0
    http_5xx_total: int = 0
    http_status_spikes_total: int = 0
    proxy_bans_total: int = 0
    retry_http_total: int = 0
    retries_by_reason_total: int = 0
    explicit_backoff_decisions_total: int = 0
    explicit_backoff_header_hints_total: int = 0
    explicit_backoff_retry_suggested_total: int = 0
    explicit_backoff_cooldown_suggested_total: int = 0
    explicit_backoff_wait_applied_total: int = 0
    explicit_backoff_cooldown_applied_total: int = 0
    explicit_backoff_retry_blocked_total: int = 0

    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _labeled_counters: dict[str, int] = field(default_factory=dict, init=False, repr=False)

    def bump(self, field_name: str, n: int = 1) -> None:
        with self._lock:
            current = getattr(self, field_name, 0)
            setattr(self, field_name, current + n)

    def bump_labeled(
        self,
        metric_name: str,
        n: int = 1,
        *,
        store: str | None = None,
        domain: str | None = None,
        reason: str | None = None,
        status: str | int | None = None,
    ) -> None:
        """Increment a lightweight labeled counter snapshot."""
        parts = [str(metric_name).strip()]
        if store:
            parts.append(f"store={(store or '').strip().lower() or 'unknown'}")
        if domain:
            parts.append(f"domain={(domain or '').strip().lower() or 'unknown'}")
        if reason:
            parts.append(f"reason={(reason or '').strip().lower()}")
        if status is not None:
            parts.append(f"status={str(status).strip().lower()}")
        key = "|".join(parts)
        with self._lock:
            self._labeled_counters[key] = int(self._labeled_counters.get(key, 0)) + int(n)

    def labeled_snapshot(self) -> dict[str, int]:
        """Return current labeled counters."""
        with self._lock:
            return dict(self._labeled_counters)

    def reset(self) -> None:
        """Reset all in-memory counters (test helper)."""
        with self._lock:
            self.requests_plain_http_total = 0
            self.requests_proxy_total = 0
            self.requests_browser_total = 0
            self.browser_escalations_total = 0
            self.proxy_escalations_total = 0
            self.ban_signals_total = 0
            self.captcha_hits_total = 0
            self.empty_shell_hits_total = 0
            self.mobile_redirect_hits_total = 0
            self.retry_transport_total = 0
            self.retry_ban_total = 0
            self.request_jitter_applied_total = 0
            self.captcha_hook_detected_total = 0
            self.captcha_solver_attempt_total = 0
            self.captcha_solver_handled_total = 0
            self.captcha_solver_noop_total = 0
            self.empty_body_anomalies_total = 0
            self.http_403_total = 0
            self.http_429_total = 0
            self.http_5xx_total = 0
            self.http_status_spikes_total = 0
            self.proxy_bans_total = 0
            self.retry_http_total = 0
            self.retries_by_reason_total = 0
            self.explicit_backoff_decisions_total = 0
            self.explicit_backoff_header_hints_total = 0
            self.explicit_backoff_retry_suggested_total = 0
            self.explicit_backoff_cooldown_suggested_total = 0
            self.explicit_backoff_wait_applied_total = 0
            self.explicit_backoff_cooldown_applied_total = 0
            self.explicit_backoff_retry_blocked_total = 0
            self._labeled_counters.clear()

    def to_dict(self) -> dict[str, int]:
        with self._lock:
            return {
                "requests_plain_http_total": self.requests_plain_http_total,
                "requests_proxy_total": self.requests_proxy_total,
                "requests_browser_total": self.requests_browser_total,
                "browser_escalations_total": self.browser_escalations_total,
                "proxy_escalations_total": self.proxy_escalations_total,
                "ban_signals_total": self.ban_signals_total,
                "captcha_hits_total": self.captcha_hits_total,
                "empty_shell_hits_total": self.empty_shell_hits_total,
                "mobile_redirect_hits_total": self.mobile_redirect_hits_total,
                "retry_transport_total": self.retry_transport_total,
                "retry_ban_total": self.retry_ban_total,
                "request_jitter_applied_total": self.request_jitter_applied_total,
                "captcha_hook_detected_total": self.captcha_hook_detected_total,
                "captcha_solver_attempt_total": self.captcha_solver_attempt_total,
                "captcha_solver_handled_total": self.captcha_solver_handled_total,
                "captcha_solver_noop_total": self.captcha_solver_noop_total,
                "empty_body_anomalies_total": self.empty_body_anomalies_total,
                "http_403_total": self.http_403_total,
                "http_429_total": self.http_429_total,
                "http_5xx_total": self.http_5xx_total,
                "http_status_spikes_total": self.http_status_spikes_total,
                "proxy_bans_total": self.proxy_bans_total,
                "retry_http_total": self.retry_http_total,
                "retries_by_reason_total": self.retries_by_reason_total,
                "explicit_backoff_decisions_total": self.explicit_backoff_decisions_total,
                "explicit_backoff_header_hints_total": self.explicit_backoff_header_hints_total,
                "explicit_backoff_retry_suggested_total": self.explicit_backoff_retry_suggested_total,
                "explicit_backoff_cooldown_suggested_total": self.explicit_backoff_cooldown_suggested_total,
                "explicit_backoff_wait_applied_total": self.explicit_backoff_wait_applied_total,
                "explicit_backoff_cooldown_applied_total": self.explicit_backoff_cooldown_applied_total,
                "explicit_backoff_retry_blocked_total": self.explicit_backoff_retry_blocked_total,
            }


access_metrics = AccessLayerMetrics()
