#!/usr/bin/env bash
#
# Production launcher for barloni-gram-seva (internet-facing).
#
# Differs from start.py (the local one-click dev launcher) in that it:
#   - runs uvicorn with --proxy-headers so the app sees the real client IP
#     (needed for per-IP rate limiting) when behind a reverse proxy / HTTPS,
#   - refuses to start while SECRET_KEY / ADMIN_PASSWORD are still defaults,
#   - hides the server version header,
#   - stays single-worker on purpose (rate limiting is in-process; see WORKERS).
#
# Expected setup:  put this behind nginx/Caddy doing TLS termination, and set
# SESSION_COOKIE_SECURE=true in .env. Run setup once with:  python start.py --setup-only
#
# Usage:   ./serve-prod.sh
# Override via .env or environment: HOST, PORT, WORKERS, FORWARDED_ALLOW_IPS
#
set -uo pipefail
cd "$(dirname "$0")"

# --- read a key from .env without sourcing it (values may contain spaces) ---
getenv() {  # getenv KEY DEFAULT
  local key="$1" def="${2:-}" val=""
  if [ -f .env ]; then
    val="$(grep -E "^${key}=" .env 2>/dev/null | tail -n1 | cut -d= -f2-)"
  fi
  if [ -z "$val" ]; then val="${!key:-}"; fi
  printf '%s' "${val:-$def}"
}

# --- choose interpreter (prefer the project venv) ---------------------------
if [ -x ".venv/bin/python" ]; then
  PY=".venv/bin/python"
else
  PY="$(command -v python3 || true)"
fi
if [ -z "$PY" ]; then
  echo "ERROR: no Python found. Run 'python3 start.py --setup-only' first." >&2
  exit 1
fi

HOST="$(getenv HOST 0.0.0.0)"
PORT="$(getenv PORT 8000)"
WORKERS="$(getenv WORKERS 1)"          # keep 1: rate limiting is per-process
FORWARDED_ALLOW_IPS="$(getenv FORWARDED_ALLOW_IPS 127.0.0.1)"
SECRET_KEY="$(getenv SECRET_KEY '')"
ADMIN_PASSWORD="$(getenv ADMIN_PASSWORD admin123)"
SESSION_COOKIE_SECURE="$(getenv SESSION_COOKIE_SECURE false)"

# --- pre-flight safety checks ----------------------------------------------
fail=0
if [ -z "$SECRET_KEY" ] || [ "$SECRET_KEY" = "change-this-to-a-random-string" ]; then
  echo "ERROR: SECRET_KEY is unset or still the default. Set a random value in .env" >&2
  echo "       (e.g.  echo \"SECRET_KEY=\$(openssl rand -hex 32)\" >> .env )" >&2
  fail=1
fi
if [ "$ADMIN_PASSWORD" = "admin123" ]; then
  echo "ERROR: ADMIN_PASSWORD is still the default 'admin123'. Change it in .env" >&2
  fail=1
fi
if [ "$SESSION_COOKIE_SECURE" != "true" ]; then
  echo "WARNING: SESSION_COOKIE_SECURE is not 'true'. Set it once you serve over HTTPS," >&2
  echo "         otherwise session cookies are sent over plain HTTP." >&2
fi
if [ "$WORKERS" != "1" ]; then
  echo "WARNING: WORKERS=$WORKERS. Rate limiting is in-process; with >1 worker each" >&2
  echo "         worker counts separately. Use a shared store (Redis) before scaling." >&2
fi
if [ "$fail" = 1 ]; then
  echo "Refusing to start with insecure settings." >&2
  exit 1
fi

echo ">>> Starting barloni-gram-seva (production) on ${HOST}:${PORT}, workers=${WORKERS}"
echo "    Trusting proxy headers from: ${FORWARDED_ALLOW_IPS}"

exec "$PY" -m uvicorn app.main:app \
  --host "$HOST" --port "$PORT" \
  --workers "$WORKERS" \
  --proxy-headers --forwarded-allow-ips "$FORWARDED_ALLOW_IPS" \
  --no-server-header
