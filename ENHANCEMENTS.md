# BARLONI-GRAM-SEVA — Long-term Enhancements & Roadmap

## Before Production (internet-facing deployment) — TODO
This app will be exposed to the public internet. `serve-prod.sh` runs it with
the right uvicorn flags and refuses to start with default credentials, but the
following still need a human:
- [ ] Set a strong `ADMIN_PASSWORD` and a random `SECRET_KEY` in `.env`
      (`openssl rand -hex 32`). `serve-prod.sh` will refuse to start otherwise.
- [ ] Put a TLS-terminating reverse proxy (nginx / Caddy) in front, then set
      `SESSION_COOKIE_SECURE=true` in `.env`.
- [ ] Set `FORWARDED_ALLOW_IPS` to the proxy's IP so `--proxy-headers` is
      trusted only from it (default `127.0.0.1` for a same-host proxy).
- [ ] Keep `WORKERS=1` until rate limiting is moved to a shared store (Redis);
      with multiple workers each keeps its own in-process counters.
- [ ] Set up automated backups of the SQLite DB and the `data/uploads/` files
      (these hold PII — Aadhaar scans etc.).
- [ ] Decide on a log-rotation / monitoring story for the server.
- [ ] (Recommended) add CAPTCHA on signup and password-strength rules — see
      Security Enhancements below.

## Phase 2 — Complaints Module
- [x] Complaint categories: water, electricity, garbage, roads, drainage, other
- [x] Complaint form: category, ward/area, description, optional photo upload
- [x] Complaint status tracking: submitted → acknowledged → in progress → resolved (+ rejected/withdrawn)
- [x] Admin view: complaints dashboard with filtering by category, ward, status
- [x] Public **anonymous** community board (filer identity kept to the admin/audit trail only)
- [x] Filer can withdraw a still-"submitted" complaint; per-user rate limit on filing
- [x] Status-change audit trail (who changed what, when, with a note)
- [x] Ward-level complaint analytics (totals, by category/ward/status, ward×category matrix, this-month)
- [x] Notify the filer when their complaint status changes (in-app: dashboard banner + "Updated" badge)
- [x] Officials / responsible-people directory: admin CRUD + public level-based hierarchy (`/officials`), linked to complaints by ward + department
- [x] Profile `ward_no` (+ surfaced mobile); complaint ward optional, defaulting to the profile ward
- [x] Homepage "Raise a Complaint" CTA enabled
- [ ] Email / SMS notification on status change (needs an external provider)

## Data Collection
- [ ] Agentic data collector: AI agent that scrapes government portals, structures scheme data and eligibility rules, loops until coverage is complete
- [ ] Auto-update mechanism: periodic re-scraping to catch scheme changes, new schemes, deadline updates

## Admin Enhancements
- [ ] Admin dashboard analytics: user signups over time, most-viewed schemes, eligibility distribution
- [x] Bulk user import via CSV
- [x] Export user data / reports
- [x] Delete a scheme
- [x] Reset a user's password (recovery path, since there is no email/SMS)
- [x] Admin activity log (who did what, when) — `/admin/activity`
- [x] Manage users: change role / deactivate / delete

## Multi-language Support
- [ ] Hindi (primary)
- [ ] Marathi
- [ ] Language toggle in UI
- [ ] Store scheme data in multiple languages (name_hi, name_mr, objective_hi, etc.)

## Offline / Low-bandwidth Mode
- [ ] PWA (Progressive Web App) with service worker for offline access
- [ ] Cache scheme data locally
- [ ] Queue profile submissions for sync when online
- [ ] Compressed assets, lazy loading

## White-labeling
- [ ] Village name / branding from config file
- [ ] Custom color scheme from config
- [ ] Deploy guide for any village to self-host

## Eligibility Engine Improvements
- [ ] Rule versioning: track when eligibility rules change
- [ ] Partial eligibility: "you meet 4/5 criteria, missing: BPL card"
- [ ] Recommended actions: "get a BPL card to qualify for 3 more schemes"
- [ ] Notification when new schemes match a user's profile

## Security Enhancements
- [x] Rate limiting on login/signup (per-account + per-IP; in-process)
- [x] Account lockout after failed attempts (8/account, 40/IP per 5 min)
- [x] Security headers (CSP, X-Frame-Options, nosniff, Referrer-Policy)
- [x] Secure session cookie flag (`SESSION_COOKIE_SECURE`, HttpOnly, SameSite)
- [x] CSV formula-injection neutralised on export; open-redirect on login fixed
- [x] Users can change their own password (`/account`); admins can reset a user's password
- [ ] CAPTCHA for signup
- [ ] Password strength requirements
- [ ] HTTPS enforcement / HSTS (currently terminated at the reverse proxy)
- [ ] Move rate-limit + session store to Redis when scaling past one worker

## Data Migration
- [ ] SQLite → PostgreSQL migration script
- [ ] Export all data as JSON for backup / transfer
- [ ] Import from JSON to bootstrap new village instance
