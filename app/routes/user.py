"""User routes: dashboard, profile view/edit, eligible schemes."""
from datetime import date, datetime

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth import require_user
from app.services import user_service, scheme_service, eligibility_service

router = APIRouter()


def _templates(request: Request):
    return request.app.state.templates


GENDERS = ["male", "female", "other"]
CASTE_CATEGORIES = ["general", "obc", "sc", "st"]
OCCUPATIONS = [
    "farmer", "labourer", "self_employed", "salaried",
    "student", "unemployed", "other",
]
LAND_OWNERSHIP = ["landless", "marginal", "small", "large"]


def _calc_age(dob_str: str):
    try:
        dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None
    today = date.today()
    return today.year - dob.year - (
        (today.month, today.day) < (dob.month, dob.day)
    )


def _to_float(value):
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _to_int(value):
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _parse_profile_form(form) -> tuple:
    """Build a profile dict from raw form data. Returns (profile, errors)."""
    errors = []

    full_name = (form.get("full_name") or "").strip()
    date_of_birth = (form.get("date_of_birth") or "").strip()
    gender = (form.get("gender") or "").strip()
    state = (form.get("state") or "").strip()
    district = (form.get("district") or "").strip()
    village = (form.get("village") or "").strip()
    caste_category = (form.get("caste_category") or "").strip()
    occupation = (form.get("occupation") or "").strip()
    land_ownership = (form.get("land_ownership") or "").strip()

    if not full_name:
        errors.append("Full name is required.")
    age = _calc_age(date_of_birth)
    if age is None:
        errors.append("A valid date of birth is required.")
    if gender not in GENDERS:
        errors.append("Please select a valid gender.")
    if not state:
        errors.append("State is required.")
    if not district:
        errors.append("District is required.")
    if not village:
        errors.append("Village is required.")
    if caste_category not in CASTE_CATEGORIES:
        errors.append("Please select a valid caste category.")
    if occupation not in OCCUPATIONS:
        errors.append("Please select a valid occupation.")
    if land_ownership not in LAND_OWNERSHIP:
        errors.append("Please select a valid land ownership type.")

    income = _to_float(form.get("annual_family_income"))
    if income is None or income < 0:
        errors.append("A valid annual family income is required.")

    family_size = _to_int(form.get("family_size"))
    if family_size is None or family_size < 1:
        errors.append("Family size must be at least 1.")

    land_area = _to_float(form.get("land_area_acres"))
    if land_ownership == "landless":
        land_area = 0.0

    profile = {
        "full_name": full_name,
        "date_of_birth": date_of_birth,
        "age": age,
        "gender": gender,
        "state": state,
        "district": district,
        "village": village,
        "caste_category": caste_category.upper() if caste_category else "",
        "bpl_card": form.get("bpl_card") == "on",
        "annual_family_income": income,
        "occupation": occupation,
        "land_ownership": land_ownership,
        "land_area_acres": land_area,
        "family_size": family_size,
        "has_disability": form.get("has_disability") == "on",
        "bank_account_aadhaar_linked": form.get("bank_account_aadhaar_linked") == "on",
    }
    return profile, errors


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    user = await require_user(request)
    profile = user_service.get_profile(user)
    eligible_count = 0
    if profile:
        schemes = await scheme_service.list_schemes(only_active=True)
        eligible_count = len(
            eligibility_service.matching_schemes(profile, schemes)
        )
    pending = await user_service.has_pending_request(user["id"])
    return _templates(request).TemplateResponse(request, 
        "user/dashboard.html",
        {
            "request": request,
            "user": user,
            "profile": profile,
            "profile_submitted": bool(user.get("profile_submitted")),
            "eligible_count": eligible_count,
            "has_pending": pending,
        },
    )


@router.get("/profile", response_class=HTMLResponse)
async def view_profile(request: Request):
    user = await require_user(request)
    profile = user_service.get_profile(user)
    pending_profile = user_service.get_pending_profile(user)
    return _templates(request).TemplateResponse(request, 
        "user/profile.html",
        {
            "request": request,
            "user": user,
            "profile": profile,
            "pending_profile": pending_profile,
            "has_pending": await user_service.has_pending_request(user["id"]),
        },
    )


@router.get("/profile/edit", response_class=HTMLResponse)
async def edit_profile_form(request: Request):
    user = await require_user(request)
    profile = user_service.get_profile(user)
    first_time = not bool(user.get("profile_submitted"))
    has_pending = await user_service.has_pending_request(user["id"])
    return _templates(request).TemplateResponse(request, 
        "user/profile_edit.html",
        {
            "request": request,
            "user": user,
            "profile": profile or {},
            "first_time": first_time,
            "has_pending": has_pending,
            "genders": GENDERS,
            "caste_categories": CASTE_CATEGORIES,
            "occupations": OCCUPATIONS,
            "land_ownership_options": LAND_OWNERSHIP,
        },
    )


@router.post("/profile/edit", response_class=HTMLResponse)
async def edit_profile_submit(request: Request):
    user = await require_user(request)
    form = await request.form()
    profile, errors = _parse_profile_form(form)
    first_time = not bool(user.get("profile_submitted"))

    if errors:
        return _templates(request).TemplateResponse(request, 
            "user/profile_edit.html",
            {
                "request": request,
                "user": user,
                "profile": profile,
                "first_time": first_time,
                "has_pending": await user_service.has_pending_request(user["id"]),
                "genders": GENDERS,
                "caste_categories": CASTE_CATEGORIES,
                "occupations": OCCUPATIONS,
                "land_ownership_options": LAND_OWNERSHIP,
                "flash": ("error", " ".join(errors)),
            },
            status_code=400,
        )

    if first_time:
        await user_service.submit_first_profile(user["id"], profile)
        return RedirectResponse(
            "/dashboard?msg=Profile+saved+successfully", status_code=303
        )

    # Subsequent edit -> change request
    if await user_service.has_pending_request(user["id"]):
        return RedirectResponse(
            "/profile?msg=You+already+have+a+pending+change+request",
            status_code=303,
        )
    old_profile = user_service.get_profile(user)
    await user_service.request_profile_change(user["id"], old_profile, profile)
    return RedirectResponse(
        "/profile?msg=Change+request+submitted+for+admin+approval",
        status_code=303,
    )


@router.get("/my-schemes", response_class=HTMLResponse)
async def my_schemes(request: Request):
    user = await require_user(request)
    profile = user_service.get_profile(user)
    eligible = []
    if profile:
        schemes = await scheme_service.list_schemes(only_active=True)
        eligible = eligibility_service.matching_schemes(profile, schemes)
    return _templates(request).TemplateResponse(request, 
        "user/eligibility.html",
        {
            "request": request,
            "user": user,
            "profile": profile,
            "schemes": eligible,
        },
    )
