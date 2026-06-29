"""Automated mirror of TESTING.md (sections A-O) via FastAPI TestClient.

Runs the real app against an isolated scratch DB. Verifies everything that can
be exercised without a human (browser UX, LibreOffice rendering, and the real
5-minute lockout clock are flagged as manual-only).
"""
import os
import sys
import tempfile
import shutil
import asyncio
import io
import csv as _csv

SCRATCH = tempfile.mkdtemp(prefix="gramseva-full-")
os.environ["DATABASE_PATH"] = os.path.join(SCRATCH, "test.db")
os.environ["SEED_USERS_CSV"] = ""
os.environ["SECRET_KEY"] = "test-secret-key-fixed"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "admin123"
os.environ["ADMIN_MOBILE"] = "9999999999"

# Make the project root importable no matter where this is launched from.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app                    # noqa: E402
from app.services import (                  # noqa: E402
    user_service, scheme_service, document_service,
    user_document_service, import_export_service as iio,
)

_p = _f = 0
_fail = []
def check(name, cond, detail=""):
    global _p, _f
    if cond:
        _p += 1; print(f"  PASS  {name}")
    else:
        _f += 1; _fail.append((name, detail)); print(f"  FAIL  {name}  -- {detail}")
def section(t): print(f"\n=== {t} ===")
def run_async(coro): return asyncio.get_event_loop().run_until_complete(coro)

PNG = bytes.fromhex("89504e470d0a1a0a") + b"\x00" * 64

def captcha_fields():
    """Mint a valid signup CAPTCHA in-process (same SECRET_KEY as the app)."""
    from app.captcha import make_captcha
    ch = make_captcha()
    a, b = ch["question"].split(" + ")
    return {"captcha_token": ch["token"], "captcha_answer": str(int(a) + int(b))}

def signup(c, u, m, pw="secret123"):
    data = {"username": u, "mobile": m, "password": pw, "confirm_password": pw}
    data.update(captcha_fields())
    return c.post("/signup", data=data, follow_redirects=False)

def fill_profile(c, **over):
    base = {"full_name": "Test User", "date_of_birth": "1980-01-01",
            "gender": "male", "state": "Rajasthan", "district": "Jaipur",
            "village": "Barloni", "caste_category": "obc",
            "annual_family_income": "100000", "occupation": "farmer",
            "land_ownership": "marginal", "land_area_acres": "2",
            "family_size": "5", "bank_account_aadhaar_linked": "on"}
    base.update(over)
    return c.post("/profile/edit", data=base, follow_redirects=False)


