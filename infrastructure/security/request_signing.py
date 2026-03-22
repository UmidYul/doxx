from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from typing import Any

from config.settings import Settings


def build_request_timestamp() -> str:
    return str(int(time.time()))


def build_request_nonce() -> str:
    return secrets.token_hex(16)


def build_canonical_request_string(
    method: str,
    path: str,
    body_bytes: bytes,
    timestamp: str,
    nonce: str,
) -> str:
    """Deterministic canonical string for HMAC (body hashed to fixed length)."""
    body_hash = hashlib.sha256(body_bytes).hexdigest()
    m = (method or "GET").upper().strip()
    p = path or "/"
    ts = (timestamp or "").strip()
    n = (nonce or "").strip()
    return f"{m}\n{p}\n{body_hash}\n{ts}\n{n}\n"


def sign_request_hmac(
    canonical_string: str,
    secret: str,
    algorithm: str = "hmac-sha256",
) -> str:
    norm = (algorithm or "").strip().lower().replace("_", "-")
    if norm != "hmac-sha256":
        raise ValueError(f"unsupported signature algorithm: {algorithm!r}")
    sig = hmac.new(secret.encode("utf-8"), canonical_string.encode("utf-8"), hashlib.sha256).hexdigest()
    return sig


def _safe_str(v: object, default: str) -> str:
    if isinstance(v, str) and v.strip():
        return v.strip()
    return default


def _parse_integrity_mode(settings_obj: Any) -> str:
    return _safe_str(getattr(settings_obj, "CRM_REQUEST_INTEGRITY_MODE", "none"), "none").lower()


def build_request_security_headers(
    method: str,
    path: str,
    body_bytes: bytes,
    settings: Settings,
) -> dict[str, str]:
    """
    Optional HMAC request integrity headers. Does not replace X-Parser-Key.
    - none: {}
    - hmac_optional: sign if signing secret available
    - hmac_required: caller must ensure secret exists (else validator fails at startup)
    """
    mode = _parse_integrity_mode(settings)
    if mode == "none":
        return {}

    from infrastructure.security.secret_loader import load_secret

    sign_env = getattr(settings, "CRM_REQUEST_SIGNING_SECRET", None)
    sign_env = sign_env if isinstance(sign_env, str) else None
    sign_file = getattr(settings, "CRM_REQUEST_SIGNING_SECRET_FILE", None)
    sign_file = sign_file if isinstance(sign_file, str) else None

    secret, _desc = load_secret(
        sign_env,
        sign_file or None,
        name="crm_request_signing",
        enable_file_fallback=bool(getattr(settings, "ENABLE_SECRET_FILE_FALLBACK", True)),
    )
    if not secret:
        if mode in ("hmac_required", "required"):
            raise RuntimeError("hmac_required mode but signing secret missing")
        return {}

    ts = build_request_timestamp()
    nonce = build_request_nonce()
    canonical = build_canonical_request_string(method, path, body_bytes, ts, nonce)
    algo = _safe_str(getattr(settings, "CRM_REQUEST_SIGNATURE_ALGORITHM", "hmac-sha256"), "hmac-sha256")
    sig = sign_request_hmac(canonical, secret, algorithm=algo)

    th = _safe_str(getattr(settings, "CRM_REQUEST_TIMESTAMP_HEADER", "X-Request-Timestamp"), "X-Request-Timestamp")
    nh = _safe_str(getattr(settings, "CRM_REQUEST_NONCE_HEADER", "X-Request-Nonce"), "X-Request-Nonce")
    sh = _safe_str(getattr(settings, "CRM_REQUEST_SIGNATURE_HEADER", "X-Request-Signature"), "X-Request-Signature")
    return {
        str(th).strip(): ts,
        str(nh).strip(): nonce,
        str(sh).strip(): sig,
    }
