"""Eligibility matching engine: evaluate a user profile against scheme rules."""
from typing import Optional


def _is_empty(value) -> bool:
    return value is None or value == "" or value == []


def evaluate_scheme(profile: dict, rules: Optional[dict]) -> bool:
    """Return True if the profile satisfies ALL non-null rules of a scheme.

    For each rule field, a null/absent value means "no restriction".
    """
    if not rules:
        # No rules at all -> open to everyone with a profile
        return True

    # min_age
    min_age = rules.get("min_age")
    if not _is_empty(min_age):
        age = profile.get("age")
        if age is None or age < min_age:
            return False

    # max_age
    max_age = rules.get("max_age")
    if not _is_empty(max_age):
        age = profile.get("age")
        if age is None or age > max_age:
            return False

    # gender
    gender = rules.get("gender")
    if not _is_empty(gender):
        if profile.get("gender") not in gender:
            return False

    # caste_category
    caste = rules.get("caste_category")
    if not _is_empty(caste):
        user_caste = (profile.get("caste_category") or "").lower()
        allowed = [c.lower() for c in caste]
        if user_caste not in allowed:
            return False

    # max_income
    max_income = rules.get("max_income")
    if not _is_empty(max_income):
        income = profile.get("annual_family_income")
        if income is None or income > max_income:
            return False

    # bpl_card_required
    if rules.get("bpl_card_required") is True:
        if not profile.get("bpl_card"):
            return False

    # occupation
    occupation = rules.get("occupation")
    if not _is_empty(occupation):
        if profile.get("occupation") not in occupation:
            return False

    # land_ownership
    land = rules.get("land_ownership")
    if not _is_empty(land):
        if profile.get("land_ownership") not in land:
            return False

    # has_disability
    if rules.get("has_disability") is True:
        if not profile.get("has_disability"):
            return False

    # bank_account_required
    if rules.get("bank_account_required") is True:
        if not profile.get("bank_account_aadhaar_linked"):
            return False

    return True


def matching_schemes(profile: dict, schemes: list) -> list:
    """Return the subset of schemes the profile is eligible for."""
    if not profile:
        return []
    eligible = []
    for scheme in schemes:
        rules = scheme.get("eligibility_rules")
        if evaluate_scheme(profile, rules):
            eligible.append(scheme)
    return eligible
