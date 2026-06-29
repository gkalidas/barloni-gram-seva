# Manual Test Checklist — barloni-gram-seva

Run through this before building new modules (e.g. the Complaints module).
Tip: use two browser profiles (or one normal + one incognito) so you can be the
**admin** and a **regular user** at the same time. Tick each box as you verify
it; each line is **action → expected result**.

## A. Setup & startup
- [ ] `python start.py` on a fresh clone → installs deps, creates `.env`, opens browser, no errors
- [ ] Startup log prints the **SECURITY WARNING** while `ADMIN_PASSWORD=admin123` / default `SECRET_KEY`
- [ ] App loads at http://127.0.0.1:8000
- [ ] If a `users.csv` is present in the root → startup log shows "Loaded users… added N, skipped M"
- [ ] Restart the app → second run shows "added 0, skipped N" (no duplicate users)
- [ ] `data/gramseva.db` created; 10 seed schemes present

## B. Public area (no login)
- [ ] Landing page loads
- [ ] Browse `/schemes` lists all active schemes
- [ ] Search box filters by keyword
- [ ] Category filter narrows the list
- [ ] Open a scheme detail page → shows objective, benefits, documents, how-to-apply
- [ ] Visiting `/schemes/99999` (nonexistent) → graceful "not found", not a crash
- [ ] While logged out, `/dashboard`, `/profile`, `/documents`, `/my-schemes` → redirect to login

## C. Signup, login, sessions
- [ ] Sign up with valid details → lands on dashboard, logged in
- [ ] Sign up with mobile that isn't 10 digits → rejected with message
- [ ] Sign up with password < 6 chars → rejected
- [ ] Sign up with mismatched passwords → rejected
- [ ] Sign up with an already-used username → rejected
- [ ] Sign up with an already-used mobile → rejected
- [ ] Log out → returns to home, protected pages redirect again
- [ ] Log in with correct credentials → dashboard
- [ ] Log in with wrong password → "Invalid username or password"
- [ ] Log in as admin → admin panel link visible

## D. Profile & change requests
- [ ] First-time profile fill (all fields) → saved immediately (no approval needed)
- [ ] Leave a required field blank → validation error, not saved
- [ ] Pick "landless" → land area forced to 0 / handled sensibly
- [ ] Edit profile a **second** time → creates a **pending change request** (profile not yet changed)
- [ ] Try editing again while one is pending → blocked ("already have a pending request")
- [ ] Dashboard/profile shows the pending state

## E. Eligibility matcher
- [ ] As a farmer/marginal-land/BPL user → "My schemes" shows PM-KISAN, etc.
- [ ] Change occupation (via approved edit) from labourer→farmer → PM-KISAN appears only after approval
- [ ] A female-only scheme (Ujjwala/Sukanya) does **not** show for a male profile
- [ ] An income-capped scheme drops off when income is above the cap
- [ ] User with **no profile** → "My schemes" prompts to complete profile (no crash)
- [ ] Each eligible scheme shows the documents have/need count

## F. Document locker (user)
- [ ] Upload a valid Aadhaar (jpg/png/pdf) with a number → status "pending"
- [ ] Upload `.exe` or `.txt` → rejected (allowed types message)
- [ ] Upload an empty file → rejected
- [ ] Upload a file > 5 MB → rejected (too large)
- [ ] Pick a document not in the list → rejected
- [ ] Re-upload the same document → replaces it, back to "pending", old file gone
- [ ] Delete your own document → removed from the list
- [ ] Open your own uploaded file via its link → opens

## G. Admin — change request review
- [ ] Pending change request appears in admin list with a count badge
- [ ] Open it → old vs new values shown side by side
- [ ] **Approve** → user's profile updates, pending clears, eligibility recomputes
- [ ] **Reject with a reason** → user sees the reason on their dashboard/profile
- [ ] **Reject and tick required documents** → those docs show up on the user's Documents page
- [ ] Reject with **neither** reason nor documents → blocked
- [ ] Approve/reject an already-reviewed request → "not found or already reviewed"

## H. Admin — document review
- [ ] Pending uploaded document appears with a count badge
- [ ] **Approve** → user's doc becomes "approved" and counts toward scheme readiness
- [ ] **Reject with a reason** → user sees "rejected" + reason
- [ ] Reject with a **blank** reason → blocked
- [ ] Approved doc shows in the user's per-scheme have/need on a scheme detail page

