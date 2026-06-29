"""JSON export / import for backup, transfer, and bootstrapping a new village.

Two shapes:

* **Full backup** (`export_backup`): every table dumped verbatim, for
  point-in-time backup or moving an instance wholesale. Includes PII and
  password hashes — treat the file as sensitive. (Restoring a full backup is
  intentionally not exposed in the UI; load it with the offline tooling.)

* **Catalogue** (`export_catalogue` / `import_catalogue`): the shareable,
  non-personal data — schemes, the document master list, and the officials
  directory. This is what bootstraps a brand-new village instance, and the
  import is idempotent (existing rows are skipped by their natural key).
"""
from datetime import datetime, timezone

from app.database import get_db
from app.services import scheme_service, document_service, officials_service

BACKUP_VERSION = 1


async def _all_table_names(db) -> list:
    cursor = await db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name")
    return [r["name"] for r in await cursor.fetchall()]


async def export_backup() -> dict:
    """Dump every table verbatim. JSON-serialisable."""
    db = await get_db()
    try:
        tables = await _all_table_names(db)
        data = {}
        for table in tables:
            cursor = await db.execute(f"SELECT * FROM {table}")
            data[table] = [dict(r) for r in await cursor.fetchall()]
    finally:
        await db.close()
    return {
        "kind": "barloni-gram-seva-backup",
        "version": BACKUP_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "tables": data,
    }


async def export_catalogue() -> dict:
    """Shareable, non-personal data: schemes + documents + officials."""
    schemes = await scheme_service.list_schemes(only_active=False)
    # Keep only the portable fields; drop instance-local ids / counters / dates.
    portable_schemes = []
    for s in schemes:
        portable_schemes.append({
            "name": s.get("name"),
            "name_hi": s.get("name_hi"),
            "ministry": s.get("ministry"),
            "category": s.get("category"),
            "objective": s.get("objective"),
            "benefits": s.get("benefits"),
            "eligibility_rules": s.get("eligibility_rules"),
            "documents_required": s.get("documents_required"),
            "how_to_apply": s.get("how_to_apply"),
            "application_deadline": s.get("application_deadline"),
            "status": s.get("status"),
            "scheme_data": s.get("scheme_data"),
        })
    documents = [d["name"] for d in await document_service.list_documents()]
    officials = []
    for o in await officials_service.list_officials():
        officials.append({k: o.get(k) for k in (
            "name", "designation", "level", "ward", "department",
            "phone", "email", "office_address", "office_hours")})
    return {
        "kind": "barloni-gram-seva-catalogue",
        "version": BACKUP_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "schemes": portable_schemes,
        "documents": documents,
        "officials": officials,
    }


async def import_catalogue(data: dict) -> dict:
    """Load a catalogue into this instance. Idempotent (skips existing).

    Returns counts: {"schemes": {added, skipped}, "documents": {...},
    "officials": {...}, "errors": [...]}.
    """
    import json

    summary = {
        "schemes": {"added": 0, "skipped": 0},
        "documents": {"added": 0, "skipped": 0},
        "officials": {"added": 0, "skipped": 0},
        "errors": [],
    }
    if not isinstance(data, dict):
        summary["errors"].append("File is not a valid catalogue object.")
        return summary
    if data.get("kind") not in ("barloni-gram-seva-catalogue", "barloni-gram-seva-backup"):
        summary["errors"].append("Unrecognised file — expected a gram-seva catalogue export.")
        return summary

    # Document master list first, so schemes that reference them line up.
    for name in (data.get("documents") or []):
        doc = await document_service.add_document(name)
        if doc is None:
            continue
        # add_document is itself idempotent; we can't cheaply tell added vs
        # existing, so count conservatively as added when a name was given.
        summary["documents"]["added"] += 1

    for s in (data.get("schemes") or []):
        name = (s.get("name") or "").strip()
        if not name:
            summary["errors"].append("A scheme with no name was skipped.")
            continue
        if await scheme_service.get_scheme_by_name(name):
            summary["schemes"]["skipped"] += 1
            continue
        rules = s.get("eligibility_rules")
        docs = s.get("documents_required")
        extra = s.get("scheme_data")
        await scheme_service.create_scheme({
            "name": name,
            "name_hi": s.get("name_hi"),
            "ministry": s.get("ministry"),
            "category": s.get("category"),
            "objective": s.get("objective"),
            "benefits": s.get("benefits"),
            "eligibility_rules": json.dumps(rules) if rules else None,
            "documents_required": json.dumps(docs) if docs else None,
            "how_to_apply": s.get("how_to_apply"),
            "application_deadline": s.get("application_deadline"),
            "status": s.get("status") or "active",
            "scheme_data": json.dumps(extra) if extra else None,
        })
        # Make sure any documents the scheme needs exist in the master list.
        for d in (docs or []):
            await document_service.add_document(d)
        summary["schemes"]["added"] += 1

    for o in (data.get("officials") or []):
        name = (o.get("name") or "").strip()
        if not name:
            continue
        if await officials_service.find_official(
                name, o.get("designation") or "", o.get("ward") or ""):
            summary["officials"]["skipped"] += 1
            continue
        try:
            await officials_service.create_official({
                "name": name,
                "designation": o.get("designation") or None,
                "level": max(1, int(o.get("level") or 2)),
                "ward": o.get("ward") or None,
                "department": (o.get("department") or None),
                "phone": o.get("phone") or None,
                "email": o.get("email") or None,
                "photo_path": None,
                "office_address": o.get("office_address") or None,
                "office_hours": o.get("office_hours") or None,
            })
            summary["officials"]["added"] += 1
        except Exception as exc:
            summary["errors"].append(f"Official '{name}': {exc}")

    return summary
