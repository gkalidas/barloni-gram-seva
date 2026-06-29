"""Eligibility matching engine: evaluate a user profile against scheme rules.

Beyond a yes/no verdict, the engine can explain *which* criteria a profile meets
and which it misses, flag the misses that the resident can actually act on
(e.g. "get a BPL card"), and recommend the single actions that would unlock the
most additional schemes.
"""
from typing import Optional


def _is_empty(value) -> bool:
    return value is None or value == "" or value == []


# Unmet criteria a resident can realistically fix map to a concrete action.
# Anything not listed here (age, gender, caste, income, occupation, land,
# disability) is treated as a fixed fact we don't suggest "fixing".
_FIXABLE = {
    "bpl_card_required": ("bpl_card", "Get a BPL / ration card"),
    "bank_account_required": ("bank_account", "Open an Aadhaar-linked bank account"),
}


def _money(n) -> str:
    try:
        return "₹{:,}".format(int(n))
    except (TypeError, ValueError):
        return str(n)


def evaluate_detailed(profile: dict, rules: Optional[dict]) -> dict:
    """Return a per-criterion breakdown of how a profile matches a scheme.

    {
      "eligible": bool,
      "criteria": [{"key", "label", "met", "fix_key"?, "fix_label"?}, ...],
      "met_count": int, "total": int,
      "unmet": [<unmet criteria>], "fixable": [<unmet criteria with a fix>],
    }
    """
    criteria = []

    def add(key, label, met):
        item = {"key": key, "label": label, "met": bool(met)}
        if not met and key in _FIXABLE:
            item["fix_key"], item["fix_label"] = _FIXABLE[key]
        criteria.append(item)

    rules = rules or {}
    age = profile.get("age")

    min_age = rules.get("min_age")
    if not _is_empty(min_age):
        add("min_age", f"Age at least {min_age}", age is not None and age >= min_age)

    max_age = rules.get("max_age")
    if not _is_empty(max_age):
        add("max_age", f"Age at most {max_age}", age is not None and age <= max_age)

    gender = rules.get("gender")
    if not _is_empty(gender):
        add("gender", "Gender: " + ", ".join(gender),
            profile.get("gender") in gender)

    caste = rules.get("caste_category")
    if not _is_empty(caste):
        allowed = [c.lower() for c in caste]
        add("caste_category", "Caste category: " + ", ".join(c.upper() for c in caste),
            (profile.get("caste_category") or "").lower() in allowed)

    max_income = rules.get("max_income")
    if not _is_empty(max_income):
        income = profile.get("annual_family_income")
        add("max_income", f"Annual family income up to {_money(max_income)}",
            income is not None and income <= max_income)

    if rules.get("bpl_card_required") is True:
        add("bpl_card_required", "Has a BPL card", bool(profile.get("bpl_card")))

    occupation = rules.get("occupation")
    if not _is_empty(occupation):
        add("occupation", "Occupation: " + ", ".join(o.replace("_", " ") for o in occupation),
            profile.get("occupation") in occupation)

    land = rules.get("land_ownership")
    if not _is_empty(land):
        add("land_ownership", "Land ownership: " + ", ".join(land),
            profile.get("land_ownership") in land)

    if rules.get("has_disability") is True:
        add("has_disability", "Person with a disability",
            bool(profile.get("has_disability")))

    if rules.get("bank_account_required") is True:
        add("bank_account_required", "Has an Aadhaar-linked bank account",
            bool(profile.get("bank_account_aadhaar_linked")))

    unmet = [c for c in criteria if not c["met"]]
    fixable = [c for c in unmet if "fix_key" in c]
    return {
        "eligible": len(unmet) == 0,
        "criteria": criteria,
        "met_count": len(criteria) - len(unmet),
        "total": len(criteria),
        "unmet": unmet,
        "fixable": fixable,
    }


def evaluate_scheme(profile: dict, rules: Optional[dict]) -> bool:
    """Return True if the profile satisfies ALL non-null rules of a scheme."""
    return evaluate_detailed(profile, rules)["eligible"]


def matching_schemes(profile: dict, schemes: list) -> list:
    """Return the subset of schemes the profile is eligible for."""
    if not profile:
        return []
    return [s for s in schemes if evaluate_scheme(profile, s.get("eligibility_rules"))]


def near_miss_schemes(profile: dict, schemes: list, max_unmet: int = 2) -> list:
    """Schemes the profile is NOT eligible for but is close to — at most
    `max_unmet` unmet criteria. Each result carries its eligibility breakdown
    under `_eligibility`, sorted by fewest unmet first (most reachable first)."""
    if not profile:
        return []
    out = []
    for s in schemes:
        result = evaluate_detailed(profile, s.get("eligibility_rules"))
        n = len(result["unmet"])
        if 0 < n <= max_unmet:
            s = dict(s)
            s["_eligibility"] = result
            out.append(s)
    out.sort(key=lambda x: len(x["_eligibility"]["unmet"]))
    return out


def recommend_actions(profile: dict, schemes: list) -> list:
    """Single actions that would each unlock one or more *additional* schemes.

    An action is recommended for a scheme only when it is the resident's *only*
    remaining blocker for that scheme (so doing it actually makes them eligible).
    Returns [{"fix_key", "fix_label", "count", "schemes": [names]}], best first.
    """
    if not profile:
        return []
    by_fix = {}
    for s in schemes:
        result = evaluate_detailed(profile, s.get("eligibility_rules"))
        unmet = result["unmet"]
        if len(unmet) != 1:
            continue
        only = unmet[0]
        if "fix_key" not in only:
            continue
        entry = by_fix.setdefault(
            only["fix_key"], {"fix_key": only["fix_key"],
                              "fix_label": only["fix_label"],
                              "count": 0, "schemes": []})
        entry["count"] += 1
        entry["schemes"].append(s.get("name"))
    out = list(by_fix.values())
    out.sort(key=lambda x: x["count"], reverse=True)
    return out
