# BARLONI-GRAM-SEVA — Full Build Spec

## INSTRUCTIONS FOR CLAUDE CODE

You are building a village-level civic platform from scratch. Build the ENTIRE project without stopping or asking questions. Everything you need is in this document. When the build is complete, initialize a git repo, commit everything, and push to `gkalidas/barloni-gram-seva` on GitHub.

DO NOT STOP until:
- All files are created
- The app runs successfully with `uvicorn`
- Database tables are created on first run
- Default admin login works
- All routes are functional
- Git repo is initialized and pushed

---

## PROJECT OVERVIEW

**barloni-gram-seva** is a village-level government scheme information portal. Two core functions:
1. **Scheme Directory** — anyone can browse/search government schemes (no login needed)
2. **Eligibility Matcher** — logged-in users fill a one-time profile, system shows which schemes they qualify for

This is a white-label app — any village can deploy it with their own data. Scheme data is the same across villages; user data differs.

---

## TECH STACK

- **Backend:** Python 3.10+, FastAPI, Uvicorn
- **Database:** SQLite with aiosqlite (single file: `data/gramseva.db`)
- **ORM:** None. Use raw SQL with aiosqlite. Keep it simple.
- **Templates:** Jinja2 (FastAPI's built-in Jinja2Templates)
- **Frontend:** Plain HTML + CSS + minimal vanilla JS. No frameworks. Mobile-first responsive design.
- **Auth:** Session-based using signed cookies (itsdangerous). No JWT.
- **Password hashing:** bcrypt via passlib
- **Config:** python-dotenv, all config from `.env` file

---

## PROJECT STRUCTURE

```
barloni-gram-seva/
├── .env                          # Environment variables (gitignored)
├── .env.example                  # Template for .env
├── .gitignore
├── README.md
├── requirements.txt
├── ENHANCEMENTS.md               # Long-term roadmap & future features
├── run.py                        # Entry point: uvicorn runner
├── app/
│   ├── __init__.py
│   ├── main.py                   # FastAPI app creation, middleware, startup
│   ├── config.py                 # Settings from .env
│   ├── database.py               # DB connection, table creation, migrations
│   ├── auth.py                   # Auth utilities: hashing, sessions, dependencies
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── public.py             # Landing page, scheme browsing (no auth)
│   │   ├── auth_routes.py        # Signup, login, logout
│   │   ├── user.py               # User dashboard, profile, eligibility view
│   │   └── admin.py              # Admin panel: approve changes, manage schemes, manage users
│   ├── services/
│   │   ├── __init__.py
│   │   ├── scheme_service.py     # Scheme CRUD, search
│   │   ├── user_service.py       # Profile management, change requests
│   │   └── eligibility_service.py # Matching engine: user profile vs scheme rules
│   ├── templates/
│   │   ├── base.html             # Base layout with nav, flash messages
│   │   ├── landing.html          # Two big buttons: Get Information | Raise Complaint (disabled)
│   │   ├── schemes/
│   │   │   ├── browse.html       # Searchable scheme directory
│   │   │   └── detail.html       # Single scheme detail page
│   │   ├── auth/
│   │   │   ├── login.html
│   │   │   └── signup.html
│   │   ├── user/
│   │   │   ├── dashboard.html    # Overview: eligible schemes + profile status
│   │   │   ├── profile.html      # View profile (read-only after first submit)
│   │   │   ├── profile_edit.html # Edit profile (creates change request)
│   │   │   └── eligibility.html  # Full list of eligible schemes with details
│   │   └── admin/
│   │       ├── dashboard.html    # Pending change requests count, user count, scheme count
│   │       ├── change_requests.html  # List of pending profile change requests
│   │       ├── review_change.html    # Side-by-side diff: old vs new, approve/reject
│   │       ├── users.html        # All users list
│   │       ├── schemes.html      # Scheme management: list, add, edit
│   │       └── scheme_form.html  # Add/edit scheme form
│   └── static/
│       ├── css/
│       │   └── style.css         # Mobile-first, simple, clean. No framework.
│       └── js/
│           └── main.js           # Minimal: search filtering, form validation
└── data/                         # SQLite DB lives here (gitignored)
    └── .gitkeep
```

---

## DATABASE SCHEMA

All tables created on first startup in `database.py`. Use `CREATE TABLE IF NOT EXISTS`.

### Table: `users`

```sql
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    mobile TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',  -- 'user' or 'admin'
    profile_data TEXT,                  -- JSON blob, nullable until first profile submit
    pending_profile_data TEXT,          -- JSON blob, nullable, holds unapproved edits
    profile_submitted INTEGER DEFAULT 0, -- 0 = not yet submitted, 1 = submitted
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
```

### Table: `profile_change_requests`

```sql
CREATE TABLE IF NOT EXISTS profile_change_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    old_values TEXT NOT NULL,            -- JSON snapshot before change
    new_values TEXT NOT NULL,            -- JSON snapshot of requested changes
    status TEXT NOT NULL DEFAULT 'pending',  -- 'pending', 'approved', 'rejected'
    rejection_reason TEXT,              -- Required when status = 'rejected'
    reviewed_by INTEGER,               -- admin user_id who acted on it
    requested_at TEXT DEFAULT (datetime('now')),
    reviewed_at TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (reviewed_by) REFERENCES users(id)
);
```

### Table: `schemes`

```sql
CREATE TABLE IF NOT EXISTS schemes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    name_hi TEXT,                        -- Hindi name
    ministry TEXT,                       -- Ministry / Department
    category TEXT,                       -- agriculture, housing, health, education, pension, employment, women_child, sc_st_welfare, other
    objective TEXT,                      -- One-line plain-language summary
    benefits TEXT,                       -- What the person gets
    eligibility_rules TEXT,             -- JSON: structured rules for matching engine
    documents_required TEXT,            -- JSON array of strings
    how_to_apply TEXT,                  -- Free text
    application_deadline TEXT,          -- Date string or 'ongoing'
    status TEXT DEFAULT 'active',       -- 'active', 'closed', 'upcoming'
    scheme_data TEXT,                   -- JSON blob for any additional flexible fields
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
```

---

## PROFILE DATA JSON STRUCTURE

When a user fills the profile form, store this JSON in `profile_data`:

```json
{
    "full_name": "Rajesh Kumar",
    "date_of_birth": "1985-03-15",
    "age": 40,
    "gender": "male",
    "state": "Rajasthan",
    "district": "Jaipur",
    "village": "Barloni",
    "caste_category": "OBC",
    "bpl_card": true,
    "annual_family_income": 120000,
    "occupation": "farmer",
    "land_ownership": "marginal",
    "land_area_acres": 2.5,
    "family_size": 5,
    "has_disability": false,
    "bank_account_aadhaar_linked": true
}
```

### Profile form field specs:

| Field | Type | Options / Validation |
|---|---|---|
| full_name | text | Required |
| date_of_birth | date | Required, auto-calculate age |
| gender | select | male, female, other |
| state | text | Required |
| district | text | Required |
| village | text | Required |
| caste_category | select | general, obc, sc, st |
| bpl_card | checkbox | true/false |
| annual_family_income | number | Required, in ₹ |
| occupation | select | farmer, labourer, self_employed, salaried, student, unemployed, other |
| land_ownership | select | landless, marginal (< 2.5 acres), small (2.5-5 acres), large (> 5 acres) |
| land_area_acres | number | Show only if not landless, optional |
| family_size | number | Required, min 1 |
| has_disability | checkbox | true/false |
| bank_account_aadhaar_linked | checkbox | true/false |

---

## ELIGIBILITY RULES JSON STRUCTURE

Each scheme has `eligibility_rules` stored as JSON. The matching engine evaluates user profile against these rules.

```json
{
    "min_age": 18,
    "max_age": 60,
    "gender": ["female"],
    "caste_category": ["sc", "st", "obc"],
    "max_income": 250000,
    "bpl_card_required": true,
    "occupation": ["farmer", "labourer"],
    "land_ownership": ["landless", "marginal"],
    "has_disability": null,
    "bank_account_required": true
}
```

**Matching logic (in `eligibility_service.py`):**
- For each rule field, if the value is `null` or the key is absent → skip (no restriction).
- `min_age` / `max_age`: user's age must fall within range.
- `gender`: user's gender must be in the list.
- `caste_category`: user's caste must be in the list.
- `max_income`: user's income must be ≤ this value.
- `bpl_card_required`: if true, user must have BPL card.
- `occupation`: user's occupation must be in the list.
- `land_ownership`: user's land type must be in the list.
- `has_disability`: if true, user must have disability.
- `bank_account_required`: if true, user must have linked bank account.

A user is **eligible** for a scheme only if they pass ALL non-null rules.

---

## AUTHENTICATION

### Session-based auth using signed cookies:
- Use `itsdangerous.URLSafeTimedSerializer` to sign session cookies
- Cookie name: `session`
- Cookie contains: `{"user_id": 123, "role": "admin"}`
- Session expiry: 24 hours
- Secret key from `.env`

### Auth dependency (in `auth.py`):
```python
async def get_current_user(request: Request) -> Optional[dict]:
    """Returns user dict if logged in, None otherwise."""

async def require_user(request: Request) -> dict:
    """Returns user dict or redirects to login."""

async def require_admin(request: Request) -> dict:
    """Returns admin user dict or returns 403."""
```

### Default admin from ENV:
On startup, check if admin exists. If not, create one from ENV vars:
```
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123
ADMIN_MOBILE=9999999999
```

---

## ROUTES

### Public (no auth):
- `GET /` — Landing page with two options: "Get Information" and "Raise a Complaint" (complaint button shows "Coming Soon" badge, disabled)
- `GET /schemes` — Browse all active schemes, search by name/category
- `GET /schemes/{id}` — Scheme detail page
- `GET /login` — Login form
- `POST /login` — Process login
- `GET /signup` — Signup form
- `POST /signup` — Process signup (creates user with role='user')
- `GET /logout` — Clear session, redirect to /

### User (auth required):
- `GET /dashboard` — User dashboard: profile status, count of eligible schemes, pending change requests status
- `GET /profile` — View current profile (read-only)
- `GET /profile/edit` — Edit profile form (first time: full form; subsequent: pre-filled, changes create change request)
- `POST /profile/edit` — Submit profile (first time: saves directly to profile_data, sets profile_submitted=1; subsequent: saves to pending_profile_data, creates change_request)
- `GET /my-schemes` — Full list of schemes user is eligible for, with details

### Admin (admin auth required):
- `GET /admin` — Admin dashboard: counts of pending requests, total users, total schemes
- `GET /admin/change-requests` — List all pending profile change requests
- `GET /admin/change-requests/{id}` — Review single change request: show old vs new side by side, approve/reject buttons
- `POST /admin/change-requests/{id}/approve` — Approve: copy new_values to user's profile_data, clear pending_profile_data, update change_request status, record reviewed_by
- `POST /admin/change-requests/{id}/reject` — Reject: require rejection_reason, update change_request status, clear pending_profile_data, record reviewed_by
- `GET /admin/users` — List all users
- `GET /admin/schemes` — List all schemes
- `GET /admin/schemes/add` — Add new scheme form
- `POST /admin/schemes/add` — Save new scheme
- `GET /admin/schemes/{id}/edit` — Edit scheme form
- `POST /admin/schemes/{id}/edit` — Update scheme

---

## UI / DESIGN GUIDELINES

- **Mobile-first.** Most users will be on cheap Android phones. Design for 360px width first.
- **Simple, clean, government-style.** Think: NIC websites but actually usable. No fancy animations.
- **Color scheme:** Deep blue (#1a365d) header, white background, green (#2f855a) for success/eligible, orange (#c05621) for pending, red (#c53030) for rejected. Light gray (#f7fafc) for card backgrounds.
- **Typography:** System fonts only. No web font loading. `font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;`
- **Language:** English for now. All UI labels in English. Multi-language is a future enhancement.
- **Navigation:** Simple top nav bar with: Home | Schemes | Dashboard (if logged in) | Admin (if admin) | Login/Logout
- **Flash messages:** Show success/error messages using a simple banner at top of content area. Pass via query params or session.
- **Forms:** Clear labels, large touch targets (min 44px height for inputs/buttons), visible validation errors.
- **Tables:** Responsive — on mobile, either scroll horizontally or stack as cards.

---

## SEED DATA

Create a `seed_schemes.py` script that populates 10 sample schemes on first run (skip if schemes already exist). Use realistic Indian government schemes:

1. **PM-KISAN** — ₹6000/year to small/marginal farmers
2. **MGNREGA** — 100 days guaranteed employment
3. **PM Awas Yojana (Gramin)** — Housing for rural BPL families
4. **Ayushman Bharat (PMJAY)** — ₹5 lakh health coverage for BPL
5. **PM Ujjwala Yojana** — Free LPG connections for BPL women
6. **Sukanya Samriddhi Yojana** — Savings scheme for girl child
7. **PM Fasal Bima Yojana** — Crop insurance for farmers
8. **National Social Assistance Programme (NSAP)** — Old age pension for BPL
9. **Scholarship for SC/ST students** — Education scholarship
10. **PM Vishwakarma** — Support for traditional artisans/craftspeople

For each scheme, provide realistic `eligibility_rules` JSON that the matching engine can evaluate against user profiles.

---

## .env.example

```
SECRET_KEY=change-this-to-a-random-string
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123
ADMIN_MOBILE=9999999999
DATABASE_PATH=data/gramseva.db
```

---

## .gitignore

```
__pycache__/
*.py[cod]
.env
data/*.db
*.sqlite3
.venv/
venv/
.idea/
.vscode/
*.egg-info/
dist/
build/
```

---

## requirements.txt

```
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
aiosqlite>=0.19.0
jinja2>=3.1.0
python-multipart>=0.0.6
itsdangerous>=2.1.0
passlib[bcrypt]>=1.7.4
python-dotenv>=1.0.0
```

---

## ENHANCEMENTS.md (create this file in the project root)

```markdown
# BARLONI-GRAM-SEVA — Long-term Enhancements & Roadmap

## Phase 2 — Complaints Module
- [ ] Complaint categories: water, electricity, garbage, roads, drainage, common/other
- [ ] Complaint form: category, description, ward/area, optional photo upload
- [ ] Complaint status tracking: submitted → acknowledged → in progress → resolved
- [ ] Admin view: complaints dashboard with filtering by category, ward, status
- [ ] Ward-level complaint analytics ("15 water complaints from Ward 3 this month")

## Data Collection
- [ ] Agentic data collector: AI agent that scrapes government portals, structures scheme data and eligibility rules, loops until coverage is complete
- [ ] Auto-update mechanism: periodic re-scraping to catch scheme changes, new schemes, deadline updates

## Admin Enhancements
- [ ] Admin dashboard analytics: user signups over time, most-viewed schemes, eligibility distribution
- [ ] Bulk user import via CSV
- [ ] Export user data / reports
- [ ] Admin activity log (who did what, when)

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
- [ ] Rate limiting on login/signup
- [ ] CAPTCHA for signup
- [ ] Password strength requirements
- [ ] Account lockout after failed attempts
- [ ] HTTPS enforcement

## Data Migration
- [ ] SQLite → PostgreSQL migration script
- [ ] Export all data as JSON for backup / transfer
- [ ] Import from JSON to bootstrap new village instance
```

---

## FINAL CHECKLIST BEFORE PUSHING

1. ✅ All files created per project structure
2. ✅ `pip install -r requirements.txt` succeeds
3. ✅ App starts with `python run.py`
4. ✅ Database tables created on first startup
5. ✅ Default admin created from .env on first startup
6. ✅ Landing page loads at `/`
7. ✅ Can signup as new user
8. ✅ Can login as user and admin
9. ✅ Can fill profile form (first submit saves directly)
10. ✅ Can edit profile (creates change request)
11. ✅ Admin can see and approve/reject change requests
12. ✅ Scheme browse/search works
13. ✅ Eligibility matching works for logged-in users with submitted profiles
14. ✅ Admin can add/edit schemes
15. ✅ Seed schemes load on first run
16. ✅ Mobile-responsive design works
17. ✅ Git init, commit all, push to gkalidas/barloni-gram-seva
18. ✅ `.env` is gitignored, `.env.example` is committed
19. ✅ README.md has setup instructions

---

## README.md content

Include:
- Project name and one-line description
- Features list
- Prerequisites (Python 3.10+)
- Setup steps: clone, create venv, install deps, copy .env.example to .env, edit .env, run
- Default admin credentials note
- Project structure overview
- License: MIT