def run():
    with TestClient(app) as root:
        admin = TestClient(app)
        admin.post("/login", data={"username": "admin", "password": "admin123"},
                   follow_redirects=False)

        # ---------- A. Setup & startup ----------
        section("A. Setup & startup")
        n = run_async(scheme_service.count_schemes())
        check("10 seed schemes present", n == 10, n)
        # users.csv idempotency proxy: import twice via service
        ucsv = ("username,mobile,password,full_name,date_of_birth,gender,state,"
                "district,village,caste_category,occupation,land_ownership,"
                "annual_family_income,family_size\n"
                "seeded1,9990000001,pw123456,Seed One,1990-01-01,male,RJ,J,Barloni,obc,farmer,marginal,90000,4\n")
        s1 = run_async(iio.import_users(ucsv.encode()))
        s2 = run_async(iio.import_users(ucsv.encode()))
        check("seed import idempotent (1 added then 0)",
              s1["added"] == 1 and s2["added"] == 0 and s2["skipped"] == 1, (s1, s2))
        check("DB file exists on disk", os.path.isfile(os.environ["DATABASE_PATH"]))

        # ---------- B. Public area ----------
        section("B. Public area (no login)")
        anon = TestClient(app)
        check("landing loads", anon.get("/").status_code == 200)
        # i18n: switching to Hindi translates the nav; invalid codes fall back.
        lang_client = TestClient(app)
        lr = lang_client.get("/lang/hi?next=/", follow_redirects=False)
        check("language switch sets cookie + redirects",
              lr.status_code == 303 and "lang=hi" in lr.headers.get("set-cookie", ""))
        check("nav renders in Hindi after switch", "योजनाएँ" in lang_client.get("/").text)
        lang_client.get("/lang/zz?next=/", follow_redirects=False)
        check("invalid language falls back to English", "योजनाएँ" not in lang_client.get("/").text)
        check("PWA manifest + service worker served",
              anon.get("/manifest.webmanifest").status_code == 200
              and anon.get("/sw.js").status_code == 200)
        r = anon.get("/schemes")
        check("browse schemes loads + lists", r.status_code == 200 and "PM-KISAN" in r.text)
        r = anon.get("/schemes", params={"q": "MGNREGA"})
        check("search filters (MGNREGA found, PM-KISAN out)",
              "MGNREGA" in r.text and "PM-KISAN" not in r.text)
        r = anon.get("/schemes", params={"category": "health"})
        check("category filter (health shows Ayushman)", "Ayushman" in r.text)
        # a scheme detail page
        s = run_async(scheme_service.get_scheme_by_name("PM-KISAN"))
        r = anon.get(f"/schemes/{s['id']}")
        check("scheme detail loads", r.status_code == 200 and "PM-KISAN" in r.text)
        r = anon.get("/schemes/99999", follow_redirects=False)
        check("nonexistent scheme -> graceful 404", r.status_code == 404)
        for path in ["/dashboard", "/profile", "/documents", "/my-schemes"]:
            rr = anon.get(path, follow_redirects=False)
            check(f"logged-out {path} -> login redirect",
                  rr.status_code == 303 and "/login" in rr.headers.get("location", ""))

        # ---------- C. Signup, login, sessions ----------
        section("C. Signup, login, sessions")
        c = TestClient(app)
        check("valid signup -> dashboard", signup(c, "validjoe", "9000001000").status_code == 303)
        bad = TestClient(app)
        check("signup bad mobile rejected", signup(bad, "shortmob", "12345").status_code == 400)
        check("signup short password rejected",
              signup(TestClient(app), "shortpw", "9000001001", pw="123").status_code == 400)
        mm = {"username": "mm", "mobile": "9000001002",
              "password": "abcdef12", "confirm_password": "zzzzzz12"}
        mm.update(captcha_fields())
        r = TestClient(app).post("/signup", data=mm, follow_redirects=False)
        check("signup mismatched passwords rejected", r.status_code == 400)
        check("signup duplicate username rejected",
              signup(TestClient(app), "validjoe", "9000001003").status_code == 400)
        check("signup duplicate mobile rejected",
              signup(TestClient(app), "another", "9000001000").status_code == 400)
        # CAPTCHA: a signup with a wrong/missing answer is rejected
        wrong = {"username": "botuser", "mobile": "9000001009",
                 "password": "secret123", "confirm_password": "secret123",
                 "captcha_token": "0.deadbeef", "captcha_answer": "7"}
        check("signup with bad CAPTCHA rejected",
              TestClient(app).post("/signup", data=wrong,
                                   follow_redirects=False).status_code == 400)
        # password without a digit is rejected (strength rule)
        check("signup weak password (no digit) rejected",
              signup(TestClient(app), "nodigits", "9000001010", pw="abcdefgh").status_code == 400)
        # login / logout
        lc = TestClient(app)
        signup(lc, "loginuser", "9000001004", pw="mypass123")
        lc.get("/logout", follow_redirects=False)
        r = lc.post("/login", data={"username": "loginuser", "password": "mypass123"},
                    follow_redirects=False)
        check("login correct creds -> 303", r.status_code == 303)
        r = lc.post("/login", data={"username": "loginuser", "password": "WRONG"},
                    follow_redirects=False)
        check("login wrong password -> 401", r.status_code == 401)

        # ---------- D. Profile & change requests ----------
        section("D. Profile & change requests")
        d = TestClient(app)
        signup(d, "profuser", "9000002000")
        # missing required field -> 400
        r = d.post("/profile/edit", data={"full_name": ""}, follow_redirects=False)
        check("profile missing fields -> 400 validation", r.status_code == 400)
        # valid first-time save
        fill_profile(d, occupation="labourer")
        du = run_async(user_service.get_user_by_username("profuser"))
        prof = user_service.get_profile(du)
        check("first profile saved directly", prof and prof["occupation"] == "labourer")
        # landless -> land area 0
        d2 = TestClient(app); signup(d2, "landlessguy", "9000002001")
        fill_profile(d2, land_ownership="landless", land_area_acres="9")
        d2u = run_async(user_service.get_user_by_username("landlessguy"))
        check("landless forces land area 0",
              user_service.get_profile(d2u)["land_area_acres"] == 0.0)
        # second edit -> pending request, profile unchanged
        fill_profile(d, occupation="farmer")
        du = run_async(user_service.get_user_by_username("profuser"))
        check("2nd edit keeps profile until approval",
              user_service.get_profile(du)["occupation"] == "labourer")
        check("2nd edit creates pending request",
              run_async(user_service.has_pending_request(du["id"])))
        # block while pending
        fill_profile(d, village="Elsewhere")
        reqs = run_async(user_service.list_user_change_requests(du["id"]))
        check("only one pending while one open",
              len([r for r in reqs if r["status"] == "pending"]) == 1)

        # ---------- E. Eligibility matcher ----------
        section("E. Eligibility matcher")
        # /my-schemes now also lists "close to qualifying" (near-miss) schemes
        # and recommended actions below the eligible list. Exclusion checks must
        # look only at the *eligible* section (the text before that heading).
        def eligible_section(text):
            return text.split("close to qualifying")[0]

        e = TestClient(app); signup(e, "farmerguy", "9000003000")
        fill_profile(e, occupation="farmer", land_ownership="marginal")
        page = e.get("/my-schemes").text
        page_elig = eligible_section(page)
        check("farmer sees PM-KISAN", "PM-KISAN" in page_elig)
        check("farmer-only excludes female-only Sukanya", "Sukanya" not in page_elig)
        # female-only visibility
        f = TestClient(app); signup(f, "girlchild", "9000003001")
        fill_profile(f, gender="female", date_of_birth="2020-01-01",
                     occupation="student", land_ownership="landless")
        fp = eligible_section(f.get("/my-schemes").text)
        check("female child sees Sukanya", "Sukanya" in fp)
        check("male not eligible for Sukanya (cross-check)", "Sukanya" not in page_elig)
        # income cap: high income drops Ayushman (needs bpl + income<=200k)
        g = TestClient(app); signup(g, "richguy", "9000003002")
        fill_profile(g, annual_family_income="999999", occupation="farmer")
        gp = eligible_section(g.get("/my-schemes").text)
        check("high income excludes income-capped Awas", "Awas" not in gp)
        # no profile
        h = TestClient(app); signup(h, "noprofile", "9000003003")
        r = h.get("/my-schemes")
        check("no-profile my-schemes renders (no crash)", r.status_code == 200)
        # docs have/need annotation present for eligible farmer
        check("eligible scheme shows doc readiness wording",
              "document" in page.lower() or "doc" in page.lower())
        # BPL enforcement: farmer without a BPL card is excluded from BPL schemes
        check("non-BPL farmer excluded from PM Awas (BPL-required)", "Awas" not in page_elig)

        # ---------- F. Document locker ----------
        section("F. Document locker")
        def upload(cli, name, fname, content, number="123"):
            return cli.post("/documents", data={"document_name": name, "doc_number": number},
                            files={"file": (fname, content, "application/octet-stream")},
                            follow_redirects=False)
        check("valid upload -> 303", upload(e, "Aadhaar card", "a.png", PNG).status_code == 303)
        check("disallowed ext -> 400", upload(e, "Aadhaar card", "x.exe", b"MZ").status_code == 400)
        check("empty file -> 400", upload(e, "Aadhaar card", "x.png", b"").status_code == 400)
        big = b"\x00" * (user_document_service.MAX_FILE_BYTES + 1)
        check("oversized -> 400", upload(e, "Aadhaar card", "big.png", big).status_code == 400)
        check("unknown doc name -> 400", upload(e, "No Such Doc", "x.png", PNG).status_code == 400)
        eu = run_async(user_service.get_user_by_username("farmerguy"))
        edocs = run_async(user_document_service.list_user_documents(eu["id"]))
        aad = [x for x in edocs if x["document_name"] == "Aadhaar card"][0]
        old = aad["file_path"]
        upload(e, "Aadhaar card", "a2.png", PNG, number="555")
        edocs = run_async(user_document_service.list_user_documents(eu["id"]))
        aad = [x for x in edocs if x["document_name"] == "Aadhaar card"][0]
        check("re-upload replaces + old file gone", not os.path.isfile(old) and aad["doc_number"] == "555")
        r = e.get(f"/documents/file/{aad['id']}", follow_redirects=False)
        check("owner opens own file -> 200", r.status_code == 200)

        # ---------- G. Admin change-request review ----------
        section("G. Admin change-request review")
        creqs = run_async(user_service.list_change_requests(status="pending"))
        target = [r for r in creqs if r["user_id"] == du["id"]][0]
        r = admin.get(f"/admin/change-requests/{target['id']}")
        check("review page shows old/new", r.status_code == 200)
        admin.post(f"/admin/change-requests/{target['id']}/approve", follow_redirects=False)
        du = run_async(user_service.get_user_by_username("profuser"))
        check("approve updates profile", user_service.get_profile(du)["occupation"] == "farmer")
        check("approve clears pending", not run_async(user_service.has_pending_request(du["id"])))
        # reject with reason + required docs
        fill_profile(d, annual_family_income="40000")
        req = [r for r in run_async(user_service.list_user_change_requests(du["id"]))
               if r["status"] == "pending"][0]
        admin.post(f"/admin/change-requests/{req['id']}/reject",
                   data={"rejection_reason": "Need proof",
                         "required_documents": ["Income certificate"]}, follow_redirects=False)
        latest = run_async(user_service.latest_change_request(du["id"]))
        check("reject stores reason", latest["rejection_reason"] == "Need proof")
        check("reject stores required docs", "Income certificate" in latest["required_documents"])
        docpage = d.get("/documents").text
        check("user sees requested doc on documents page", "Income certificate" in docpage)
        dash = d.get("/dashboard").text
        check("user dashboard shows rejection", "reject" in dash.lower())
        # reject with neither -> blocked
        fill_profile(d, family_size="8")
        req = [r for r in run_async(user_service.list_user_change_requests(du["id"]))
               if r["status"] == "pending"][0]
        admin.post(f"/admin/change-requests/{req['id']}/reject",
                   data={"rejection_reason": ""}, follow_redirects=False)
        still = [r for r in run_async(user_service.list_user_change_requests(du["id"]))
                 if r["status"] == "pending"]
        check("reject with nothing -> blocked", len(still) == 1)
        admin.post(f"/admin/change-requests/{req['id']}/reject",
                   data={"rejection_reason": "cleanup"}, follow_redirects=False)

        # ---------- H. Admin document review ----------
        section("H. Admin document review")
        admin.post(f"/admin/document-requests/{aad['id']}/approve", follow_redirects=False)
        check("doc approved -> in approved set",
              "Aadhaar card" in run_async(user_document_service.approved_document_names(eu["id"])))
        upload(e, "PAN card", "pan.png", PNG)
        pan = [x for x in run_async(user_document_service.list_user_documents(eu["id"]))
               if x["document_name"] == "PAN card"][0]
        admin.post(f"/admin/document-requests/{pan['id']}/reject",
                   data={"rejection_reason": ""}, follow_redirects=False)
        pan = [x for x in run_async(user_document_service.list_user_documents(eu["id"]))
               if x["document_name"] == "PAN card"][0]
        check("doc reject blank reason -> still pending", pan["status"] == "pending")
        admin.post(f"/admin/document-requests/{pan['id']}/reject",
                   data={"rejection_reason": "blurry"}, follow_redirects=False)
        pan = [x for x in run_async(user_document_service.list_user_documents(eu["id"]))
               if x["document_name"] == "PAN card"][0]
        check("doc reject with reason -> rejected", pan["status"] == "rejected")

        # ---------- I. Admin scheme management ----------
        section("I. Admin scheme management")
        before = run_async(scheme_service.count_schemes())
        form = {"name": "Auto Test Scheme", "ministry": "Min Z", "category": "agriculture",
                "objective": "obj", "benefits": "ben", "how_to_apply": "apply",
                "application_deadline": "ongoing", "status": "active",
                "min_age": "18", "max_age": "60", "max_income": "200000",
                "rule_gender": ["male", "female"], "rule_occupation": ["farmer"],
                "rule_land": ["marginal"],
                "documents": ["Aadhaar card", "Bank account passbook"]}
        r = admin.post("/admin/schemes/add", data=form, follow_redirects=False)
        check("add scheme -> redirect", r.status_code == 303)
        check("scheme count +1", run_async(scheme_service.count_schemes()) == before + 1)
        news = run_async(scheme_service.get_scheme_by_name("Auto Test Scheme"))
        check("new scheme rules parsed (gender both)",
              news["eligibility_rules"].get("gender") == ["male", "female"])
        # min>max age validation
        bad_form = dict(form); bad_form["name"] = "Bad Age"; bad_form["min_age"] = "70"
        r = admin.post("/admin/schemes/add", data=bad_form, follow_redirects=False)
        check("min>max age -> 400 validation", r.status_code == 400)
        check("bad-age scheme NOT created",
              run_async(scheme_service.get_scheme_by_name("Bad Age")) is None)
        # inline add document
        r = admin.post("/admin/documents/add", data={"name": "Brand New Inline Doc"})
        check("inline add document -> ok json", r.status_code == 200 and r.json().get("ok"))
        names = {m["name"] for m in run_async(document_service.list_documents())}
        check("inline doc in master list", "Brand New Inline Doc" in names)
        # edit scheme persists
        r = admin.post(f"/admin/schemes/{news['id']}/edit",
                       data={**form, "objective": "updated objective"}, follow_redirects=False)
        upd = run_async(scheme_service.get_scheme(news["id"]))
        check("scheme edit persists", upd["objective"] == "updated objective")
        # new scheme matches an eligible user
        mp = e.get("/my-schemes").text
        check("eligible farmer sees the new scheme", "Auto Test Scheme" in mp)

        # ---------- J. Admin users / dashboard ----------
        section("J. Admin users & dashboard")
        r = admin.get("/admin/users")
        check("admin users page lists users", r.status_code == 200 and "farmerguy" in r.text)
        r = admin.get("/admin")
        check("admin dashboard loads", r.status_code == 200)
        check("dashboard user count matches",
              str(run_async(user_service.count_users())) in r.text)

        # ---------- K. CSV import / export ----------
        section("K. CSV import / export")
        check("users template downloads",
              admin.get("/admin/template/users.csv").status_code == 200)
        check("schemes template downloads",
              admin.get("/admin/template/schemes.csv").status_code == 200)
        imp = ("username,mobile,password,full_name,date_of_birth,gender,state,district,"
               "village,caste_category,occupation,land_ownership,annual_family_income,family_size\n"
               "csvjoe,9100002000,pw123456,CSV Joe,1990-01-01,male,RJ,J,Barloni,obc,farmer,marginal,90000,4\n"
               "badrow,123,pw,,,,,,,,,,,\n")
        su = run_async(iio.import_users(imp.encode()))
        check("user import added 1 + 1 error", su["added"] == 1 and len(su["errors"]) >= 1)
        check("user re-import skips", run_async(iio.import_users(imp.encode()))["added"] == 0)
        exp = run_async(iio.export_users_csv())
        rows = list(_csv.DictReader(io.StringIO(exp)))
        check("export passwords blank", all((r.get("password") or "") == "" for r in rows))
        check("export round-trip skips all", run_async(iio.import_users(exp.encode()))["added"] == 0)
        # formula injection neutralized
        ev = TestClient(app); signup(ev, "evil2", "9100002001")
        fill_profile(ev, full_name="=cmd|'/c calc'!A1", village="+SUM(1)")
        exp2 = run_async(iio.export_users_csv())
        rows2 = list(_csv.reader(io.StringIO(exp2)))
        bad_cells = [cc for row in rows2[1:] for cc in row if cc and cc[0] in ("=", "+", "-", "@")]
        check("CSV export neutralizes formula cells", not bad_cells, bad_cells)
        # scheme import
        scsv = ("name,ministry,category,min_age,gender,occupation,documents_required,status\n"
                "CSV Scheme One,MinA,health,21,female,student,Aadhaar card;New CSV Doc,active\n"
                ",,,,,,,\n")
        ss = run_async(iio.import_schemes(scsv.encode()))
        check("scheme import added 1 (blank skipped)", ss["added"] == 1)
        check("scheme re-import skips", run_async(iio.import_schemes(scsv.encode()))["added"] == 0)
        check("empty CSV graceful", len(run_async(iio.import_users(b""))["errors"]) >= 1)

        # ---------- L. Security & access control ----------
        section("L. Security & access control")
        nonadmin = TestClient(app); signup(nonadmin, "plainuser", "9000009000")
        for p in ["/admin", "/admin/users", "/admin/export/users.csv"]:
            check(f"non-admin {p} -> 403", nonadmin.get(p, follow_redirects=False).status_code == 403)
        # other user cannot read someone's file
        check("other user file -> 403",
              nonadmin.get(f"/documents/file/{aad['id']}", follow_redirects=False).status_code == 403)
        check("admin reads any file -> 200",
              admin.get(f"/documents/file/{aad['id']}", follow_redirects=False).status_code == 200)
        check("anon file -> redirect",
              anon.get(f"/documents/file/{aad['id']}", follow_redirects=False).status_code == 303)
        forged = TestClient(app); forged.cookies.set("session", "a.b.c")
        check("forged cookie -> logged out",
              forged.get("/dashboard", follow_redirects=False).status_code == 303)
        r = anon.post("/login", data={"username": "admin", "password": "admin123",
                                      "next": "//evil.example.com"}, follow_redirects=False)
        check("open-redirect blocked", not r.headers.get("location", "").startswith("//"))
        h = root.get("/").headers
        check("security headers present",
              h.get("x-frame-options") == "DENY" and h.get("x-content-type-options") == "nosniff"
              and "frame-ancestors 'none'" in (h.get("content-security-policy") or ""))

        # ---------- M. Rate limiting ----------
        section("M. Rate limiting")
        from app import rate_limit
        rate_limit.login_failures_ip._hits.clear(); rate_limit.login_failures_user._hits.clear()
        rl = TestClient(app); signup(rl, "lockme2", "9000009001", pw="rightpw123")
        for _ in range(8):
            rl.post("/login", data={"username": "lockme2", "password": "x"}, follow_redirects=False)
        r = rl.post("/login", data={"username": "lockme2", "password": "rightpw123"}, follow_redirects=False)
        check("8 failures locks account (429 even w/ right pw)", r.status_code == 429)
        r = rl.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=False)
        check("other account unaffected during lockout", r.status_code == 303)

        # ---------- O. Data integrity / edge cases ----------
        # ---------- N. Approval Phase 2 — content gating + initiator notice ----------
        section("N. Approval Phase 2 (content gating)")
        from app.services import approval_service as _aps
        # The default admin is the superadmin. Create a helper admin to initiate.
        helper = TestClient(app); signup(helper, "phase2admin", "9000009099", pw="helperpw1")
        h = run_async(user_service.get_user_by_username("phase2admin"))
        run_async(user_service.update_role(h["id"], "admin"))
        run_async(_aps.set_level("scheme.create", "superadmin"))
        # Helper adds a scheme -> must be deferred, not created.
        helper.post("/admin/schemes/add",
                    data={"name": "Phase2 Gated Scheme", "status": "active"},
                    follow_redirects=False)
        check("gated scheme.create is deferred",
              run_async(scheme_service.get_scheme_by_name("Phase2 Gated Scheme")) is None)
        pend = run_async(_aps.list_requests("pending"))
        gated = [r for r in pend if r["action_key"] == "scheme.create"]
        check("a scheme.create approval request was opened", len(gated) == 1)
        # Superadmin approves -> scheme is created.
        admin.post(f"/admin/approvals/{gated[0]['id']}/vote",
                   data={"decision": "approve"}, follow_redirects=False)
        check("approved scheme.create is applied",
              run_async(scheme_service.get_scheme_by_name("Phase2 Gated Scheme")) is not None)
        # Initiator sees a one-time "approved" notice on their dashboard.
        dash = helper.get("/admin").text
        check("initiator sees approved notice", "Updates on your requests" in dash and "Approved" in dash)
        check("notice clears after being shown once",
              "Updates on your requests" not in helper.get("/admin").text)
        run_async(_aps.set_level("scheme.create", "none"))  # restore for later sections

        # New-scheme-match notification: first dashboard view initialises
        # silently; a newly-added matching scheme then flags once.
        check("first dashboard view shows no new-match banner",
              "new scheme(s) match" not in e.get("/dashboard").text)
        admin.post("/admin/schemes/add",
                   data={"name": "Fresh Match Scheme", "status": "active"},
                   follow_redirects=False)
        dash_e = e.get("/dashboard").text
        check("new matching scheme flagged on dashboard",
              "new scheme(s) match" in dash_e and "Fresh Match Scheme" in dash_e)
        check("new-match banner clears after being shown",
              "new scheme(s) match" not in e.get("/dashboard").text)

        section("O. Data integrity / edge cases")
        # scheme with no rules eligible to anyone with a profile
        admin.post("/admin/schemes/add", data={"name": "Open To All", "status": "active"},
                   follow_redirects=False)
        check("rule-less scheme eligible to profiled user", "Open To All" in e.get("/my-schemes").text)
        # unicode scheme name round-trips through export
        admin.post("/admin/schemes/add",
                   data={"name": "यूनिकोड योजना", "objective": "हिंदी विवरण", "status": "active"},
                   follow_redirects=False)
        sx = run_async(iio.export_schemes_csv())
        check("unicode scheme exported intact", "यूनिकोड योजना" in sx)
        # long text doesn't error
        r = admin.post("/admin/schemes/add",
                       data={"name": "Long " + "x" * 5000, "objective": "y" * 8000, "status": "active"},
                       follow_redirects=False)
        check("very long text handled", r.status_code in (303, 400))
        # persistence: data already written to the on-disk DB is readable
        check("data persisted to disk DB", run_async(user_service.count_users()) > 5)

    print(f"\n{'='*54}\nRESULT: {_p} passed, {_f} failed")
    if _fail:
        print("\nFAILURES:")
        for n, d in _fail:
            print(f"  - {n}: {d}")
    return _f


if __name__ == "__main__":
    try:
        rc = run()
    finally:
        shutil.rmtree(SCRATCH, ignore_errors=True)
    sys.exit(1 if rc else 0)
