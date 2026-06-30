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


def _solve_captcha(cli):
    """GET /signup and solve its arithmetic CAPTCHA from the rendered HTML.

    The server runs in a separate process with its own SECRET_KEY, so we can't
    mint a token locally — we read the real challenge the way a browser would.
    """
    html = cli.get("/signup").text
    tok = re.search(r'name="captcha_token" value="([^"]+)"', html)
    nums = re.search(r"What is <strong>(\d+) \+ (\d+)</strong>", html)
    if not tok or not nums:
        return {}
    return {"captcha_token": tok.group(1),
            "captcha_answer": str(int(nums.group(1)) + int(nums.group(2)))}

def signup(cli, u, m, pw="secret123"):
    data = {"username": u, "mobile": m, "password": pw, "confirm_password": pw}
    data.update(_solve_captcha(cli))
    return cli.post("/signup", data=data)

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
    # /my-schemes also lists near-miss schemes below the "close to qualifying"
    # heading; scope the exclusion check to the eligible section above it.
    page_elig = page.text.split("close to qualifying")[0]
    check("GET /my-schemes shows PM-KISAN", page.status_code == 200 and "PM-KISAN" in page_elig)
    check("farmer not shown female-only Sukanya", "Sukanya" not in page_elig)
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
    dl = user.get(f"/documents/file/{doc_file_id}?download=1")
    check("owner can download own document (attachment)",
          dl.status_code == 200 and "attachment" in dl.headers.get("content-disposition", "").lower())
    check("documents page has a real download link (download attr)",
          '?download=1" download' in user.get("/documents").text)
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

    # in-app notification to the filer when status changes
    check("filer dashboard shows a status-update notice",
          "status update" in comp.get("/dashboard").text.lower())
    check("my-complaints flags the updated complaint",
          "Updated" in comp.get("/my/complaints").text)
    comp.get(f"/complaints/{cid}")  # owner views it -> clears the flag
    check("notification cleared after the filer views it",
          "status update" not in comp.get("/dashboard").text.lower())

    # withdraw a fresh (submitted) complaint
    r = comp.post("/complaints", data={"category": "roads", "description": "Pothole on main road."})
    cid2 = first_int(r"/complaints/(\d+)", r.headers.get("location", ""))
    check("withdraw own submitted complaint -> 303",
          comp.post(f"/complaints/{cid2}/withdraw").status_code == 303)
    check("withdrawn status shown", "Withdrawn" in anon.get(f"/complaints/{cid2}").text)
    check("admin dashboard shows open-complaints stat",
          "Open complaints" in admin.get("/admin").text)

    # ward-level analytics
    an = admin.get("/admin/complaints/analytics")
    check("admin analytics loads", an.status_code == 200 and "Complaint Analytics" in an.text)
    check("analytics shows ward breakdown (Ward 2)", "Ward 2" in an.text)
    check("analytics shows category breakdown (Water)", "Water" in an.text)
    check("analytics ward x category matrix present", "Ward × category" in an.text)

    # ---------- Officials & ward routing ----------
    section("Officials, homepage CTA, ward routing")
    home = anon.get("/").text
    check("homepage 'Raise a Complaint' enabled",
          'href="/complaints"' in home and "Coming Soon" not in home)
    check("public /officials page loads", anon.get("/officials").status_code == 200)
    check("Officials in nav", "/officials" in home)
    # realistic starter officials are seeded on first run
    pub0 = anon.get("/officials").text
    check("seeded officials present (Sarpanch + Anganwadi Sevika)",
          "Sarpanch" in pub0 and "Anganwadi Sevika" in pub0)

    def official_id(html, name):
        m = re.search(re.escape(name) + r".*?/admin/officials/(\d+)/edit", html, re.S)
        return int(m.group(1)) if m else None

    # admin creates an official (Ward 2 / water) with a photo
    oname = "E2E Ward2 Water Person"
    r = admin.post("/admin/officials/add",
                   data={"name": oname, "designation": "Ward 2 Member", "level": "3",
                         "ward": "Ward 2", "department": "water", "phone": "9812345678",
                         "email": "e2e@example.com", "office_address": "Panchayat Bhawan",
                         "office_hours": "Mon-Sat 10-5"},
                   files={"photo": ("p.png", PNG, "image/png")})
    check("admin add official -> 303", r.status_code == 303)
    al = admin.get("/admin/officials").text
    oid = official_id(al, oname)
    check("official in admin list", oname in al and oid is not None)
    pub = anon.get("/officials").text
    check("official on public page with phone + email",
          oname in pub and "9812345678" in pub and "e2e@example.com" in pub)
    check("official photo served publicly",
          anon.get(f"/officials/{oid}/photo").status_code == 200)
    r = admin.post(f"/admin/officials/{oid}/edit",
                   data={"name": oname, "designation": "Senior Ward Member",
                         "level": "3", "ward": "Ward 2", "department": "water",
                         "phone": "9812345678", "email": "e2e@example.com"})
    check("edit official -> 303", r.status_code == 303)
    check("edit persisted", "Senior Ward Member" in admin.get("/admin/officials").text)

    # the earlier water/Ward 2 complaint now shows responsible official(s)
    check("complaint detail shows responsible official(s)",
          oname in anon.get(f"/complaints/{cid}").text)

    # officials CSV export / import / template
    exp = admin.get("/admin/officials/export.csv")
    check("officials export CSV includes data",
          exp.status_code == 200 and oname in exp.text and "designation" in exp.text)
    check("officials template downloads",
          admin.get("/admin/officials/template.csv").status_code == 200)
    imp_csv = ("name,designation,level,ward,department,phone,email,office_address,office_hours\n"
               "CSV Imported Officer,Block Officer,2,,other,9700000000,csv@example.com,Block Office,Mon-Fri 10-5\n"
               "Bad Ward Officer,Tester,3,Ward 99,,9700000001,,,\n")
    s_off = admin.post("/admin/officials/import",
                       files={"file": ("officials.csv", imp_csv.encode(), "text/csv")}).text
    check("officials import added 1 + flagged bad ward",
          "Imported 1 official" in s_off and "invalid ward" in s_off)
    check("imported official appears on public page",
          "CSV Imported Officer" in anon.get("/officials").text)
    s_off2 = admin.post("/admin/officials/import",
                        files={"file": ("officials.csv", imp_csv.encode(), "text/csv")}).text
    check("officials re-import skips the duplicate", "skipped 1" in s_off2)
    check("non-admin cannot export officials -> 403",
          user.get("/admin/officials/export.csv").status_code == 403)

    # ward defaults from the filer's profile when left blank
    wu = new_client(base)
    signup(wu, "warduser", "9000020009")
    fill_profile(wu, ward_no="Ward 4")
    check("profile shows ward + mobile",
          "Ward 4" in wu.get("/profile").text and "9000020009" in wu.get("/profile").text)
    r = wu.post("/complaints",
                data={"category": "garbage", "description": "Garbage not collected for a week."})
    wcid = first_int(r"/complaints/(\d+)", r.headers.get("location", ""))
    check("complaint filed without ward -> 303", wcid is not None)
    check("complaint ward defaulted from profile (Ward 4)",
          "Ward 4" in admin.get(f"/admin/complaints/{wcid}").text)

    # delete official
    check("delete official -> 303",
          admin.post(f"/admin/officials/{oid}/delete").status_code == 303)
    check("official removed", "Senior Ward Member" not in admin.get("/admin/officials").text)

    # ---------- Account: password management ----------
    section("Password management & scheme delete")
    pw = new_client(base)
    signup(pw, "pwuser", "9000030001", pw="origpass1")
    check("GET /account -> 200", pw.get("/account").status_code == 200)
    check("change pw with wrong current -> 400",
          pw.post("/account/password", data={"current_password": "WRONG",
                  "new_password": "newpass1", "confirm_password": "newpass1"}).status_code == 400)
    check("change pw too short -> 400",
          pw.post("/account/password", data={"current_password": "origpass1",
                  "new_password": "123", "confirm_password": "123"}).status_code == 400)
    check("change pw mismatch -> 400",
          pw.post("/account/password", data={"current_password": "origpass1",
                  "new_password": "newpass1", "confirm_password": "nope2"}).status_code == 400)
    check("valid password change -> 303",
          pw.post("/account/password", data={"current_password": "origpass1",
                  "new_password": "newpass1", "confirm_password": "newpass1"}).status_code == 303)
    check("old password rejected after change -> 401",
          new_client(base).post("/login", data={"username": "pwuser", "password": "origpass1"}).status_code == 401)
    check("new password works -> 303",
          new_client(base).post("/login", data={"username": "pwuser", "password": "newpass1"}).status_code == 303)

    # admin resets a user's password (recovery path, no email/SMS)
    au = admin.get("/admin/users").text
    m = re.search(r"<td>(\d+)</td>\s*<td>pwuser</td>", au)
    uid = int(m.group(1)) if m else None
    check("found pwuser id in admin users", uid is not None, au[:200])
    check("non-admin cannot reset a password -> 403",
          user.post(f"/admin/users/{uid}/reset-password", data={"new_password": "hacked1"}).status_code == 403)
    check("admin reset too-short -> 303 (no change)",
          admin.post(f"/admin/users/{uid}/reset-password", data={"new_password": "12"}).status_code == 303)
    check("admin reset password -> 303",
          admin.post(f"/admin/users/{uid}/reset-password", data={"new_password": "adminset9"}).status_code == 303)
    check("user can log in with admin-set password",
          new_client(base).post("/login", data={"username": "pwuser", "password": "adminset9"}).status_code == 303)

    # ---------- Scheme delete ----------
    admin.post("/admin/schemes/add", data={"name": "Delete Me Scheme", "status": "active"})
    sl = admin.get("/admin/schemes").text
    m = re.search(r"<td>(\d+)</td>\s*<td>Delete Me Scheme", sl)
    sid_del = int(m.group(1)) if m else None
    check("created a scheme to delete", sid_del is not None)
    check("non-admin cannot delete scheme -> 403",
          user.post(f"/admin/schemes/{sid_del}/delete").status_code == 403)
    check("admin delete scheme -> 303",
          admin.post(f"/admin/schemes/{sid_del}/delete").status_code == 303)
    check("deleted scheme gone from admin list",
          "Delete Me Scheme" not in admin.get("/admin/schemes").text)
    check("deleted scheme gone from public browse",
          "Delete Me Scheme" not in anon.get("/schemes").text)

    # ---------- User management ----------
    section("User management (role / active / delete)")
    mu = new_client(base)
    signup(mu, "manageme", "9000040001", pw="managepw1")
    au = admin.get("/admin/users").text
    muid = int(re.search(r"<td>(\d+)</td>\s*<td>manageme</td>", au).group(1))
    adminid = int(re.search(r"<td>(\d+)</td>\s*<td>admin</td>", au).group(1))

    check("non-admin cannot change roles -> 403",
          user.post(f"/admin/users/{muid}/role", data={"role": "admin"}).status_code == 403)

    # promote -> user gains /admin access; demote -> loses it (role read from DB live)
    check("promote to admin -> 303",
          admin.post(f"/admin/users/{muid}/role", data={"role": "admin"}).status_code == 303)
    madmin = new_client(base)
    madmin.post("/login", data={"username": "manageme", "password": "managepw1"})
    check("promoted user can reach /admin", madmin.get("/admin").status_code == 200)
    check("demote to user -> 303",
          admin.post(f"/admin/users/{muid}/role", data={"role": "user"}).status_code == 303)
    check("demoted user loses /admin access", madmin.get("/admin").status_code == 403)

    # deactivate blocks login; reactivate restores it
    check("deactivate -> 303",
          admin.post(f"/admin/users/{muid}/active", data={"active": "0"}).status_code == 303)
    check("deactivated user cannot log in -> 403",
          new_client(base).post("/login", data={"username": "manageme", "password": "managepw1"}).status_code == 403)
    check("reactivate -> 303",
          admin.post(f"/admin/users/{muid}/active", data={"active": "1"}).status_code == 303)
    check("reactivated user can log in -> 303",
          new_client(base).post("/login", data={"username": "manageme", "password": "managepw1"}).status_code == 303)

    # self / last-admin guards
    admin.post(f"/admin/users/{adminid}/active", data={"active": "0"})
    check("admin cannot deactivate self (still works)", admin.get("/admin").status_code == 200)
    admin.post(f"/admin/users/{adminid}/role", data={"role": "user"})
    check("cannot demote the last admin (still admin)", admin.get("/admin").status_code == 200)
    check("admin cannot delete self",
          admin.post(f"/admin/users/{adminid}/delete").status_code == 303 and admin.get("/admin").status_code == 200)

    # delete a user who has data (exercises the cascade cleanup)
    mu.post("/complaints", data={"category": "roads", "description": "Pothole near manageme's home."})
    check("delete user -> 303",
          admin.post(f"/admin/users/{muid}/delete").status_code == 303)
    check("deleted user gone from admin list", "manageme" not in admin.get("/admin/users").text)
    check("deleted user cannot log in -> 401",
          new_client(base).post("/login", data={"username": "manageme", "password": "managepw1"}).status_code == 401)

    # ---------- Activity log ----------
    section("Admin activity log")
    act = admin.get("/admin/activity")
    check("activity log page loads", act.status_code == 200 and "Activity Log" in act.text)
    # earlier admin actions in this run should be recorded
    check("activity log records a scheme deletion",
          "scheme.delete" in act.text)
    check("activity log records a user deletion",
          "user.delete" in act.text and "manageme" in act.text)
    check("activity log shows the acting admin", "admin" in act.text)
    check("non-admin cannot view activity log -> 403",
          user.get("/admin/activity").status_code == 403)

    # ---------- Help / tour ----------
    section("Help / tour")
    h = anon.get("/help")
    check("public /help loads with resident guide",
          h.status_code == 200 and "How it works" in h.text and "For residents" in h.text)
    check("resident does not see the admin guide", "For admins" not in h.text)
    check("admin sees the admin guide", "For admins" in admin.get("/help").text)
    check("Help link in nav", "/help" in anon.get("/").text)

    # ---------- Superadmin approval engine ----------
    section("Superadmin approval engine")
    su = admin  # the default admin is bootstrapped as the superadmin

    def find_uid(uname):
        m = re.search(r"<td>(\d+)</td>\s*<td>" + re.escape(uname) + r"</td>",
                      su.get("/admin/users").text)
        return int(m.group(1)) if m else None

    def newest_request_id(html):
        m = re.search(r"/admin/approvals/(\d+)/vote", html)
        return int(m.group(1)) if m else None

    check("superadmin can open approval policy",
          su.get("/admin/approval-policy").status_code == 200)

    # two helper admins (promote via the role action; default policy is 'none')
    adminA = new_client(base); signup(adminA, "appadmin_a", "9000050001", pw="adminpw123")
    adminB = new_client(base); signup(adminB, "appadmin_b", "9000050002", pw="adminpw123")
    su.post(f"/admin/users/{find_uid('appadmin_a')}/role", data={"role": "admin"})
    su.post(f"/admin/users/{find_uid('appadmin_b')}/role", data={"role": "admin"})
    check("promoted helper admins reach /admin",
          adminA.get("/admin").status_code == 200 and adminB.get("/admin").status_code == 200)
    check("regular admin cannot open approval policy -> 403",
          adminA.get("/admin/approval-policy").status_code == 403)

    # A regular admin must not be able to manage a SUPERADMIN account
    # (deactivate / delete / reset password) — only another superadmin can.
    suid = find_uid("admin")
    adminA.post(f"/admin/users/{suid}/active", data={"active": "0"})
    check("plain admin cannot deactivate the superadmin",
          su.get("/admin").status_code == 200)
    adminA.post(f"/admin/users/{suid}/delete")
    check("plain admin cannot delete the superadmin",
          su.get("/admin").status_code == 200)
    adminA.post(f"/admin/users/{suid}/reset-password", data={"new_password": "hacked123"})
    check("plain admin cannot reset the superadmin's password",
          new_client(base).post("/login",
              data={"username": "admin", "password": "admin123"}).status_code == 303)

    # policy: deleting a scheme needs a superadmin
    su.post("/admin/approval-policy", data={"level__scheme.delete": "superadmin"})
    su.post("/admin/schemes/add", data={"name": "Gated Scheme A", "status": "active"})
    gsid = int(re.search(r"<td>(\d+)</td>\s*<td>Gated Scheme A", su.get("/admin/schemes").text).group(1))
    r = adminA.post(f"/admin/schemes/{gsid}/delete")
    check("gated scheme delete is deferred (not executed)",
          r.status_code == 303 and "Gated Scheme A" in su.get("/admin/schemes").text)
    reqid = newest_request_id(su.get("/admin/approvals?status=pending").text)
    check("a pending approval request was created", reqid is not None)
    adminB.post(f"/admin/approvals/{reqid}/vote", data={"decision": "approve"})
    check("another admin's approval does NOT satisfy a superadmin policy",
          "Gated Scheme A" in su.get("/admin/schemes").text)
    su.post(f"/admin/approvals/{reqid}/vote", data={"decision": "approve"})
    check("superadmin approval applies the deletion",
          "Gated Scheme A" not in su.get("/admin/schemes").text)

    # policy: deleting a user needs 2 distinct admins
    su.post("/admin/approval-policy", data={"level__user.delete": "2"})
    signup(new_client(base), "gatedvictim", "9000050003", pw="x1234567")
    vid = find_uid("gatedvictim")
    adminA.post(f"/admin/users/{vid}/delete")  # initiator counts as approval #1
    check("2-admin user delete is deferred", "gatedvictim" in su.get("/admin/users").text)
    reqid2 = newest_request_id(su.get("/admin/approvals?status=pending").text)
    adminB.post(f"/admin/approvals/{reqid2}/vote", data={"decision": "approve"})
    check("the second admin's approval applies the delete",
          "gatedvictim" not in su.get("/admin/users").text)

    # superadmin override: a superadmin's own action executes immediately
    signup(new_client(base), "gatedvictim2", "9000050004", pw="x1234567")
    su.post(f"/admin/users/{find_uid('gatedvictim2')}/delete")
    check("superadmin override executes immediately",
          "gatedvictim2" not in su.get("/admin/users").text)

    # reject flow
    su.post("/admin/approval-policy", data={"level__scheme.delete": "superadmin"})
    su.post("/admin/schemes/add", data={"name": "Gated Scheme B", "status": "active"})
    gsid2 = int(re.search(r"<td>(\d+)</td>\s*<td>Gated Scheme B", su.get("/admin/schemes").text).group(1))
    adminA.post(f"/admin/schemes/{gsid2}/delete")
    reqid3 = newest_request_id(su.get("/admin/approvals?status=pending").text)
    su.post(f"/admin/approvals/{reqid3}/vote", data={"decision": "reject", "note": "keep it"})
    check("a rejected request does not apply the action",
          "Gated Scheme B" in su.get("/admin/schemes").text)
    check("non-admin cannot view approvals -> 403",
          user.get("/admin/approvals").status_code == 403)
    # reset policy so later/other behaviour is unaffected
    su.post("/admin/approval-policy", data={})

    # ---------- Scheme sources + eligibility dispute ----------
    section("Scheme sources + eligibility dispute")

    # a scheme nobody can qualify for (impossible age window)
    admin.post("/admin/schemes/add", data={
        "name": "Eligibility Test Scheme", "status": "active",
        "min_age": "200", "max_age": "201"})
    et_sid = int(re.search(r"<td>(\d+)</td>\s*<td>Eligibility Test Scheme",
                           admin.get("/admin/schemes").text).group(1))

    # sources: add an official link + upload a GR file
    r = admin.post(f"/admin/schemes/{et_sid}/sources/link",
                   data={"label": "Official page", "url": "https://example.gov.in/scheme"})
    check("admin adds source link -> 303", r.status_code == 303)
    r = admin.post(f"/admin/schemes/{et_sid}/sources/file", data={"label": "GR 2024"},
                   files={"file": ("gr.pdf", b"%PDF-1.4 fake gr bytes", "application/pdf")})
    check("admin uploads GR file -> 303", r.status_code == 303)
    detail = anon.get(f"/schemes/{et_sid}").text
    check("public scheme page shows the source link",
          "https://example.gov.in/scheme" in detail)
    check("public scheme page shows the GR file", "GR 2024" in detail)
    src_file_id = int(re.search(rf"/schemes/{et_sid}/sources/(\d+)/file", detail).group(1))
    dl = anon.get(f"/schemes/{et_sid}/sources/{src_file_id}/file")
    check("anon downloads the GR file as attachment",
          dl.status_code == 200 and "attachment" in dl.headers.get("content-disposition", ""))
    # disallowed file type is rejected
    r = admin.post(f"/admin/schemes/{et_sid}/sources/file",
                   files={"file": ("evil.svg", b"<svg/>", "image/svg+xml")})
    check("disallowed source file type rejected",
          "not+allowed" in r.headers.get("location", ""))
    # delete a source removes the file
    r = admin.post(f"/admin/schemes/{et_sid}/sources/{src_file_id}/delete")
    check("admin deletes a source -> 303", r.status_code == 303)
    check("deleted GR file no longer downloadable (404)",
          anon.get(f"/schemes/{et_sid}/sources/{src_file_id}/file").status_code == 404)

    # eligibility dispute: a resident who the system says doesn't qualify
    du = new_client(base)
    signup(du, "disputer", "9000060001")
    fill_profile(du)  # age ~46, never 200+, so NOT eligible
    p = du.get(f"/schemes/{et_sid}").text
    check("non-eligible user is told they don't qualify", "don't currently qualify" in p)
    check("dispute form is shown on a non-eligible scheme",
          f'action="/schemes/{et_sid}/dispute"' in p)
    r = du.post(f"/schemes/{et_sid}/dispute",
                data={"description": "My age is fine, I can provide proof."})
    check("POST dispute -> 303 to the complaint",
          r.status_code == 303 and "/complaints/" in r.headers.get("location", ""))
    disp_id = int(re.search(r"/complaints/(\d+)", r.headers["location"]).group(1))
    my = du.get("/my/complaints").text
    check("dispute appears in 'my complaints' as Eligibility",
          f"/complaints/{disp_id}" in my and "Eligibility" in my)
    check("eligibility dispute is NOT on the public board",
          f"/complaints/{disp_id}" not in anon.get("/complaints").text)
    ac = admin.get("/admin/complaints").text
    check("admin sees the dispute typed Eligibility + scheme",
          "Eligibility" in ac and "Eligibility Test Scheme" in ac)
    # one open dispute per scheme
    r = du.post(f"/schemes/{et_sid}/dispute", data={"description": "again"})
    check("duplicate open dispute is blocked", r.status_code == 303)
    # cannot dispute a scheme you already qualify for
    admin.post("/admin/schemes/add", data={"name": "Open To All Scheme", "status": "active"})
    open_sid = int(re.search(r"<td>(\d+)</td>\s*<td>Open To All Scheme",
                             admin.get("/admin/schemes").text).group(1))
    check("eligible user sees a 'you qualify' message",
          "you qualify" in du.get(f"/schemes/{open_sid}").text.lower())
    r = du.post(f"/schemes/{open_sid}/dispute", data={"description": "x"})
    check("dispute blocked when already eligible",
          r.status_code == 303 and "already+qualify" in r.headers.get("location", ""))
    check("anon POST dispute -> 303 login",
          new_client(base).post(f"/schemes/{et_sid}/dispute",
                                data={"description": "x"}).status_code == 303)

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
