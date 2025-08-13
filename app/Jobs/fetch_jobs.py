from __future__ import annotations
import os
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
import requests

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.crud import (
    get_last_fetch,
    set_last_fetch,
    upsert_job_from_theirstack,
    ensure_job_result_for_day,
    prune_old_results,
)
from app.config import settings

THEIRSTACK_API_KEY = os.getenv("THEIRSTACK_API_KEY")
THEIRSTACK_URL = "https://api.theirstack.com/v1/jobs/search"


def _today_et_date() -> datetime.date:
    ny = ZoneInfo("America/New_York")
    return datetime.now(ny).date()


def _default_discovered_gte_iso(last_fetch: datetime | None) -> str:
    utc = ZoneInfo("UTC")
    if last_fetch:
        return last_fetch.astimezone(utc).isoformat()
    ny = ZoneInfo("America/New_York")
    yday = datetime.now(ny).date() - timedelta(days=1)
    yday_6am = datetime.combine(yday, time(6, 0), tzinfo=ny)
    return yday_6am.astimezone(utc).isoformat()


def build_payload(db: Session) -> dict:
    discovered_gte = _default_discovered_gte_iso(get_last_fetch(db))
    payload = {
        "limit": 100,
        "order_by": [{"field": "date_posted", "desc": True}],
        "discovered_at_gte": discovered_gte,
    }
    # Optionally set server-side filters from settings
    if settings.FILTER_TITLE_KEYWORDS:
        payload["job_title_pattern_or"] = settings.FILTER_TITLE_KEYWORDS
    if settings.FILTER_DESC_KEYWORDS:
        payload["job_description_pattern_or"] = settings.FILTER_DESC_KEYWORDS
    if settings.FILTER_COMPANY_DENY:
        payload["company_name_not"] = settings.FILTER_COMPANY_DENY
    if settings.FILTER_LOCATION_ALLOW:
        payload["job_location_pattern_or"] = settings.FILTER_LOCATION_ALLOW
    return payload


def _text_contains_any(text: str, needles: list[str]) -> bool:
    t = (text or "").lower()
    return any(n.lower() in t for n in needles)


def _passes_local_filters(job: dict) -> bool:
    """Apply local allow/deny filters based on settings.

    Allow if any of title/desc contains title/desc keywords AND location matches allow list (if provided),
    and the company is not in deny list.
    If lists are empty, treat as permissive for that dimension.
    """
    title_ok = True
    desc_ok = True
    loc_ok = True
    company_ok = True

    title = job.get("job_title") or job.get("title") or ""
    desc = job.get("job_description") or job.get("description") or ""
    company = job.get("company_name") or job.get("company") or ""
    location = job.get("job_location") or job.get("location") or ""

    if settings.FILTER_TITLE_KEYWORDS:
        title_ok = _text_contains_any(title, settings.FILTER_TITLE_KEYWORDS)
    if settings.FILTER_DESC_KEYWORDS:
        desc_ok = _text_contains_any(desc, settings.FILTER_DESC_KEYWORDS)
    if settings.FILTER_LOCATION_ALLOW:
        loc_ok = _text_contains_any(location, settings.FILTER_LOCATION_ALLOW)
    if settings.FILTER_COMPANY_DENY:
        company_ok = not _text_contains_any(company, settings.FILTER_COMPANY_DENY)

    return (title_ok or desc_ok) and loc_ok and company_ok


def fetch_and_store_jobs():
    if not THEIRSTACK_API_KEY:
        raise RuntimeError("Set THEIRSTACK_API_KEY env var")

    db = SessionLocal()
    try:
        payload = build_payload(db)
        headers = {"Authorization": f"Bearer {THEIRSTACK_API_KEY}"}
        r = requests.post(THEIRSTACK_URL, json=payload, headers=headers, timeout=60)
        r.raise_for_status()
        data = r.json()
        jobs = data.get("jobs") or data.get("results") or []

        # Apply local filtering
        jobs = [j for j in jobs if _passes_local_filters(j)]

        today_tag = _today_et_date()
        saved = 0
        for j in jobs:
            job = upsert_job_from_theirstack(db, j)
            ensure_job_result_for_day(db, job, today_tag)
            saved += 1
        db.commit()

        prune_old_results(db)
        db.commit()

        set_last_fetch(db, datetime.now(tz=ZoneInfo("UTC")))
        print(f"[ok] saved {saved} jobs for {today_tag}")

    except Exception as e:
        db.rollback()
        print("[error] fetch_and_store_jobs:", e)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    fetch_and_store_jobs()