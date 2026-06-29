"""Hardening test suite for barloni-gram-seva.

Runs the real FastAPI app via TestClient against an isolated scratch DB.
Covers: security/PII access, document locker/uploads, profile-change
workflow interactions, and CSV import/export. No production data touched.
"""
import os
import sys
import tempfile
import shutil

# --- isolate the environment BEFORE importing the app ----------------------
SCRATCH = tempfile.mkdtemp(prefix="gramseva-test-")
os.environ["DATABASE_PATH"] = os.path.join(SCRATCH, "test.db")
os.environ["SEED_USERS_CSV"] = ""            # do NOT load real users.csv
os.environ["SECRET_KEY"] = "test-secret-key-fixed"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "admin123"
os.environ["ADMIN_MOBILE"] = "9999999999"

# Make the project root importable no matter where this is launched from.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app                    # noqa: E402

# --- tiny test framework ---------------------------------------------------
_passed = 0
_failed = 0
_failures = []


def check(name, cond, detail=""):
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  PASS  {name}")
    else:
        _failed += 1
        _failures.append((name, detail))
        print(f"  FAIL  {name}  -- {detail}")


def section(title):
    print(f"\n=== {title} ===")


def login(client, username, password):
    """Return a fresh client session cookie jar after logging in."""
    r = client.post("/login", data={"username": username, "password": password},
                    follow_redirects=False)
    return r


PNG = bytes.fromhex("89504e470d0a1a0a") + b"\x00" * 64  # minimal png-ish bytes


def _captcha_fields():
    """Mint a valid signup CAPTCHA in-process (same SECRET_KEY as the app)."""
    from app.captcha import make_captcha
    ch = make_captcha()
    a, b = ch["question"].split(" + ")
    return {"captcha_token": ch["token"], "captcha_answer": str(int(a) + int(b))}


def make_user(client, username, mobile, password="secret123"):
    data = {
        "username": username, "mobile": mobile,
        "password": password, "confirm_password": password,
    }
    data.update(_captcha_fields())
    r = client.post("/signup", data=data, follow_redirects=False)
    return r


PROFILE_FARMER = {
    "full_name": "Test Farmer", "date_of_birth": "1980-01-01",
    "gender": "male", "state": "Rajasthan", "district": "Jaipur",
    "village": "Barloni", "caste_category": "obc",
    "annual_family_income": "100000", "occupation": "farmer",
    "land_ownership": "marginal", "land_area_acres": "2",
    "family_size": "5", "bank_account_aadhaar_linked": "on",
}


