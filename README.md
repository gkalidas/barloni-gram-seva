# barloni-gram-seva

A village-level government scheme information portal. Browse government schemes and find out which ones you are eligible for.

## Features

- **Scheme Directory** — Anyone can browse and search government schemes (no login needed).
- **Eligibility Matcher** — Logged-in users fill a one-time profile and instantly see which schemes they qualify for.
- **Profile change approvals** — Profile edits create change requests that an admin reviews and approves/rejects.
- **Complaints** — Residents file civic complaints (category, ward, optional photo); a public **anonymous** board shows everyone the issues and their status, while admins track them to resolution with an audit trail.
- **Admin panel** — Manage schemes, review change requests and documents, track complaints, and view users.
- **White-label** — Any village can deploy its own instance; scheme data is shared, user data is local.

## Prerequisites

- Python 3.10+

## Quick start (one click)

After cloning, just launch the app — it sets everything up for you the first
time (creates a `.env` with a secure secret key, builds an isolated
environment, installs dependencies, then starts the server and opens your
browser). Python 3.10+ is the only thing you need installed first.

- **Windows:** double-click **`start.bat`**
- **macOS / Linux:** double-click **`start.sh`** (or run `./start.sh` in a terminal)
- **Any platform:** `python start.py`

The first run takes a minute to install dependencies; later runs start in
seconds. To set up without launching (e.g. to pre-install), run
`python start.py --setup-only`.

The app starts on http://127.0.0.1:8000

## Manual setup (alternative)

```bash
# 1. Clone
git clone https://github.com/gkalidas/barloni-gram-seva.git
cd barloni-gram-seva

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate        # On Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env and set a strong SECRET_KEY and admin credentials

# 5. Run
python run.py
```

The app starts on http://127.0.0.1:8000

On first startup the app will:
- Create the SQLite database and tables in `data/gramseva.db`
- Create the default admin user from `.env`
- Seed 10 sample government schemes

## Default admin credentials

Set in `.env` (defaults shown below — **change these in production**):

```
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123
ADMIN_MOBILE=9999999999
```

## Configuration (`.env`)

Each village can customise its instance via `.env`:

- `VILLAGE_NAME` / `APP_NAME` — branding shown in the header and titles
- `HOST` / `PORT` — where the server listens (default `127.0.0.1:8000`).
  Set `HOST=0.0.0.0` to let other devices on the same Wi‑Fi/LAN (e.g. phones)
  open the app at `http://<this-computer-ip>:8000`.
- `SECRET_KEY` — auto-generated on first run by `start.py`; keep it private.

## Production deployment (internet-facing)

`start.py` is for **local / LAN** use. To serve the app on the **public
internet**, use **`serve-prod.sh`**, which runs uvicorn with the right flags and
refuses to start with insecure defaults.

```bash
# 1. One-time setup (creates .venv, installs deps)
python3 start.py --setup-only

# 2. Lock down .env (serve-prod.sh will refuse to start otherwise)
echo "SECRET_KEY=$(openssl rand -hex 32)" >> .env   # or edit the existing line
#   set a strong ADMIN_PASSWORD=...
#   set SESSION_COOKIE_SECURE=true   (once you're behind HTTPS)

# 3. Launch
./serve-prod.sh
```

`serve-prod.sh` will:

- run behind a reverse proxy with `--proxy-headers` so per-IP rate limiting sees
  real clients (set `FORWARDED_ALLOW_IPS` to your proxy's IP; default
  `127.0.0.1`),
- **refuse to start** while `SECRET_KEY` / `ADMIN_PASSWORD` are still defaults,
- hide the server version header, and stay **single-worker** (rate limiting is
  in-process; keep `WORKERS=1` until you move it to a shared store like Redis).

Put a TLS-terminating reverse proxy (nginx / Caddy) in front of it and point it
at `HOST:PORT`. Security-relevant `.env` knobs:

- `SESSION_COOKIE_SECURE` — set `true` behind HTTPS so the session cookie is
  TLS-only (keep `false` for local http dev).
- `WORKERS`, `FORWARDED_ALLOW_IPS` — read by `serve-prod.sh` (see above).

See **`ENHANCEMENTS.md` → "Before Production"** for the full go-live checklist
(strong creds, HTTPS, PII backups of the DB and `data/uploads/`, monitoring).

## Tests

An automated end-to-end regression suite drives the real app against a
throwaway database (your real data is never touched):

```bash
pip install -r requirements-dev.txt     # one-time (httpx + pytest)
python tests/run_tests.py               # one command, runs everything
# or: pytest tests/
```

It covers security/access control, the document locker, the change-request
workflow, CSV import/export, eligibility matching, admin scheme management, and
the internet-exposure hardening. See `tests/README.md` for details and
`TESTING.md` for the manual checklist (a few items can only be checked by hand).

## Project structure

```
barloni-gram-seva/
├── start.py                # One-click setup + launcher (local/dev)
├── start.sh / start.bat    # Double-click wrappers (macOS-Linux / Windows)
├── serve-prod.sh           # Production launcher (internet-facing)
├── run.py                  # Dev entry point (uvicorn runner, auto-reload)
├── app/
│   ├── main.py             # FastAPI app, middleware, startup
│   ├── config.py           # Settings from .env
│   ├── database.py         # DB connection, table creation
│   ├── auth.py             # Auth utilities and dependencies
│   ├── routes/             # public, auth, user, admin routes
│   ├── services/           # scheme, user, eligibility services
│   ├── templates/          # Jinja2 templates
│   └── static/             # CSS and JS
├── seed_schemes.py         # Seed sample schemes
├── tests/                  # Automated regression suite (run_tests.py / pytest)
├── requirements-dev.txt    # Test dependencies (httpx, pytest)
└── data/                   # SQLite DB lives here (gitignored)
```

## License

MIT
