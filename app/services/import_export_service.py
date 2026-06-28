"""CSV bulk import/export for users and schemes.

Uses only the Python standard library (csv). Multi-value cells (e.g. a
scheme's allowed genders, or its required documents) are separated by ";".
"""
import csv
import io
import json
import re
from datetime import date, datetime

from app.constants import GENDERS, CASTE_CATEGORIES, OCCUPATIONS, LAND_OWNERSHIP
from app.services import user_service, scheme_service, document_service

# Column layouts. Export and the downloadable templates both use these, so an
# exported file can be edited and imported straight back.
USER_COLUMNS = [
    "username", "mobile", "password", "role",
    "full_name", "date_of_birth", "gender", "state", "district", "village",
    "caste_category", "bpl_card", "annual_family_income", "occupation",
    "land_ownership", "land_area_acres", "family_size", "has_disability",
    "bank_account_aadhaar_linked",
]

SCHEME_COLUMNS = [
    "name", "name_hi", "ministry", "category", "objective", "benefits",
    "how_to_apply", "application_deadline", "status",
    "min_age", "max_age", "gender", "caste_category", "max_income",
    "bpl_card_required", "occupation", "land_ownership", "has_disability",
    "bank_account_required", "documents_required",
]

_TRUE_VALUES = {"true", "yes", "y", "1", "t"}


# --- small parsing helpers -------------------------------------------------

def _parse_bool(value) -> bool:
    return str(value).strip().lower() in _TRUE_VALUES


def _bool_out(value) -> str:
    return "true" if value else "false"


def _num_out(value) -> str:
    """Render a number for export without a trailing '.0' on whole values."""
    if value is None or value == "":
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _split_multi(value) -> list:
    """Split a multi-value cell on ';' (or ',') into a clean list."""
    if not value:
        return []
    out = []
    for chunk in str(value).replace(",", ";").split(";"):
        chunk = chunk.strip()
        if chunk:
            out.append(chunk)
    return out


def _to_int(value):
    value = str(value).strip()
    if not value:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def _to_float(value):
    value = str(value).strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _calc_age(dob_str):
    try:
        dob = datetime.strptime(str(dob_str).strip(), "%Y-%m-%d").date()
    except (ValueError, AttributeError):
        return None
    today = date.today()
    return today.year - dob.year - (
        (today.month, today.day) < (dob.month, dob.day)
    )


def _reader(raw_bytes):
    """Return (DictReader, getter) with case-insensitive header lookup."""
    text = raw_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    fieldmap = {
        (fn or "").strip().lower(): fn for fn in (reader.fieldnames or [])
    }

    def get(row, key):
        fn = fieldmap.get(key)
        return (row.get(fn) or "").strip() if fn else ""

    return reader, get


# --- user import -----------------------------------------------------------

def _build_profile(get, row):
    """Return (profile_dict_or_None, error_or_None) from profile columns."""
    full_name = get(row, "full_name")
    dob = get(row, "date_of_birth")
    gender = get(row, "gender").lower()
    occupation = get(row, "occupation").lower()
    caste = get(row, "caste_category").lower()
    land = get(row, "land_ownership").lower()
    village = get(row, "village")

    # No profile columns filled at all -> create account without a profile.
    if not any([full_name, dob, gender, occupation, caste, village]):
        return None, None

    errors = []
    age = _calc_age(dob)
    if not full_name:
        errors.append("full_name required for profile")
    if age is None:
        errors.append("valid date_of_birth (YYYY-MM-DD) required")
    if gender and gender not in GENDERS:
        errors.append(f"invalid gender '{gender}'")
    if caste and caste not in CASTE_CATEGORIES:
        errors.append(f"invalid caste_category '{caste}'")
    if occupation and occupation not in OCCUPATIONS:
        errors.append(f"invalid occupation '{occupation}'")
    if land and land not in LAND_OWNERSHIP:
        errors.append(f"invalid land_ownership '{land}'")
    if errors:
        return None, "; ".join(errors)

    land_area = _to_float(get(row, "land_area_acres"))
    profile = {
        "full_name": full_name,
        "date_of_birth": dob,
        "age": age,
        "gender": gender,
        "state": get(row, "state"),
        "district": get(row, "district"),
        "village": village,
        "caste_category": caste.upper() if caste else "",
        "bpl_card": _parse_bool(get(row, "bpl_card")),
        "annual_family_income": _to_float(get(row, "annual_family_income")),
        "occupation": occupation,
        "land_ownership": land,
        "land_area_acres": 0.0 if land == "landless" else land_area,
        "family_size": _to_int(get(row, "family_size")),
        "has_disability": _parse_bool(get(row, "has_disability")),
        "bank_account_aadhaar_linked": _parse_bool(
            get(row, "bank_account_aadhaar_linked")
        ),
    }
    return profile, None


