"""Shared option lists used across profile forms, scheme rules, and matching."""

GENDERS = ["male", "female", "other"]

CASTE_CATEGORIES = ["general", "obc", "sc", "st"]

OCCUPATIONS = [
    "farmer", "labourer", "self_employed", "salaried",
    "student", "unemployed", "other",
]

LAND_OWNERSHIP = ["landless", "marginal", "small", "large"]

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
