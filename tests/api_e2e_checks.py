"""End-to-end API tests — exercises the app exactly as the frontend does.

Unlike the other suites, this one boots a REAL uvicorn server on an isolated
scratch database and drives it over actual HTTP with an httpx client: form
posts, multipart uploads, cookies, redirects. Outcomes are verified only
through the API — by reading pages back and following the same links / IDs a
browser would click — never by touching the database or service layer.
"""
import os
import re
import socket
import subprocess
import sys
import tempfile
import shutil
import time

import httpx

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_p = _f = 0
_fail = []
def check(name, cond, detail=""):
    global _p, _f
    if cond:
        _p += 1; print(f"  PASS  {name}")
    else:
        _f += 1; _fail.append((name, detail)); print(f"  FAIL  {name}  -- {detail}")
def section(t): print(f"\n=== {t} ===")

PNG = bytes.fromhex("89504e470d0a1a0a") + b"\x00" * 64


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def start_server(port, db_path):
    env = dict(os.environ)
    env.update({
        "DATABASE_PATH": db_path,
        "SEED_USERS_CSV": "",
        "SECRET_KEY": "e2e-test-secret",
        "ADMIN_USERNAME": "admin",
        "ADMIN_PASSWORD": "admin123",
        "ADMIN_MOBILE": "9999999999",
        "PYTHONPATH": ROOT,
    })
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=ROOT, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    for _ in range(80):  # up to ~20s
        if proc.poll() is not None:
            raise RuntimeError("server process exited during startup")
        try:
            httpx.get(base + "/", timeout=1.0)
            return proc
        except Exception:
            time.sleep(0.25)
    proc.terminate()
    raise RuntimeError("server did not become ready")


def new_client(base):
    # follow_redirects=False so we can assert on 303 Location like a browser nav
    return httpx.Client(base_url=base, follow_redirects=False, timeout=10.0)


def signup(cli, u, m, pw="secret123"):
    return cli.post("/signup", data={"username": u, "mobile": m,
                    "password": pw, "confirm_password": pw})

def fill_profile(cli, **over):
    base = {"full_name": "API User", "date_of_birth": "1980-01-01",
            "gender": "male", "state": "Rajasthan", "district": "Jaipur",
            "village": "Barloni", "caste_category": "obc",
            "annual_family_income": "100000", "occupation": "farmer",
            "land_ownership": "marginal", "land_area_acres": "2",
            "family_size": "5", "bank_account_aadhaar_linked": "on"}
    base.update(over)
    return cli.post("/profile/edit", data=base)

def first_int(pattern, text, default=None):
    m = re.search(pattern, text)
    return int(m.group(1)) if m else default