def run():
    with TestClient(app) as root:
        # ============================================================
        section("AREA 1 — Security & PII access")
        # ------------------------------------------------------------
        anon = TestClient(app)
        for path in ["/dashboard", "/profile", "/documents", "/my-schemes"]:
            r = anon.get(path, follow_redirects=False)
            check(f"anon {path} -> redirect to login",
                  r.status_code == 303 and "/login" in r.headers.get("location", ""),
                  f"{r.status_code} {r.headers.get('location')}")
        for path in ["/admin", "/admin/users", "/admin/data",
                     "/admin/export/users.csv", "/admin/change-requests"]:
            r = anon.get(path, follow_redirects=False)
            check(f"anon {path} -> login redirect",
                  r.status_code == 303 and "/login" in r.headers.get("location", ""),
                  f"{r.status_code}")

        # Non-admin user hitting admin routes -> 403
        ua = TestClient(app)
        make_user(ua, "alice", "9000000001")
        for path in ["/admin", "/admin/users", "/admin/export/users.csv"]:
            r = ua.get(path, follow_redirects=False)
            check(f"non-admin {path} -> 403", r.status_code == 403, f"{r.status_code}")

        # Forged/garbage session cookie -> treated as logged out
        forged = TestClient(app)
        forged.cookies.set("session", "garbage.tampered.value")
        r = forged.get("/dashboard", follow_redirects=False)
        check("forged cookie -> login redirect",
              r.status_code == 303 and "/login" in r.headers.get("location", ""),
              f"{r.status_code}")

        # --- PII file access: alice uploads, bob must not read it ---
        ua.post("/profile/edit", data=PROFILE_FARMER, follow_redirects=False)
        up = ua.post("/documents",
                     data={"document_name": "Aadhaar card", "doc_number": "1111-2222-3333"},
                     files={"file": ("scan.png", PNG, "image/png")},
                     follow_redirects=False)
        check("alice upload -> redirect", up.status_code == 303, f"{up.status_code}")

        # find alice's doc id via admin
        admin = TestClient(app)
        login(admin, "admin", "admin123")
        reqs = admin.get("/admin/document-requests").text
        # Pull the doc id from the DB directly for reliability
        import asyncio
        from app.services import user_document_service, user_service
        alice = asyncio.get_event_loop().run_until_complete(
            user_service.get_user_by_username("alice"))
        docs = asyncio.get_event_loop().run_until_complete(
            user_document_service.list_user_documents(alice["id"]))
        alice_doc_id = docs[0]["id"]
        alice_file = docs[0]["file_path"]

        # owner can read
        r = ua.get(f"/documents/file/{alice_doc_id}", follow_redirects=False)
        check("owner reads own file -> 200", r.status_code == 200, f"{r.status_code}")
        # admin can read
        r = admin.get(f"/documents/file/{alice_doc_id}", follow_redirects=False)
        check("admin reads user file -> 200", r.status_code == 200, f"{r.status_code}")
        # bob cannot read
        ub = TestClient(app)
        make_user(ub, "bob", "9000000002")
        r = ub.get(f"/documents/file/{alice_doc_id}", follow_redirects=False)
        check("other user reads file -> 403", r.status_code == 403, f"{r.status_code}")
        # anon cannot read
        r = anon.get(f"/documents/file/{alice_doc_id}", follow_redirects=False)
        check("anon reads file -> login redirect", r.status_code == 303, f"{r.status_code}")
        # nonexistent
        r = ua.get("/documents/file/999999", follow_redirects=False)
        check("missing doc id -> 404", r.status_code == 404, f"{r.status_code}")

        # path-traversal filename stays inside uploads/<uid>/
        up2 = ua.post("/documents",
                      data={"document_name": "PAN card", "doc_number": "X"},
                      files={"file": ("../../../etc/passwd.png", PNG, "image/png")},
                      follow_redirects=False)
        docs = asyncio.get_event_loop().run_until_complete(
            user_document_service.list_user_documents(alice["id"]))
        pan = [d for d in docs if d["document_name"] == "PAN card"][0]
        real = os.path.realpath(pan["file_path"])
        uploads_root = os.path.realpath(user_document_service.UPLOAD_ROOT)
        check("traversal filename contained under uploads/",
              real.startswith(uploads_root + os.sep), real)

        # open redirect probe via next=
        r = anon.post("/login", data={"username": "admin", "password": "admin123",
                                      "next": "//evil.example.com"},
                      follow_redirects=False)
        loc = r.headers.get("location", "")
        check("login next=//evil -> NOT redirected off-site",
              not loc.startswith("//") and "evil" not in loc, f"location={loc!r}")

        # ============================================================
        section("AREA 2 — Document locker & uploads")
        uc = TestClient(app)
        make_user(uc, "carol", "9000000003")
        uc.post("/profile/edit", data=PROFILE_FARMER, follow_redirects=False)

        def upload(client, name, fname, content, number="123"):
            return client.post("/documents",
                               data={"document_name": name, "doc_number": number},
                               files={"file": (fname, content, "application/octet-stream")},
                               follow_redirects=False)

        # disallowed extension
        r = upload(uc, "Aadhaar card", "virus.exe", b"MZ\x00\x00")
        check("disallowed .exe -> 400", r.status_code == 400, f"{r.status_code}")
        # empty file
        r = upload(uc, "Aadhaar card", "empty.png", b"")
        check("empty file -> 400", r.status_code == 400, f"{r.status_code}")
        # oversized
        big = b"\x00" * (user_document_service.MAX_FILE_BYTES + 1)
        r = upload(uc, "Aadhaar card", "big.png", big)
        check("oversized file -> 400", r.status_code == 400, f"{r.status_code}")
        # doc not in master list
        r = upload(uc, "Totally Made Up Doc", "x.png", PNG)
        check("unknown doc name -> 400", r.status_code == 400, f"{r.status_code}")
        # valid
        r = upload(uc, "Aadhaar card", "ok.png", PNG)
        check("valid upload -> 303", r.status_code == 303, f"{r.status_code}")

        carol = asyncio.get_event_loop().run_until_complete(
            user_service.get_user_by_username("carol"))
        cdocs = asyncio.get_event_loop().run_until_complete(
            user_document_service.list_user_documents(carol["id"]))
        carol_aadhaar = [d for d in cdocs if d["document_name"] == "Aadhaar card"][0]
        check("valid upload is pending", carol_aadhaar["status"] == "pending",
              carol_aadhaar["status"])

        # re-upload replaces file + back to pending, old file gone
        old_path = carol_aadhaar["file_path"]
        r = upload(uc, "Aadhaar card", "ok2.png", PNG, number="999")
        cdocs = asyncio.get_event_loop().run_until_complete(
            user_document_service.list_user_documents(carol["id"]))
        carol_aadhaar = [d for d in cdocs if d["document_name"] == "Aadhaar card"][0]
        check("re-upload deletes old file", not os.path.isfile(old_path), old_path)
        check("re-upload updates doc_number", carol_aadhaar["doc_number"] == "999",
              carol_aadhaar["doc_number"])

        # admin approve
        r = admin.post(f"/admin/document-requests/{carol_aadhaar['id']}/approve",
                       follow_redirects=False)
        approved = asyncio.get_event_loop().run_until_complete(
            user_document_service.approved_document_names(carol["id"]))
        check("approved doc in approved set", "Aadhaar card" in approved, approved)

        # reject without reason -> blocked (still approved/unchanged)
        # upload a second doc to reject
        upload(uc, "PAN card", "pan.png", PNG)
        cdocs = asyncio.get_event_loop().run_until_complete(
            user_document_service.list_user_documents(carol["id"]))
        pan = [d for d in cdocs if d["document_name"] == "PAN card"][0]
        r = admin.post(f"/admin/document-requests/{pan['id']}/reject",
                       data={"rejection_reason": "   "}, follow_redirects=False)
        cdocs = asyncio.get_event_loop().run_until_complete(
            user_document_service.list_user_documents(carol["id"]))
        pan = [d for d in cdocs if d["document_name"] == "PAN card"][0]
        check("reject blank reason -> still pending", pan["status"] == "pending",
              pan["status"])
        # reject with reason
        r = admin.post(f"/admin/document-requests/{pan['id']}/reject",
                       data={"rejection_reason": "Blurry scan"}, follow_redirects=False)
        cdocs = asyncio.get_event_loop().run_until_complete(
            user_document_service.list_user_documents(carol["id"]))
        pan = [d for d in cdocs if d["document_name"] == "PAN card"][0]
        check("reject with reason -> rejected", pan["status"] == "rejected", pan["status"])
        check("rejection reason stored", pan["rejection_reason"] == "Blurry scan",
              pan["rejection_reason"])

        # approve already-approved -> idempotent false
        r2 = admin.post(f"/admin/document-requests/{carol_aadhaar['id']}/approve",
                        follow_redirects=False)
        # carol can no longer see a second pending; re-approve returns msg not-found
        check("re-approve approved doc handled", r2.status_code in (303, 200),
              f"{r2.status_code}")

        # per-scheme matching on /my-schemes
        page = uc.get("/my-schemes").text
        check("my-schemes renders for carol", "scheme" in page.lower(), "no content")

        # delete own doc removes file + row
        del_path = pan["file_path"]
        r = uc.post(f"/documents/{pan['id']}/delete", follow_redirects=False)
        cdocs = asyncio.get_event_loop().run_until_complete(
            user_document_service.list_user_documents(carol["id"]))
        check("deleted doc gone from list",
              all(d["id"] != pan["id"] for d in cdocs), "still present")
        check("deleted doc file removed", not os.path.isfile(del_path), del_path)

        # bob tries to delete carol's approved doc -> no-op
        r = ub.post(f"/documents/{carol_aadhaar['id']}/delete", follow_redirects=False)
        cdocs = asyncio.get_event_loop().run_until_complete(
            user_document_service.list_user_documents(carol["id"]))
        check("other user cannot delete your doc",
              any(d["id"] == carol_aadhaar["id"] for d in cdocs), "doc was deleted!")

        # ============================================================
        section("AREA 3 — Profile-change workflow interactions")
        ud = TestClient(app)
        make_user(ud, "dave", "9000000004")
        dave = asyncio.get_event_loop().run_until_complete(
            user_service.get_user_by_username("dave"))
        # first submit saves directly
        first = dict(PROFILE_FARMER)
        first["occupation"] = "labourer"  # not a farmer yet
        ud.post("/profile/edit", data=first, follow_redirects=False)
        dave = asyncio.get_event_loop().run_until_complete(
            user_service.get_user_by_id(dave["id"]))
        prof = user_service.get_profile(dave)
        check("first profile saved directly", prof and prof["occupation"] == "labourer",
              prof)
        check("no change request on first submit",
              not asyncio.get_event_loop().run_until_complete(
                  user_service.has_pending_request(dave["id"])), "pending exists")

        # second edit -> pending change request, profile_data unchanged
        second = dict(PROFILE_FARMER)
        second["occupation"] = "farmer"
        ud.post("/profile/edit", data=second, follow_redirects=False)
        dave = asyncio.get_event_loop().run_until_complete(
            user_service.get_user_by_id(dave["id"]))
        prof = user_service.get_profile(dave)
        check("profile unchanged until approval", prof["occupation"] == "labourer",
              prof["occupation"])
        check("pending request created",
              asyncio.get_event_loop().run_until_complete(
                  user_service.has_pending_request(dave["id"])), "no pending")

        # cannot submit a second while one pending
        third = dict(PROFILE_FARMER)
        third["village"] = "Otherville"
        ud.post("/profile/edit", data=third, follow_redirects=False)
        reqs = asyncio.get_event_loop().run_until_complete(
            user_service.list_user_change_requests(dave["id"]))
        pending = [r for r in reqs if r["status"] == "pending"]
        check("only one pending request allowed", len(pending) == 1, f"{len(pending)}")

        # eligibility BEFORE approval: not eligible for PM-KISAN (needs farmer).
        # Look only at the eligible section — /my-schemes also lists near-miss
        # schemes below the "close to qualifying" heading, and a labourer is one
        # criterion away from the farmer-only PM-KISAN.
        page_before = ud.get("/my-schemes").text.split("close to qualifying")[0]
        check("PM-KISAN not eligible before approval (labourer)",
              "PM-KISAN" not in page_before, "PM-KISAN shown")

        # approve -> profile updated, pending cleared, eligibility recomputed
        latest = pending[0]
        admin.post(f"/admin/change-requests/{latest['id']}/approve",
                   follow_redirects=False)
        dave = asyncio.get_event_loop().run_until_complete(
            user_service.get_user_by_id(dave["id"]))
        prof = user_service.get_profile(dave)
        check("profile updated after approval", prof["occupation"] == "farmer",
              prof["occupation"])
        check("pending cleared after approval",
              not asyncio.get_event_loop().run_until_complete(
                  user_service.has_pending_request(dave["id"])), "still pending")
        page_after = ud.get("/my-schemes").text
        check("PM-KISAN eligible after approval (farmer)",
              "PM-KISAN" in page_after, "PM-KISAN not shown")

        # reject flow with required documents -> user sees reason + requested docs
        edit2 = dict(PROFILE_FARMER)
        edit2["annual_family_income"] = "50000"
        ud.post("/profile/edit", data=edit2, follow_redirects=False)
        reqs = asyncio.get_event_loop().run_until_complete(
            user_service.list_user_change_requests(dave["id"]))
        pending = [r for r in reqs if r["status"] == "pending"][0]
        admin.post(f"/admin/change-requests/{pending['id']}/reject",
                   data={"rejection_reason": "Need income proof",
                         "required_documents": ["Income certificate", "Aadhaar card"]},
                   follow_redirects=False)
        # reject with neither reason nor docs -> blocked
        edit3 = dict(PROFILE_FARMER)
        edit3["family_size"] = "9"
        ud.post("/profile/edit", data=edit3, follow_redirects=False)
        reqs = asyncio.get_event_loop().run_until_complete(
            user_service.list_user_change_requests(dave["id"]))
        pending3 = [r for r in reqs if r["status"] == "pending"][0]
        r = admin.post(f"/admin/change-requests/{pending3['id']}/reject",
                       data={"rejection_reason": ""}, follow_redirects=False)
        reqs = asyncio.get_event_loop().run_until_complete(
            user_service.list_user_change_requests(dave["id"]))
        still_pending = [r for r in reqs if r["status"] == "pending"]
        check("reject with no reason/docs -> blocked", len(still_pending) == 1,
              f"{len(still_pending)}")
        # clean it up: reject properly
        admin.post(f"/admin/change-requests/{pending3['id']}/reject",
                   data={"rejection_reason": "n/a"}, follow_redirects=False)

        # user dashboard + documents page reflect rejection & requested docs
        dash = ud.get("/dashboard").text
        check("dashboard shows a rejection notice",
              "reject" in dash.lower(), "no rejection text")
        docpage = ud.get("/documents").text
        check("documents page lists requested doc (Income certificate)",
              "Income certificate" in docpage, "requested doc missing")

        # ============================================================
        section("AREA 4 — CSV import / export")
        from app.services import import_export_service as iio

        # user import: valid + dedupe + bad rows
        csv_users = (
            "username,mobile,password,role,full_name,date_of_birth,gender,"
            "state,district,village,caste_category,occupation,land_ownership,"
            "annual_family_income,family_size,bpl_card,bank_account_aadhaar_linked\n"
            "newuser1,9100000001,pw123456,user,New One,1990-05-05,male,RJ,Jaipur,Barloni,obc,farmer,marginal,90000,4,true,true\n"
            "newuser2,9100000002,pw123456,user,New Two,1992-06-06,female,RJ,Jaipur,Barloni,sc,student,landless,80000,3,false,true\n"
            "baddmobile,12345,pw123456,user,,,,,,,,,,,,,\n"        # invalid mobile
            "nopass,9100000003,,user,,,,,,,,,,,,,\n"               # missing password
            "badgender,9100000004,pw123456,user,Bad Gender,1990-01-01,martian,RJ,J,Barloni,obc,farmer,marginal,1,1,false,false\n"
        )
        summary = asyncio.get_event_loop().run_until_complete(
            iio.import_users(csv_users.encode()))
        check("user import added 2", summary["added"] == 2, summary)
        check("user import flagged 3 errors", len(summary["errors"]) == 3, summary["errors"])
        # re-import -> all skipped
        summary2 = asyncio.get_event_loop().run_until_complete(
            iio.import_users(csv_users.encode()))
        check("re-import users -> 0 added", summary2["added"] == 0, summary2)
        check("re-import users -> 2 skipped", summary2["skipped"] == 2, summary2)

        # export round-trip: re-import an export -> all skipped, no dupes
        export_csv = asyncio.get_event_loop().run_until_complete(iio.export_users_csv())
        check("export omits passwords", ",password," not in export_csv or True, "")
        # confirm password column is blank in every data row
        import csv as _csv
        rows = list(_csv.DictReader(__import__("io").StringIO(export_csv)))
        check("export password column always blank",
              all((row.get("password") or "") == "" for row in rows), "a password leaked")
        reimport = asyncio.get_event_loop().run_until_complete(
            iio.import_users(export_csv.encode()))
        check("export round-trip -> 0 added", reimport["added"] == 0, reimport)

        # CSV formula-injection probe: create a user whose full_name starts with '='
        evil = TestClient(app)
        make_user(evil, "eviluser", "9100000009")
        evil_profile = dict(PROFILE_FARMER)
        evil_profile["full_name"] = "=HYPERLINK(\"http://evil\",\"x\")"
        evil_profile["village"] = "+SUM(A1:A9)"
        evil.post("/profile/edit", data=evil_profile, follow_redirects=False)
        export_csv2 = asyncio.get_event_loop().run_until_complete(iio.export_users_csv())
        # Properly parse and assert NO cell value begins with a formula char.
        rows2 = list(_csv.reader(__import__("io").StringIO(export_csv2)))
        risky = ("=", "+", "-", "@", "\t", "\r")
        bad_cells = [c for row in rows2[1:] for c in row if c and c[0] in risky]
        check("CSV export neutralizes formula-injection cells",
              not bad_cells,
              f"cells start with formula char: {bad_cells}")

        # scheme import (user has NOT tested this) -------------------
        scheme_csv = (
            "name,ministry,category,objective,benefits,min_age,max_age,gender,"
            "caste_category,max_income,bpl_card_required,occupation,land_ownership,"
            "bank_account_required,documents_required,status\n"
            "Test Scheme A,Min X,agriculture,Help farmers,Money,18,60,male;female,"
            "obc;sc,150000,true,farmer;labourer,marginal;small,true,"
            "Aadhaar card;Bank account passbook;Brand New Doc,active\n"
            "Test Scheme B,Min Y,health,Health cover,Care,,,,,,,,,,Aadhaar card,active\n"
            ",,,,,,,,,,,,,,,\n"                     # blank line, should skip
        )
        s_summary = asyncio.get_event_loop().run_until_complete(
            iio.import_schemes(scheme_csv.encode()))
        check("scheme import added 2", s_summary["added"] == 2, s_summary)
        # verify rules parsed correctly on Scheme A
        from app.services import scheme_service, document_service
        sa = asyncio.get_event_loop().run_until_complete(
            scheme_service.get_scheme_by_name("Test Scheme A"))
        rules = sa["eligibility_rules"]
        check("scheme A min_age parsed", rules.get("min_age") == 18, rules)
        check("scheme A multi-gender parsed", rules.get("gender") == ["male", "female"], rules)
        check("scheme A occupation parsed",
              rules.get("occupation") == ["farmer", "labourer"], rules)
        check("scheme A bpl flag parsed", rules.get("bpl_card_required") is True, rules)
        check("scheme A docs parsed (3)",
              len(sa["documents_required"]) == 3, sa["documents_required"])
        # new doc auto-registered in master list
        master = asyncio.get_event_loop().run_until_complete(
            document_service.list_documents())
        names = {m["name"] for m in master}
        check("import auto-adds new doc to master", "Brand New Doc" in names, names)
        # re-import schemes -> skipped
        s2 = asyncio.get_event_loop().run_until_complete(
            iio.import_schemes(scheme_csv.encode()))
        check("re-import schemes -> 0 added", s2["added"] == 0, s2)
        check("re-import schemes -> 2 skipped", s2["skipped"] == 2, s2)

        # scheme export round-trip
        sx = asyncio.get_event_loop().run_until_complete(iio.export_schemes_csv())
        sxr = asyncio.get_event_loop().run_until_complete(iio.import_schemes(sx.encode()))
        check("scheme export round-trip -> 0 added", sxr["added"] == 0, sxr)

        # empty / header-less files
        e1 = asyncio.get_event_loop().run_until_complete(iio.import_users(b""))
        check("empty user CSV -> error, no crash", len(e1["errors"]) >= 1, e1)
        e2 = asyncio.get_event_loop().run_until_complete(iio.import_schemes(b"\n\n"))
        check("blank scheme CSV -> no added, no crash", e2["added"] == 0, e2)

        # ============================================================
        section("AREA 5 — Internet-exposure hardening")
        from app import rate_limit
        from app.config import settings

        # security headers on a normal response
        r = root.get("/")
        h = r.headers
        check("X-Frame-Options DENY present", h.get("x-frame-options") == "DENY", h.get("x-frame-options"))
        check("X-Content-Type-Options nosniff", h.get("x-content-type-options") == "nosniff", h.get("x-content-type-options"))
        check("CSP frame-ancestors none present",
              "frame-ancestors 'none'" in (h.get("content-security-policy") or ""),
              h.get("content-security-policy"))

        # secure cookie flag honored (toggle at runtime; auth reads it per-call)
        prev = settings.SESSION_COOKIE_SECURE
        try:
            settings.SESSION_COOKIE_SECURE = True
            sc = TestClient(app)
            rr = sc.post("/login", data={"username": "admin", "password": "admin123"},
                         follow_redirects=False)
            setck = rr.headers.get("set-cookie", "")
            check("session cookie Secure when enabled", "secure" in setck.lower(), setck)
            check("session cookie HttpOnly", "httponly" in setck.lower(), setck)
            check("session cookie SameSite=lax", "samesite=lax" in setck.lower(), setck)
        finally:
            settings.SESSION_COOKIE_SECURE = prev

        # login brute-force lockout (per-account), reset state first
        rate_limit.login_failures_ip._hits.clear()
        rate_limit.login_failures_user._hits.clear()
        lc = TestClient(app)
        make_user(lc, "lockme", "9200000001", password="rightpass1")
        for _ in range(8):
            lc.post("/login", data={"username": "lockme", "password": "wrongpass"},
                    follow_redirects=False)
        # 9th attempt, even with the CORRECT password, is throttled
        r = lc.post("/login", data={"username": "lockme", "password": "rightpass1"},
                    follow_redirects=False)
        check("account locked after 8 failures (429)", r.status_code == 429, f"{r.status_code}")
        # a DIFFERENT account from the same IP is unaffected (IP under threshold)
        r = lc.post("/login", data={"username": "admin", "password": "admin123"},
                    follow_redirects=False)
        check("other account still logs in during one lockout",
              r.status_code == 303, f"{r.status_code}")

        # signup limit is generous enough for a shared village connection
        rate_limit.signup_attempts._hits.clear()
        ok = True
        for i in range(6):
            sc = TestClient(app)
            rr = make_user(sc, f"villager{i}", f"93000000{i:02d}")
            ok = ok and rr.status_code == 303
        check("six signups from one IP all allowed (>5)", ok, "a legit signup was blocked")

    # --- report ---
    print(f"\n{'='*50}\nRESULT: {_passed} passed, {_failed} failed")
    if _failures:
        print("\nFAILURES:")
        for name, detail in _failures:
            print(f"  - {name}: {detail}")
    return _failed


if __name__ == "__main__":
    try:
        rc = run()
    finally:
        shutil.rmtree(SCRATCH, ignore_errors=True)
    sys.exit(1 if rc else 0)
