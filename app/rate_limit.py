"""Lightweight in-process rate limiting for auth endpoints.

A sliding-window counter keyed by client IP. This is per-process: it protects
a single-worker deployment (the default for this app). If you ever run multiple
workers or processes, move this to a shared store (e.g. Redis).
"""
import threading
import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    def __init__(self, max_events: int, window_seconds: int):
        self.max_events = max_events
        self.window = window_seconds
        self._hits = defaultdict(deque)
        self._lock = threading.Lock()

    def _trim(self, dq: deque, now: float) -> None:
        cutoff = now - self.window
        while dq and dq[0] < cutoff:
            dq.popleft()

    def is_blocked(self, key: str) -> bool:
        """True if this key has already reached the limit within the window."""
        now = time.time()
        with self._lock:
            dq = self._hits[key]
            self._trim(dq, now)
            return len(dq) >= self.max_events

    def record(self, key: str) -> None:
        """Record one event against the key."""
        now = time.time()
        with self._lock:
            dq = self._hits[key]
            self._trim(dq, now)
            dq.append(now)

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)

    def retry_after(self, key: str) -> int:
        """Seconds until the oldest event in the window expires."""
        now = time.time()
        with self._lock:
            dq = self._hits[key]
            self._trim(dq, now)
            if not dq:
                return 0
            return max(1, int(dq[0] + self.window - now))


def client_ip(request) -> str:
    """Best-effort client IP.

    When deployed behind a reverse proxy, run uvicorn with --proxy-headers
    (and --forwarded-allow-ips) so request.client.host reflects the real
    client rather than the proxy.
    """
    return request.client.host if request.client else "unknown"


# Brute-force protection is keyed on BOTH the targeted account and the source
# IP, because villages often share one public IP (NAT). Keying only on IP would
# let a handful of mistyped passwords lock out a whole village; keying only on
# account would miss a single host spraying many accounts.
#
#   - per-account: 8 failed logins / 5 min  -> that account is briefly locked.
#   - per-IP:     40 failed logins / 5 min  -> catches one host flooding logins
#                                              while staying clear of a busy
#                                              shared connection.
login_failures_user = SlidingWindowLimiter(max_events=8, window_seconds=300)
login_failures_ip = SlidingWindowLimiter(max_events=40, window_seconds=300)

# New signups per IP: generous, so a shared village connection isn't blocked,
# but automated mass account creation still gets stopped.
signup_attempts = SlidingWindowLimiter(max_events=20, window_seconds=3600)


def login_is_blocked(ip: str, username: str) -> int:
    """Return seconds-to-wait if login is currently throttled, else 0."""
    uname = (username or "").strip().lower()
    if login_failures_user.is_blocked(uname):
        return login_failures_user.retry_after(uname)
    if login_failures_ip.is_blocked(ip):
        return login_failures_ip.retry_after(ip)
    return 0


def login_record_failure(ip: str, username: str) -> None:
    login_failures_user.record((username or "").strip().lower())
    login_failures_ip.record(ip)


def login_reset(ip: str, username: str) -> None:
    login_failures_user.reset((username or "").strip().lower())
    login_failures_ip.reset(ip)
