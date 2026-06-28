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

## Setup

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

## Project structure

```
barloni-gram-seva/
├── run.py                  # Entry point (uvicorn runner)
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
