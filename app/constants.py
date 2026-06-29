"""Shared option lists used across profile forms, scheme rules, and matching."""

GENDERS = ["male", "female", "other"]

CASTE_CATEGORIES = ["general", "obc", "sc", "st"]

OCCUPATIONS = [
    "farmer", "labourer", "self_employed", "salaried",
    "student", "unemployed", "other",
]

LAND_OWNERSHIP = ["landless", "marginal", "small", "large"]

# --- Complaints module -----------------------------------------------------

COMPLAINT_CATEGORIES = [
    "water", "electricity", "garbage", "roads", "drainage", "other",
]

# Full lifecycle. 'submitted' is the initial state; 'withdrawn' is set by the
# filer; the rest are set by an admin.
COMPLAINT_STATUSES = [
    "submitted", "acknowledged", "in_progress", "resolved", "rejected", "withdrawn",
]

# Statuses an admin can move a complaint to.
COMPLAINT_ADMIN_STATUSES = ["acknowledged", "in_progress", "resolved", "rejected"]

# "Open" = still needs attention (counts toward the admin badge).
COMPLAINT_OPEN_STATUSES = ["submitted", "acknowledged", "in_progress"]

# Master list seeded into the `documents` table on first run. Admins can add
# more from the scheme form; additions become available to every scheme.
DEFAULT_DOCUMENTS = [
    "Aadhaar card",
    "Bank account passbook",
    "Ration / BPL card",
    "Income certificate",
    "Caste certificate",
    "Domicile / Residence certificate",
    "Land records (Khasra / Khatauni)",
    "Passport-size photograph",
    "Voter ID card",
    "PAN card",
    "Disability certificate",
    "Birth certificate",
    "Aadhaar-linked mobile number",
]
