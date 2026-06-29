"""Admin analytics: signups over time, scheme popularity, eligibility spread.

All figures are computed on demand from the existing tables — no extra
bookkeeping beyond the scheme `views` counter. Fine at village scale (a few
thousand users / hundreds of schemes); revisit with materialised stats if the
dataset ever grows much larger.
"""
from app.database import get_db
from app.services import scheme_service, user_service, eligibility_service


async def signups_over_time(days: int = 30) -> dict:
    """Daily resident sign-up counts for the last `days` days.

    Returns {"labels": [YYYY-MM-DD...], "counts": [int...], "total": int}
    with one entry per day (zero-filled), oldest first.
    """
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT date(created_at) AS d, COUNT(*) AS c
               FROM users
               WHERE role = 'user' AND created_at >= date('now', ?)
               GROUP BY date(created_at)""",
            (f"-{int(days) - 1} days",))
        rows = {r["d"]: r["c"] for r in await cursor.fetchall()}
        cursor = await db.execute(
            "SELECT COUNT(*) AS c FROM users WHERE role = 'user'")
        total = (await cursor.fetchone())["c"]
    finally:
        await db.close()

    # Zero-fill every day in the window so the chart has no gaps.
    from datetime import date, timedelta
    today = date.today()
    labels, counts = [], []
    for i in range(int(days) - 1, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        labels.append(d)
        counts.append(rows.get(d, 0))
    return {"labels": labels, "counts": counts, "total": total}


async def most_viewed_schemes(limit: int = 10) -> list:
    """Schemes ordered by public view count (descending)."""
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT id, name, category, COALESCE(views, 0) AS views
               FROM schemes
               ORDER BY COALESCE(views, 0) DESC, name COLLATE NOCASE ASC
               LIMIT ?""",
            (int(limit),))
        rows = await cursor.fetchall()
    finally:
        await db.close()
    return [dict(r) for r in rows]


async def eligibility_distribution() -> dict:
    """How residents' profiles spread across the active schemes.

    Returns:
      per_scheme:  [{"name", "eligible": n}] — residents eligible per scheme
      buckets:     {"0": n, "1-2": n, "3-5": n, "6+": n} — residents grouped by
                   how many schemes they qualify for
      profiles:    number of residents with a completed profile
    """
    schemes = await scheme_service.list_schemes(only_active=True)
    users = await user_service.list_users()
    residents = [u for u in users if u.get("role") == "user"]

    per_scheme = {s["name"]: 0 for s in schemes}
    buckets = {"0": 0, "1-2": 0, "3-5": 0, "6+": 0}
    profiles = 0
    for u in residents:
        profile = user_service.get_profile(u)
        if not profile:
            continue
        profiles += 1
        matches = eligibility_service.matching_schemes(profile, schemes)
        for s in matches:
            per_scheme[s["name"]] += 1
        n = len(matches)
        if n == 0:
            buckets["0"] += 1
        elif n <= 2:
            buckets["1-2"] += 1
        elif n <= 5:
            buckets["3-5"] += 1
        else:
            buckets["6+"] += 1

    per_scheme_list = sorted(
        ({"name": k, "eligible": v} for k, v in per_scheme.items()),
        key=lambda x: x["eligible"], reverse=True)
    return {"per_scheme": per_scheme_list, "buckets": buckets, "profiles": profiles}
