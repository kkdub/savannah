from __future__ import annotations
import os
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
import requests

from sqlalchemy.orm import Session
from .database import SessionLocal
from .crud import get_last_fetch, set_last_fetch, upsert_job_from_theirstack, ensure_job_result_for_day, prune_old_results

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
        # TODO: fill these from your keyword/title lists
        # "job_title_pattern_or": [...],
        # "job_description_pattern_or": [...],
        # "company_name_not": [...],
        # "job_location_pattern_or": ["remote", "anywhere", "usa-remote"],
    }
    return payload

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