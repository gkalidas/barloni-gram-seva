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
- [x] Officials CSV import/export + seeded starter directory (real Gram Panchayat roles: Sarpanch, Secretary/Gram Sevak, Patwari, ward members, Anganwadi Sevika, ASHA, ANM, service staff per department)
- [x] Profile `ward_no` (+ surfaced mobile); complaint ward optional, defaulting to the profile ward
- [x] Homepage "Raise a Complaint" CTA enabled
- [ ] Email / SMS notification on status change (needs an external provider)

## Schemes — sources & eligibility disputes
- [x] Scheme **sources / references**: admins attach the Government Resolution (GR) file in any format + official source links; shown publicly on the scheme page (files served as a download)
- [x] **Eligibility dispute**: when the matcher says a resident is *not* eligible, they can raise a private complaint ("I think I qualify") tied to that scheme — reuses the complaint engine (status tracking, admin queue, notifications) but is kept off the public anonymous board

## Data Collection
- [ ] Agentic data collector: AI agent that scrapes government portals, structures scheme data and eligibility rules, loops until coverage is complete
- [ ] Auto-update mechanism: periodic re-scraping to catch scheme changes, new schemes, deadline updates

## Admin Enhancements
- [x] Admin dashboard analytics: user signups over time, most-viewed schemes, eligibility distribution — `/admin/analytics`
- [x] Bulk user import via CSV
- [x] Export user data / reports
- [x] Delete a scheme
- [x] Reset a user's password (recovery path, since there is no email/SMS)
- [x] Admin activity log (who did what, when) — `/admin/activity`
- [x] Manage users: change role / deactivate / delete
- [x] Superadmin role + configurable multi-level approval engine (deferred execution): per-action policy (none / N admins / superadmin), approvals queue, superadmin override. Phase 1 wires deletes + role/active/reset-password
- [x] Approval engine — Phase 2 (content edits + initiator notice): scheme add/edit and official add/edit/remove now route through the approval engine; the initiating admin sees a one-time in-app "approved/rejected" notice on their dashboard. (Deferred: CSV-import gating, and folding the resident change-request/document/complaint flows into the same engine — those already have their own review UI and unifying them is a larger refactor.)

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
- [x] Village name / branding from config file (`VILLAGE_NAME`, `APP_NAME`, `BRAND_EMOJI`, `BRAND_TAGLINE`)
- [x] Custom color scheme from config (`BRAND_PRIMARY`, `BRAND_ACCENT`; validated hex, injected as CSS vars)
- [x] Deploy guide for any village to self-host — README "Rebrand for your village" + Production deployment + `.env.example`

## Eligibility Engine Improvements
- [ ] Rule versioning: track when eligibility rules change
- [x] Partial eligibility: "you meet 4/5 criteria, missing: BPL card" — shown on `/my-schemes`
- [x] Recommended actions: "get a BPL card to qualify for 3 more schemes" — shown on `/my-schemes`
- [ ] Notification when new schemes match a user's profile

## Security Enhancements
- [x] Rate limiting on login/signup (per-account + per-IP; in-process)
- [x] Account lockout after failed attempts (8/account, 40/IP per 5 min)
- [x] Security headers (CSP, X-Frame-Options, nosniff, Referrer-Policy)
- [x] Secure session cookie flag (`SESSION_COOKIE_SECURE`, HttpOnly, SameSite)
- [x] CSV formula-injection neutralised on export; open-redirect on login fixed
- [x] Users can change their own password (`/account`); admins can reset a user's password
- [x] CAPTCHA for signup — self-contained stateless arithmetic CAPTCHA (HMAC-signed, no external provider; pairs with per-IP signup rate limiting)
- [x] Password strength requirements — min 8 chars incl. a letter and a number; enforced on signup, self-service change, and admin reset (`app/auth.py:password_problems`)
- [ ] HTTPS enforcement / HSTS (currently terminated at the reverse proxy)
- [ ] Move rate-limit + session store to Redis when scaling past one worker

## Data Migration
- [x] SQLite → PostgreSQL migration script — `scripts/sqlite_to_postgres.py` (dependency-free; emits schema + data + sequence resets)
- [x] Export all data as JSON for backup / transfer — `/admin/export/backup.json` (full dump)
- [x] Import from JSON to bootstrap new village instance — `/admin/export/catalogue.json` + idempotent `/admin/import/catalogue` (schemes, documents, officials; no PII)