async def import_users(raw_bytes: bytes) -> dict:
    reader, get = _reader(raw_bytes)
    summary = {"added": 0, "skipped": 0, "errors": []}
    if not reader.fieldnames:
        summary["errors"].append((0, "The file is empty or has no header row."))
        return summary

    rownum = 1  # header is row 1
    for row in reader:
        rownum += 1
        username = get(row, "username")
        mobile = get(row, "mobile")
        if not username and not mobile and not any(row.values()):
            continue  # blank line
        if not username or not mobile:
            summary["errors"].append((rownum, "username and mobile are required"))
            continue
        if not re.fullmatch(r"\d{10}", mobile):
            summary["errors"].append(
                (rownum, f"invalid mobile '{mobile}' (need 10 digits)")
            )
            continue
        # Dedupe BEFORE requiring a password, so re-importing an export
        # (which has a blank password column) simply skips existing users.
        if await user_service.get_user_by_username(username) or \
                await user_service.get_user_by_mobile(mobile):
            summary["skipped"] += 1
            continue

        password = get(row, "password")
        if not password:
            summary["errors"].append((rownum, "password is required for a new user"))
            continue
        role = get(row, "role").lower()
        if role not in ("user", "admin"):
            role = "user"

        profile, perr = _build_profile(get, row)
        if perr:
            summary["errors"].append((rownum, perr))
            continue

        user_id = await user_service.create_user(username, mobile, password, role)
        if profile:
            await user_service.submit_first_profile(user_id, profile)
        summary["added"] += 1

    return summary


# --- scheme import ---------------------------------------------------------

def _build_rules(get, row) -> dict:
    rules = {}
    min_age = _to_int(get(row, "min_age"))
    max_age = _to_int(get(row, "max_age"))
    max_income = _to_int(get(row, "max_income"))
    if min_age is not None:
        rules["min_age"] = min_age
    if max_age is not None:
        rules["max_age"] = max_age
    if max_income is not None:
        rules["max_income"] = max_income

    gender = [g.lower() for g in _split_multi(get(row, "gender")) if g.lower() in GENDERS]
    if gender:
        rules["gender"] = gender
    caste = [c.lower() for c in _split_multi(get(row, "caste_category")) if c.lower() in CASTE_CATEGORIES]
    if caste:
        rules["caste_category"] = caste
    occupation = [o.lower() for o in _split_multi(get(row, "occupation")) if o.lower() in OCCUPATIONS]
    if occupation:
        rules["occupation"] = occupation
    land = [l.lower() for l in _split_multi(get(row, "land_ownership")) if l.lower() in LAND_OWNERSHIP]
    if land:
        rules["land_ownership"] = land

    if _parse_bool(get(row, "bpl_card_required")):
        rules["bpl_card_required"] = True
    if _parse_bool(get(row, "has_disability")):
        rules["has_disability"] = True
    if _parse_bool(get(row, "bank_account_required")):
        rules["bank_account_required"] = True
    return rules


async def import_schemes(raw_bytes: bytes) -> dict:
    reader, get = _reader(raw_bytes)
    summary = {"added": 0, "skipped": 0, "errors": []}
    if not reader.fieldnames:
        summary["errors"].append((0, "The file is empty or has no header row."))
        return summary

    rownum = 1
    for row in reader:
        rownum += 1
        name = get(row, "name")
        if not name and not any(row.values()):
            continue
        if not name:
            summary["errors"].append((rownum, "scheme name is required"))
            continue
        if await scheme_service.get_scheme_by_name(name):
            summary["skipped"] += 1
            continue

        rules = _build_rules(get, row)
        documents = _split_multi(get(row, "documents_required"))
        # Register any new documents in the shared master list.
        for doc in documents:
            await document_service.add_document(doc)

        data = {
            "name": name,
            "name_hi": get(row, "name_hi") or None,
            "ministry": get(row, "ministry") or None,
            "category": get(row, "category") or None,
            "objective": get(row, "objective") or None,
            "benefits": get(row, "benefits") or None,
            "eligibility_rules": json.dumps(rules) if rules else None,
            "documents_required": json.dumps(documents) if documents else None,
            "how_to_apply": get(row, "how_to_apply") or None,
            "application_deadline": get(row, "application_deadline") or None,
            "status": get(row, "status") or "active",
            "scheme_data": None,
        }
        await scheme_service.create_scheme(data)
        summary["added"] += 1

    return summary


