"""A self-contained arithmetic CAPTCHA for the signup form.

Deliberately has no external dependency (no reCAPTCHA / hCaptcha), so it works
offline and needs no third-party script — important for a low-bandwidth, public
deployment with a strict Content-Security-Policy.

The challenge is stateless: the token carries an HMAC of the answer (keyed by
SECRET_KEY) plus the issue time, never the answer itself, so it is tamper-proof
and expires on its own without any server-side storage. A determined bot can of
course read the rendered "3 + 5" and compute it — this stops naive scripted
sign-ups, not a targeted attacker. Pair it with the existing per-IP signup rate
limiting (see app/rate_limit.py) for defence in depth.
"""
import hashlib
import hmac
import secrets
import time

from app.config import settings

CAPTCHA_MAX_AGE = 600  # seconds a challenge stays valid (10 minutes)


def _sign(answer: int, issued_at: int) -> str:
    msg = f"{answer}:{issued_at}".encode("utf-8")
    return hmac.new(settings.SECRET_KEY.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def make_captcha() -> dict:
    """Return a fresh challenge: {'question': '3 + 5', 'token': '<ts>.<hmac>'}."""
    a = secrets.randbelow(9) + 1
    b = secrets.randbelow(9) + 1
    issued_at = int(time.time())
    token = f"{issued_at}.{_sign(a + b, issued_at)}"
    return {"question": f"{a} + {b}", "token": token}


def verify_captcha(token: str, answer: str) -> bool:
    """True if `answer` matches the signed `token` and it hasn't expired."""
    if not token or answer is None:
        return False
    try:
        ts_str, sig = token.split(".", 1)
        issued_at = int(ts_str)
    except (ValueError, AttributeError):
        return False
    if time.time() - issued_at > CAPTCHA_MAX_AGE:
        return False
    try:
        ans = int(str(answer).strip())
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(sig, _sign(ans, issued_at))
