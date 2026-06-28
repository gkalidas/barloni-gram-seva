"""Seed the database with 10 realistic Indian government schemes.

Runs on first startup (skipped if any schemes already exist). Can also be
run standalone:  python seed_schemes.py
"""
import asyncio
import json

from app.database import init_db, get_db
from app.services import scheme_service

SCHEMES = [
    {
        "name": "PM-KISAN",
        "name_hi": "पीएम-किसान",
        "ministry": "Ministry of Agriculture & Farmers Welfare",
        "category": "agriculture",
        "objective": "Income support of ₹6,000/year to small and marginal farmer families.",
        "benefits": "₹6,000 per year in three equal installments, paid directly to bank account.",
        "eligibility_rules": {
            "occupation": ["farmer"],
            "land_ownership": ["landless", "marginal", "small"],
            "bank_account_required": True,
        },
        "documents_required": ["Aadhaar card", "Land records", "Bank account passbook"],
        "how_to_apply": "Register at the nearest CSC or pmkisan.gov.in with land records and Aadhaar.",
        "application_deadline": "ongoing",
        "status": "active",
    },
    {
        "name": "MGNREGA",
        "name_hi": "मनरेगा",
        "ministry": "Ministry of Rural Development",
        "category": "employment",
        "objective": "Guarantees 100 days of wage employment per year to rural households.",
        "benefits": "At least 100 days of guaranteed unskilled manual work at notified wage rates.",
        "eligibility_rules": {
            "min_age": 18,
            "occupation": ["labourer", "unemployed", "farmer"],
        },
        "documents_required": ["Job card", "Aadhaar card", "Bank/Post office account"],
        "how_to_apply": "Apply for a job card at your Gram Panchayat office.",
        "application_deadline": "ongoing",
        "status": "active",
    },
    {
        "name": "PM Awas Yojana (Gramin)",
        "name_hi": "प्रधानमंत्री आवास योजना (ग्रामीण)",
        "ministry": "Ministry of Rural Development",
        "category": "housing",
        "objective": "Pucca house with basic amenities for rural BPL families.",
        "benefits": "Financial assistance of ₹1.2–1.3 lakh for construction of a pucca house.",
        "eligibility_rules": {
            "bpl_card_required": True,
            "max_income": 120000,
        },
        "documents_required": ["Aadhaar card", "BPL card", "Bank account passbook"],
        "how_to_apply": "Apply through the Gram Panchayat; beneficiaries are selected from the SECC list.",
        "application_deadline": "ongoing",
        "status": "active",
    },
    {
        "name": "Ayushman Bharat (PMJAY)",
        "name_hi": "आयुष्मान भारत",
        "ministry": "Ministry of Health & Family Welfare",
        "category": "health",
        "objective": "Health cover of ₹5 lakh per family per year for secondary and tertiary care.",
        "benefits": "Cashless hospitalization up to ₹5 lakh/year at empanelled hospitals.",
        "eligibility_rules": {
            "bpl_card_required": True,
            "max_income": 200000,
        },
        "documents_required": ["Aadhaar card", "Ration/BPL card"],
        "how_to_apply": "Check eligibility at pmjay.gov.in or a Common Service Centre and get your Ayushman card.",
        "application_deadline": "ongoing",
        "status": "active",
    },
    {
        "name": "PM Ujjwala Yojana",
        "name_hi": "प्रधानमंत्री उज्ज्वला योजना",
        "ministry": "Ministry of Petroleum & Natural Gas",
        "category": "women_child",
        "objective": "Free LPG connections to women from BPL households.",
        "benefits": "Deposit-free LPG connection with first refill and stove support.",
        "eligibility_rules": {
            "gender": ["female"],
            "bpl_card_required": True,
            "min_age": 18,
        },
        "documents_required": ["Aadhaar card", "BPL ration card", "Bank account passbook"],
        "how_to_apply": "Apply at the nearest LPG distributor with KYC and BPL proof.",
        "application_deadline": "ongoing",
        "status": "active",
    },
    {
        "name": "Sukanya Samriddhi Yojana",
        "name_hi": "सुकन्या समृद्धि योजना",
        "ministry": "Ministry of Finance",
        "category": "women_child",
        "objective": "Small savings scheme for the welfare of the girl child.",
        "benefits": "High fixed interest, tax benefits, and maturity corpus for a girl child's education/marriage.",
        "eligibility_rules": {
            "gender": ["female"],
            "max_age": 10,
        },
        "documents_required": ["Girl child's birth certificate", "Guardian Aadhaar", "Address proof"],
        "how_to_apply": "Open an account at any post office or authorised bank for a girl child under 10.",
        "application_deadline": "ongoing",
        "status": "active",
    },
    {
        "name": "PM Fasal Bima Yojana",
        "name_hi": "प्रधानमंत्री फसल बीमा योजना",
        "ministry": "Ministry of Agriculture & Farmers Welfare",
        "category": "agriculture",
        "objective": "Crop insurance against natural calamities, pests and diseases.",
        "benefits": "Insurance payout for crop loss at low farmer premium.",
        "eligibility_rules": {
            "occupation": ["farmer"],
            "land_ownership": ["marginal", "small", "large"],
        },
        "documents_required": ["Aadhaar card", "Land records", "Sowing certificate", "Bank passbook"],
        "how_to_apply": "Enrol through your bank, CSC, or pmfby.gov.in during the notified window.",
        "application_deadline": "ongoing",
        "status": "active",
    },
    {
        "name": "National Social Assistance Programme (NSAP)",
        "name_hi": "राष्ट्रीय सामाजिक सहायता कार्यक्रम",
        "ministry": "Ministry of Rural Development",
        "category": "pension",
        "objective": "Monthly pension for the elderly poor under the Old Age Pension scheme.",
        "benefits": "Monthly old-age pension to BPL persons aged 60 and above.",
        "eligibility_rules": {
            "min_age": 60,
            "bpl_card_required": True,
        },
        "documents_required": ["Aadhaar card", "Age proof", "BPL card", "Bank account passbook"],
        "how_to_apply": "Apply through the Gram Panchayat / Block office with age and BPL proof.",
        "application_deadline": "ongoing",
        "status": "active",
    },
    {
        "name": "Post-Matric Scholarship for SC/ST Students",
        "name_hi": "अनुसूचित जाति/जनजाति छात्रवृत्ति",
        "ministry": "Ministry of Social Justice & Empowerment",
        "category": "sc_st_welfare",
        "objective": "Education scholarship for SC/ST students to pursue post-matric studies.",
        "benefits": "Maintenance allowance, fee reimbursement and other education allowances.",
        "eligibility_rules": {
            "caste_category": ["sc", "st"],
            "occupation": ["student"],
            "max_income": 250000,
        },
        "documents_required": ["Caste certificate", "Income certificate", "Mark sheets", "Bank passbook"],
        "how_to_apply": "Apply online on the National Scholarship Portal (scholarships.gov.in).",
        "application_deadline": "ongoing",
        "status": "active",
    },
    {
        "name": "PM Vishwakarma",
        "name_hi": "पीएम विश्वकर्मा",
        "ministry": "Ministry of Micro, Small & Medium Enterprises",
        "category": "employment",
        "objective": "Support for traditional artisans and craftspeople.",
        "benefits": "Skill training with stipend, toolkit incentive, and collateral-free credit support.",
        "eligibility_rules": {
            "min_age": 18,
            "occupation": ["self_employed", "labourer", "other"],
        },
        "documents_required": ["Aadhaar card", "Bank account passbook", "Mobile number"],
        "how_to_apply": "Register at a Common Service Centre under the PM Vishwakarma scheme.",
        "application_deadline": "ongoing",
        "status": "active",
    },
]


