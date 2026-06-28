# barloni-gram-seva

A village-level government scheme information portal. Browse government schemes and find out which ones you are eligible for.

## Features

- **Scheme Directory** — Anyone can browse and search government schemes (no login needed).
- **Eligibility Matcher** — Logged-in users fill a one-time profile and instantly see which schemes they qualify for.
- **Profile change approvals** — Profile edits create change requests that an admin reviews and approves/rejects.
- **Admin panel** — Manage schemes, review change requests, and view users.
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

## Project structure

```
barloni-gram-seva/
├── start.py                # One-click setup + launcher (recommended)
├── start.sh / start.bat    # Double-click wrappers (macOS-Linux / Windows)
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
└── data/                   # SQLite DB lives here (gitignored)
```

## License

MIT