# --- export ----------------------------------------------------------------

async def export_users_csv() -> str:
    users = await user_service.list_users()
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=USER_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for u in users:
        profile = {}
        if u.get("profile_data"):
            try:
                profile = json.loads(u["profile_data"]) or {}
            except (json.JSONDecodeError, TypeError):
                profile = {}
        writer.writerow({
            "username": u["username"],
            "mobile": u["mobile"],
            "password": "",  # never export password hashes
            "role": u["role"],
            "full_name": profile.get("full_name", ""),
            "date_of_birth": profile.get("date_of_birth", ""),
            "gender": profile.get("gender", ""),
            "state": profile.get("state", ""),
            "district": profile.get("district", ""),
            "village": profile.get("village", ""),
            "caste_category": (profile.get("caste_category", "") or "").lower(),
            "bpl_card": _bool_out(profile.get("bpl_card")) if profile else "",
            "annual_family_income": _num_out(profile.get("annual_family_income")),
            "occupation": profile.get("occupation", ""),
            "land_ownership": profile.get("land_ownership", ""),
            "land_area_acres": _num_out(profile.get("land_area_acres")),
            "family_size": _num_out(profile.get("family_size")),
            "has_disability": _bool_out(profile.get("has_disability")) if profile else "",
            "bank_account_aadhaar_linked":
                _bool_out(profile.get("bank_account_aadhaar_linked")) if profile else "",
        })
    return out.getvalue()


async def export_schemes_csv() -> str:
    schemes = await scheme_service.list_schemes(only_active=False)
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=SCHEME_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for s in schemes:
        rules = s.get("eligibility_rules") or {}
        docs = s.get("documents_required") or []
        writer.writerow({
            "name": s.get("name", ""),
            "name_hi": s.get("name_hi", "") or "",
            "ministry": s.get("ministry", "") or "",
            "category": s.get("category", "") or "",
            "objective": s.get("objective", "") or "",
            "benefits": s.get("benefits", "") or "",
            "how_to_apply": s.get("how_to_apply", "") or "",
            "application_deadline": s.get("application_deadline", "") or "",
            "status": s.get("status", "active") or "active",
            "min_age": rules.get("min_age", ""),
            "max_age": rules.get("max_age", ""),
            "gender": ";".join(rules.get("gender") or []),
            "caste_category": ";".join(rules.get("caste_category") or []),
            "max_income": rules.get("max_income", ""),
            "bpl_card_required": _bool_out(rules.get("bpl_card_required")) if rules.get("bpl_card_required") else "",
            "occupation": ";".join(rules.get("occupation") or []),
            "land_ownership": ";".join(rules.get("land_ownership") or []),
            "has_disability": _bool_out(rules.get("has_disability")) if rules.get("has_disability") else "",
            "bank_account_required": _bool_out(rules.get("bank_account_required")) if rules.get("bank_account_required") else "",
            "documents_required": ";".join(docs),
        })
    return out.getvalue()


# --- downloadable blank templates ------------------------------------------

def user_template_csv() -> str:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=USER_COLUMNS)
    writer.writeheader()
    writer.writerow({
        "username": "rajesh", "mobile": "8888800001", "password": "changeme123",
        "role": "user", "full_name": "Rajesh Kumar", "date_of_birth": "1985-03-15",
        "gender": "male", "state": "Rajasthan", "district": "Jaipur",
        "village": "Barloni", "caste_category": "obc", "bpl_card": "true",
        "annual_family_income": "120000", "occupation": "farmer",
        "land_ownership": "marginal", "land_area_acres": "2.5", "family_size": "5",
        "has_disability": "false", "bank_account_aadhaar_linked": "true",
    })
    return out.getvalue()


def scheme_template_csv() -> str:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=SCHEME_COLUMNS)
    writer.writeheader()
    writer.writerow({
        "name": "Example Scheme", "name_hi": "", "ministry": "Ministry of X",
        "category": "agriculture", "objective": "One-line summary",
        "benefits": "What the person gets", "how_to_apply": "Apply at the CSC",
        "application_deadline": "ongoing", "status": "active",
        "min_age": "18", "max_age": "60", "gender": "male;female",
        "caste_category": "sc;st;obc", "max_income": "250000",
        "bpl_card_required": "true", "occupation": "farmer;labourer",
        "land_ownership": "landless;marginal", "has_disability": "false",
        "bank_account_required": "true",
        "documents_required": "Aadhaar card;Bank account passbook",
    })
    return out.getvalue()