def _to_db_row(scheme: dict) -> dict:
    """Serialize JSON fields to strings for storage."""
    data = dict(scheme)
    data["eligibility_rules"] = json.dumps(scheme.get("eligibility_rules") or {})
    data["documents_required"] = json.dumps(scheme.get("documents_required") or [])
    data["scheme_data"] = json.dumps(scheme.get("scheme_data") or {})
    return data


async def seed() -> None:
    """Insert sample schemes if none exist yet."""
    existing = await scheme_service.count_schemes()
    if existing > 0:
        return
    db = await get_db()
    try:
        for scheme in SCHEMES:
            row = _to_db_row(scheme)
            await db.execute(
                """INSERT INTO schemes
                   (name, name_hi, ministry, category, objective, benefits,
                    eligibility_rules, documents_required, how_to_apply,
                    application_deadline, status, scheme_data)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    row.get("name"), row.get("name_hi"), row.get("ministry"),
                    row.get("category"), row.get("objective"), row.get("benefits"),
                    row.get("eligibility_rules"), row.get("documents_required"),
                    row.get("how_to_apply"), row.get("application_deadline"),
                    row.get("status", "active"), row.get("scheme_data"),
                ),
            )
        await db.commit()
    finally:
        await db.close()


async def _main() -> None:
    await init_db()
    await seed()
    count = await scheme_service.count_schemes()
    print(f"Seed complete. Schemes in database: {count}")


if __name__ == "__main__":
    asyncio.run(_main())
