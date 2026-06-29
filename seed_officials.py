"""Seed a realistic starter list of village officials / responsible people.

Reflects a typical Indian Gram Panchayat: elected leaders, appointed
administration, ward members (Panch), ICDS / health functionaries (Anganwadi
Sevika, ASHA, ANM), and service staff mapped to each complaint department.
Runs on first startup (skipped if any officials already exist). Villages edit
this via Admin -> Officials (or CSV import/export). Phone numbers are
placeholders — replace them with the real ones.

Can also be run standalone:  python seed_officials.py
"""
import asyncio

from app.database import init_db, get_db  # noqa: F401
from app.services import officials_service

OFFICIALS = [
    # Level 1 — elected leadership
    {"name": "Ramrao Patil", "designation": "Sarpanch (Gram Pradhan)", "level": 1,
     "phone": "9810000001", "office_address": "Gram Panchayat Office",
     "office_hours": "Mon–Sat, 10am–5pm"},
    {"name": "Sunita Jadhav", "designation": "Up-Sarpanch (Deputy Sarpanch)", "level": 1,
     "phone": "9810000002"},

    # Level 2 — appointed administration
    {"name": "Vishnu Deshmukh",
     "designation": "Gram Panchayat Secretary (Gram Sevak / VDO)", "level": 2,
     "department": "other", "phone": "9810000003",
     "office_address": "Gram Panchayat Office", "office_hours": "Mon–Sat, 10am–5pm"},
    {"name": "Kishan Lal", "designation": "Patwari / Lekhpal (Land Records)", "level": 2,
     "department": "other", "phone": "9810000004", "office_hours": "Mon–Fri, 11am–4pm"},
    {"name": "Anil Gaikwad", "designation": "Gram Rozgar Sevak (MGNREGA)", "level": 2,
     "department": "other", "phone": "9810000005"},

    # Level 3 — ward members (Panch), one per ward
    {"name": "Manda Pawar", "designation": "Ward Member (Panch)", "level": 3, "ward": "Ward 1", "phone": "9810000011"},
    {"name": "Ganpat More", "designation": "Ward Member (Panch)", "level": 3, "ward": "Ward 2", "phone": "9810000012"},
    {"name": "Shobha Shinde", "designation": "Ward Member (Panch)", "level": 3, "ward": "Ward 3", "phone": "9810000013"},
    {"name": "Ravi Chavan", "designation": "Ward Member (Panch)", "level": 3, "ward": "Ward 4", "phone": "9810000014"},
    {"name": "Lata Kamble", "designation": "Ward Member (Panch)", "level": 3, "ward": "Ward 5", "phone": "9810000015"},

    # Level 3 — ICDS / health functionaries
    {"name": "Asha Devi", "designation": "Anganwadi Sevika (ICDS)", "level": 3,
     "ward": "Ward 1", "department": "other", "phone": "9810000021",
     "office_address": "Anganwadi Centre", "office_hours": "Mon–Sat, 9am–4pm"},
    {"name": "Mira Bai", "designation": "ASHA Worker (Health)", "level": 3,
     "ward": "Ward 2", "department": "other", "phone": "9810000022"},
    {"name": "Sangita Rao", "designation": "ANM (Auxiliary Nurse Midwife)", "level": 3,
     "department": "other", "phone": "9810000023", "office_address": "Sub-Centre / PHC"},

    # Level 4 — service staff, mapped to complaint departments
    {"name": "Bhau Salunke", "designation": "Jal Sahayak / Handpump Mechanic", "level": 4, "department": "water", "phone": "9810000031"},
    {"name": "Dnyaneshwar Kale", "designation": "Electricity Lineman", "level": 4, "department": "electricity", "phone": "9810000032"},
    {"name": "Raju Waghmare", "designation": "Safai Karmachari (Sanitation)", "level": 4, "department": "garbage", "phone": "9810000033"},
    {"name": "Sopan Jadhav", "designation": "Road / PWD Mate", "level": 4, "department": "roads", "phone": "9810000034"},
    {"name": "Hari Tare", "designation": "Drainage Supervisor", "level": 4, "department": "drainage", "phone": "9810000035"},
    {"name": "Baban Nikam", "designation": "Kotwar / Chowkidar (Village Watchman)", "level": 4, "department": "other", "phone": "9810000036"},
    {"name": "Vasant Bhosale", "designation": "Fair Price Shop (PDS) Dealer", "level": 4,
     "department": "other", "phone": "9810000037", "office_hours": "Mon–Sat, 9am–1pm"},
]


async def seed() -> None:
    if await officials_service.count_officials() > 0:
        return
    for o in OFFICIALS:
        await officials_service.create_official({
            "name": o["name"],
            "designation": o.get("designation"),
            "level": o.get("level", 2),
            "ward": o.get("ward"),
            "department": o.get("department"),
            "phone": o.get("phone"),
            "email": o.get("email"),
            "photo_path": None,
            "office_address": o.get("office_address"),
            "office_hours": o.get("office_hours"),
        })


async def _main() -> None:
    await init_db()
    await seed()
    print(f"Officials in database: {await officials_service.count_officials()}")


if __name__ == "__main__":
    asyncio.run(_main())