## I. Admin — scheme management
- [ ] Add a scheme via the structured form (age, gender, caste, occupation, land, BPL, bank, income, documents)
- [ ] Set min age > max age → validation error
- [ ] Add a brand-new document via the inline "add document" button → appears in the checklist
- [ ] Save → scheme shows in admin list and public browse
- [ ] Edit a scheme → values pre-filled correctly, changes persist
- [ ] Verify a newly added scheme matches the right users in eligibility

## J. Admin — users
- [ ] `/admin/users` lists all users with their details
- [ ] Counts on the admin dashboard match reality (users / schemes / pending)

## K. CSV import / export
- [ ] Download the **users template** → has the right columns + example row
- [ ] Import a valid users CSV → "added N"
- [ ] Re-import the same file → "skipped N" (dedupe by mobile/username)
- [ ] Import a row with a bad mobile / missing password / invalid gender → reported as row error, others still import
- [ ] **Export users** → password column is blank
- [ ] Re-import that export → everyone skipped (clean round-trip)
- [ ] **Open the exported CSV in LibreOffice/Excel** → a name like `=HYPERLINK(...)` shows as **text**, does not execute (formula-injection fix)
- [ ] Download the **schemes template**
- [ ] **Import schemes** → "added N"; multi-value fields like `male;female` and `farmer;labourer` parse; new documents auto-register
- [ ] Re-import schemes → skipped
- [ ] Export schemes → round-trips back in with all skipped
- [ ] Import an empty / header-less file → graceful error, no crash

## L. Security & access control
- [ ] As a regular user, open `/admin`, `/admin/users`, `/admin/export/users.csv` → **403 Forbidden**
- [ ] User A uploads a doc; **User B** opens `/documents/file/<A's id>` → **403**
- [ ] **Admin** can open User A's file → opens
- [ ] Logged-out request to a file link → redirect to login
- [ ] Tamper the session cookie value → treated as logged out
- [ ] Log in with `…/login?next=//evil.example.com` → after login you land on **/dashboard**, not an external site
- [ ] Check response headers (devtools → Network) → `Content-Security-Policy`, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff` present

## M. Rate limiting & hardening
- [ ] Fail login on one account 8 times → 9th attempt (even correct password) is blocked with a "too many attempts" message
- [ ] A **different** account from the same machine still logs in during that lockout
- [ ] Wait ~5 min → the locked account can log in again
- [ ] Set `SESSION_COOKIE_SECURE=true`, restart over plain http → cookie not sent (login won't stick) — confirms the flag works (then set back to `false` for local)

## N. Production launcher
- [ ] `./serve-prod.sh` with default `ADMIN_PASSWORD` → **refuses to start**
- [ ] With default `SECRET_KEY` → **refuses to start**
- [ ] With strong creds but `SESSION_COOKIE_SECURE=false` → warns but starts
- [ ] With everything set → starts; server header hidden

## P. Complaints module
- [ ] `/complaints` board is visible **without login**
- [ ] Logged-out "Report an issue" → sends you to login first
- [ ] File a complaint (category + ward + description, optional photo) → lands on its detail page
- [ ] Invalid/blank category or empty description → rejected
- [ ] Public board + detail show the complaint **without revealing who filed it**
- [ ] Optional photo: uploaded photo opens via the complaint's "View photo" link
- [ ] "My complaints" lists your own complaints with their status
- [ ] Withdraw a still-"submitted" complaint → status becomes Withdrawn; can't withdraw after admin has acted
- [ ] Admin `/admin/complaints` lists complaints **with** the filer's name + filters (category/ward/status)
- [ ] Admin updates status with a note → public detail shows the new status; audit trail records who/when/note
- [ ] Admin dashboard shows the "Open complaints" count
- [ ] File many complaints quickly → rate limit kicks in (try again later)

## O. Data integrity / edge cases
- [ ] Restart the app mid-use → existing data (users, schemes, docs, requests) all persist
- [ ] A scheme with **no eligibility rules** → shows as eligible for any user with a profile
- [ ] Unicode/Hindi text in a scheme name or profile → displays and exports correctly
- [ ] Very long description/objective text → no layout break or error
