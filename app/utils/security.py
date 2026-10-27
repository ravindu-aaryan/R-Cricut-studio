"""Security helpers: CSRF tokens, host checks, and response headers.

Binding to 127.0.0.1 is the first line of defence but it is not sufficient
on its own: any web page the user visits could try to send requests to the
local port. We therefore also require a CSRF token on state-changing
requests, reject foreign Host headers (DNS-rebinding protection) and
foreign Origin headers, and send a strict Content-Security-Policy.
"""
from __future__ import annotations

import hmac
import secrets

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
CSRF_HEADER = "X-CSRF-Token"

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "img-src 'self' data: blob:; "
    "style-src 'self' 'unsafe-inline'; "
    "script-src 'self'; "
    "font-src 'self'; "
    "connect-src 'self' blob:; "
    "object-src 'none'; "
    "frame-ancestors 'none'; "
    "base-uri 'none'; "
    "form-action 'self'"
)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def tokens_match(expected: str, supplied: str | None) -> bool:
    if not supplied or not expected:
        return False
    return hmac.compare_digest(expected.encode(), supplied.encode())


def host_allowed(host_header: str | None, allowed_hosts: set[str]) -> bool:
    """Check the Host header (without port) against ``allowed_hosts``."""
    if not host_header:
        return False
    host = host_header.strip().lower()
    if host.startswith("["):  # IPv6 literal like [::1]:5000
        host = host[: host.find("]") + 1]
    else:
        host = host.rsplit(":", 1)[0] if ":" in host else host
    return host in allowed_hosts


def origin_allowed(origin: str | None, allowed_hosts: set[str]) -> bool:
    """Origin may be absent (same-origin fetches from some browsers)."""
    if origin is None or origin == "":
        return True
    if origin == "null":
        return False
    for scheme in ("http://", "https://"):
        if origin.startswith(scheme):
            return host_allowed(origin[len(scheme):], allowed_hosts)
    return False


def security_headers() -> dict[str, str]:
    return {
        "Content-Security-Policy": CONTENT_SECURITY_POLICY,
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Cross-Origin-Opener-Policy": "same-origin",
        "Cross-Origin-Resource-Policy": "same-origin",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=(), interest-cohort=()",
    }