def run(base):
    # ---------- Public browse (anonymous) ----------
    section("Public API (anonymous)")
    anon = new_client(base)
    home = anon.get("/")
    check("GET / -> 200", home.status_code == 200)
    check("static assets are cache-busted (?v=)",
          "main.js?v=" in home.text and "style.css?v=" in home.text)
    r = anon.get("/schemes")
    check("GET /schemes lists schemes", r.status_code == 200 and "PM-KISAN" in r.text)
    r = anon.get("/schemes", params={"q": "MGNREGA"})
    check("GET /schemes?q= filters", "MGNREGA" in r.text and "PM-KISAN" not in r.text)
    r = anon.get("/schemes", params={"category": "health"})
    check("GET /schemes?category=health", "Ayushman" in r.text)
    sid = first_int(r'href="/schemes/(\d+)"', anon.get("/schemes").text)
    check("found a scheme id on the page", sid is not None, "no scheme link")
    check("GET /schemes/{id} detail", anon.get(f"/schemes/{sid}").status_code == 200)
    check("GET /schemes/999999 -> 404", anon.get("/schemes/999999").status_code == 404)
    r = anon.get("/dashboard")
    check("GET /dashboard anon -> 303 login",
          r.status_code == 303 and "/login" in r.headers.get("location", ""))

    # ---------- Signup / login / session ----------
    section("Auth API")
    user = new_client(base)
    r = signup(user, "apifarmer", "9000010001")
    check("POST /signup -> 303 dashboard + cookie",
          r.status_code == 303 and "/dashboard" in r.headers.get("location", "")
          and "session" in r.headers.get("set-cookie", ""))
    check("GET /dashboard now 200 (logged in)", user.get("/dashboard").status_code == 200)
    check("POST /signup bad mobile -> 400", signup(new_client(base), "badm", "123").status_code == 400)
    check("POST /signup dup username -> 400", signup(new_client(base), "apifarmer", "9000010099").status_code == 400)
    # logout clears session
    user.get("/logout")
    check("after logout /dashboard -> 303", user.get("/dashboard").status_code == 303)
    # log back in via the login form
    r = user.post("/login", data={"username": "apifarmer", "password": "secret123"})
    check("POST /login good creds -> 303", r.status_code == 303)
    check("POST /login wrong pw -> 401",
          user.post("/login", data={"username": "apifarmer", "password": "x"}).status_code == 401)
    # need a clean session (the bad attempt above doesn't drop it)
    user.post("/login", data={"username": "apifarmer", "password": "secret123"})

    # ---------- Profile + eligibility ----------
    section("Profile & eligibility API")
    r = fill_profile(user, occupation="farmer")
    check("POST /profile/edit first time -> 303", r.status_code == 303)
    page = user.get("/my-schemes")
    check("GET /my-schemes shows PM-KISAN", page.status_code == 200 and "PM-KISAN" in page.text)
    check("farmer not shown female-only Sukanya", "Sukanya" not in page.text)
    # second edit -> change request (303 to /profile)
    r = fill_profile(user, annual_family_income="80000")
    check("2nd /profile/edit -> 303 (change request)", r.status_code == 303)
    prof = user.get("/profile").text
    check("GET /profile reflects a pending change", "pending" in prof.lower() or "change" in prof.lower())

    # ---------- Document locker (multipart, as the form does) ----------
    section("Document locker API")
    r = user.post("/documents",
                  data={"document_name": "Aadhaar card", "doc_number": "1234-5678"},
                  files={"file": ("scan.png", PNG, "image/png")})
    check("POST /documents upload -> 303", r.status_code == 303)
    docs_page = user.get("/documents").text
    check("GET /documents lists the Aadhaar (Pending)",
          "Aadhaar card" in docs_page and "Pending" in docs_page)
    doc_file_id = first_int(r'href="/documents/file/(\d+)"', docs_page)
    check("found document file link id", doc_file_id is not None, "no file link")
    fr = user.get(f"/documents/file/{doc_file_id}")
    check("owner GET /documents/file/{id} -> 200", fr.status_code == 200)
    cd = fr.headers.get("content-disposition", "")
    check("file served inline with friendly name (no UUID/PII)",
          "inline" in cd and "Aadhaar-card" in cd and "API-User" in cd)
    # a different logged-in user must NOT read it
    other = new_client(base); signup(other, "nosyuser", "9000010002")
    check("other user GET that file -> 403",
          other.get(f"/documents/file/{doc_file_id}").status_code == 403)
    check("anon GET that file -> 303 login",
          new_client(base).get(f"/documents/file/{doc_file_id}").status_code == 303)
    r = user.post("/documents",
                  data={"document_name": "Aadhaar card", "doc_number": "x"},
                  files={"file": ("bad.exe", b"MZ", "application/octet-stream")})
    check("POST /documents bad ext -> 400", r.status_code == 400)

    # ---------- Admin flows ----------
    section("Admin API")
    admin = new_client(base)
    r = admin.post("/login", data={"username": "admin", "password": "admin123"})
    check("admin POST /login -> 303", r.status_code == 303)
    check("GET /admin -> 200", admin.get("/admin").status_code == 200)
    # non-admin hitting admin -> 403
    check("non-admin GET /admin -> 403", user.get("/admin").status_code == 403)
    check("admin reads user's file -> 200",
          admin.get(f"/documents/file/{doc_file_id}").status_code == 200)

    # change-request review: find id from the listing, approve, verify via user API
    cr_page = admin.get("/admin/change-requests").text
    cr_id = first_int(r'href="/admin/change-requests/(\d+)"', cr_page)
    check("found a change-request id", cr_id is not None, cr_page[:200])
    r = admin.post(f"/admin/change-requests/{cr_id}/approve")
    check("POST approve change-request -> 303", r.status_code == 303)
    prof = user.get("/profile").text
    check("user profile shows approved income 80000", "80000" in prof or "80,000" in prof)

    # document review: approve the pending Aadhaar, verify it counts on a scheme page
    dr_page = admin.get("/admin/document-requests").text
    dr_id = first_int(r'action="/admin/document-requests/(\d+)/approve"', dr_page)
    check("found a document-request id", dr_id is not None, dr_page[:200])
    check("POST approve document -> 303",
          admin.post(f"/admin/document-requests/{dr_id}/approve").status_code == 303)

    # inline add-document (exactly as main.js fetch does: urlencoded, JSON back)
    r = admin.post("/admin/documents/add", data={"name": "API Added Doc"},
                   headers={"Content-Type": "application/x-www-form-urlencoded"})
    check("POST /admin/documents/add -> JSON ok",
          r.status_code == 200 and r.json().get("ok") and r.json().get("name") == "API Added Doc")

    # add a scheme via the structured form, confirm it appears in the list + public
    scheme_form = {
        "name": "API New Scheme", "ministry": "Min Q", "category": "agriculture",
        "objective": "obj", "benefits": "ben", "how_to_apply": "apply",
        "application_deadline": "ongoing", "status": "active",
        "min_age": "18", "max_age": "65", "max_income": "300000",
        "rule_gender": ["male", "female"], "rule_occupation": ["farmer"],
        "rule_land": ["marginal"], "documents": ["Aadhaar card"],
    }
    r = admin.post("/admin/schemes/add", data=scheme_form)
    check("POST /admin/schemes/add -> 303", r.status_code == 303)
    check("new scheme appears in admin list", "API New Scheme" in admin.get("/admin/schemes").text)
    check("new scheme visible on public browse", "API New Scheme" in anon.get("/schemes").text)
    # min>max age rejected
    bad = dict(scheme_form); bad["name"] = "API Bad Age"; bad["min_age"] = "70"
    check("min>max age -> 400", admin.post("/admin/schemes/add", data=bad).status_code == 400)
    check("bad-age scheme NOT in list", "API Bad Age" not in admin.get("/admin/schemes").text)

    # CSV export/import via the real endpoints
    exp = admin.get("/admin/export/users.csv")
    check("GET export users.csv -> text/csv attachment",
          exp.status_code == 200 and "text/csv" in exp.headers.get("content-type", ""))
    header = exp.text.splitlines()[0].lower()
    pw_idx = header.split(",").index("password")
    rows = [ln.split(",") for ln in exp.text.splitlines()[1:] if ln.strip()]
    check("exported password column all blank",
          all(len(r) <= pw_idx or r[pw_idx] == "" for r in rows))
    imp_csv = ("username,mobile,password,full_name,date_of_birth,gender,state,district,"
               "village,caste_category,occupation,land_ownership,annual_family_income,family_size\n"
               "apicsv,9100010001,pw123456,Api Csv,1990-01-01,male,RJ,J,Barloni,obc,farmer,marginal,90000,4\n")
    r = admin.post("/admin/import/users",
                   files={"file": ("users.csv", imp_csv.encode(), "text/csv")})
    check("POST import users shows added", r.status_code == 200 and ("added" in r.text.lower()))

    # ---------- New features ----------
    section("Multi-upload / approve-all / admin-tab / WhatsApp share")
    # admin tab visibility in the nav
    check("normal user does NOT see Admin tab",
          'href="/admin"' not in user.get("/dashboard").text)
    check("admin DOES see Admin tab", 'href="/admin"' in admin.get("/dashboard").text)

    # upload several documents in one request (parallel document_name/doc_number/file)
    mu = new_client(base)
    signup(mu, "multiup", "9000010004")
    r = mu.post(
        "/documents",
        data={"document_name": ["Aadhaar card", "PAN card"], "doc_number": ["A-1", "P-1"]},
        files=[("file", ("a.png", PNG, "image/png")),
               ("file", ("b.png", PNG, "image/png"))],
    )
    check("multi-upload 2 files in one POST -> 303", r.status_code == 303)
    dp = mu.get("/documents").text
    check("both uploaded docs listed (2)",
          "Your documents (2)" in dp and dp.count("Pending") >= 2)

    # one failing file in a batch is reported, the valid ones still go through
    mu2 = new_client(base)
    signup(mu2, "multiup2", "9000010005")
    r = mu2.post(
        "/documents",
        data={"document_name": ["Aadhaar card", "PAN card"], "doc_number": ["", ""]},
        files=[("file", ("ok.png", PNG, "image/png")),
               ("file", ("bad.exe", b"MZ", "application/octet-stream"))],
    )
    check("partial batch (1 good, 1 bad) still 303", r.status_code == 303)
    dp = mu2.get("/documents").text
    check("only the valid doc was saved (1)", "Your documents (1)" in dp)

    # admin: approve ALL pending at once
    r = admin.post("/admin/document-requests/approve-all")
    check("approve-all -> 303", r.status_code == 303)
    pend = admin.get("/admin/document-requests?status=pending").text
    check("no pending documents remain", "No pending" in pend)
    check("multiup's documents now approved", mu.get("/documents").text.count("Approved") >= 2)

    # WhatsApp share on profile (apifarmer has a profile + an approved Aadhaar)
    pp = user.get("/profile").text
    check("profile shows WhatsApp share button", 'id="waShareBtn"' in pp)
    check("profile embeds share data with the name",
          'id="shareData"' in pp and "API User" in pp)
    check("share data includes approved document file link",
          "documents/file/" in pp)

    # ---------- Complaints module ----------
    section("Complaints (public board, file, track, withdraw)")
    # board is public; filing requires login
    br = anon.get("/complaints")
    check("public complaints board loads",
          br.status_code == 200 and "Community Complaints" in br.text)
    check("anon GET /complaints/new -> 303 login",
          anon.get("/complaints/new").status_code == 303)

    comp = new_client(base)
    signup(comp, "complainer", "9000020001")
    check("GET /complaints/new (auth) -> 200", comp.get("/complaints/new").status_code == 200)
    r = comp.post("/complaints",
                  data={"category": "water", "ward": "Ward 2",
                        "description": "No water supply for three days in our street."},
                  files={"file": ("issue.png", PNG, "image/png")})
    check("file a complaint -> 303", r.status_code == 303)
    cid = first_int(r"/complaints/(\d+)", r.headers.get("location", ""))
    check("redirected to the new complaint", cid is not None, r.headers.get("location"))

    det = anon.get(f"/complaints/{cid}")
    check("public detail loads", det.status_code == 200 and "No water supply" in det.text)
    check("public detail hides filer identity", "complainer" not in det.text)
    check("complaint starts as Submitted", "Submitted" in det.text)
    check("complaint photo served publicly -> 200",
          anon.get(f"/complaints/{cid}/photo").status_code == 200)
    br = anon.get("/complaints")
    check("complaint shown on public board", ("#%d" % cid) in br.text)
    check("public board hides filer identity", "complainer" not in br.text)
    check("invalid category -> 400",
          comp.post("/complaints", data={"category": "nonsense", "description": "x"}).status_code == 400)
    check("my complaints lists it",
          ("#%d" % cid) in comp.get("/my/complaints").text)

    # admin sees the filer and can move it through statuses
    ac = admin.get("/admin/complaints")
    check("admin list shows filer identity", ac.status_code == 200 and "complainer" in ac.text)
    check("admin complaint detail shows filer",
          "complainer" in admin.get(f"/admin/complaints/{cid}").text)
    r = admin.post(f"/admin/complaints/{cid}/status",
                   data={"status": "in_progress", "note": "Sent to water dept"})
    check("admin status update -> 303", r.status_code == 303)
    det = anon.get(f"/complaints/{cid}")
    check("public detail reflects new status", "In progress" in det.text)
    check("status note recorded in history", "Sent to water dept" in det.text)

    # withdraw a fresh (submitted) complaint
    r = comp.post("/complaints", data={"category": "roads", "description": "Pothole on main road."})
    cid2 = first_int(r"/complaints/(\d+)", r.headers.get("location", ""))
    check("withdraw own submitted complaint -> 303",
          comp.post(f"/complaints/{cid2}/withdraw").status_code == 303)
    check("withdrawn status shown", "Withdrawn" in anon.get(f"/complaints/{cid2}").text)
    check("admin dashboard shows open-complaints stat",
          "Open complaints" in admin.get("/admin").text)

    # ---------- Security ----------
    section("Security (HTTP)")
    h = anon.get("/").headers
    check("security headers present",
          h.get("x-frame-options") == "DENY" and h.get("x-content-type-options") == "nosniff"
          and "frame-ancestors 'none'" in (h.get("content-security-policy") or ""))
    r = new_client(base).post("/login",
                              data={"username": "admin", "password": "admin123",
                                    "next": "//evil.example.com"})
    check("open-redirect blocked (next=//evil)",
          not r.headers.get("location", "").startswith("//"))
    # rate limit: 8 bad logins on one account -> 9th is 429
    rl = new_client(base)
    signup(rl, "ratetest", "9000010003", pw="rightpw123")
    rl.get("/logout")
    for _ in range(8):
        rl.post("/login", data={"username": "ratetest", "password": "nope"})
    r = rl.post("/login", data={"username": "ratetest", "password": "rightpw123"})
    check("8 bad logins -> account locked (429)", r.status_code == 429)

    print(f"\n{'=' * 54}\nRESULT: {_p} passed, {_f} failed")
    if _fail:
        print("\nFAILURES:")
        for n, d in _fail:
            print(f"  - {n}: {d}")
    return _f


def main():
    scratch = tempfile.mkdtemp(prefix="gramseva-e2e-")
    port = free_port()
    proc = None
    try:
        proc = start_server(port, os.path.join(scratch, "e2e.db"))
        rc = run(f"http://127.0.0.1:{port}")
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
        shutil.rmtree(scratch, ignore_errors=True)
    return rc


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
