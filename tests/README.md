# Automated tests

End-to-end regression suite for barloni-gram-seva. It drives the real FastAPI
app via `TestClient` against a throwaway scratch database (a temp dir, deleted
afterwards) — **your real `data/` and `users.csv` are never touched**.

## Run it

```bash
pip install -r requirements-dev.txt        # one-time (adds httpx + pytest)

python tests/run_tests.py                   # one command, runs everything
# or
pytest tests/                               # same suites via pytest
```

Both run each suite in its own subprocess, because the app reads its config
once at import time and the suites need separate isolated databases.

## What's covered

- **`security_checks.py`** — PII/file access control, the document locker,
  the profile change-request workflow, CSV import/export, and the
  internet-exposure hardening (rate limiting, secure cookie, security headers,
  open-redirect, CSV formula-injection).
- **`functional_checks.py`** — mirrors `TESTING.md` sections A–O: public
  browse/search, signup & profile validation, eligibility scenarios, admin
  scheme management, admin reviews, dashboards, and data-integrity edge cases.

A few `TESTING.md` items remain **manual only** (the one-click launcher UX, how
the CSV renders in LibreOffice/Excel, the real 5-minute lockout expiry, an
actual process restart, and `serve-prod.sh`).

## Adding tests

When you build a new feature (e.g. the Complaints module), add checks to
`functional_checks.py` (or a new `*_checks.py` script plus a wrapper in
`test_suite.py`) and keep the run green before shipping.
