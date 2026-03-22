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

    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def bump(self, field_name: str, n: int = 1) -> None:
        with self._lock:
            current = getattr(self, field_name, 0)
            setattr(self, field_name, current + n)

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
            }


access_metrics = AccessLayerMetrics()
