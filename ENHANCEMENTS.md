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
