from __future__ import annotations
import os
import re
import requests
from pathlib import Path
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo

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

# Text files with one title per line (optional; used if present)
REPO_ROOT = Path(os.getenv("REPO_ROOT", "."))
INCLUDE_TITLES_FILE = REPO_ROOT / "Job Titles.txt"
EXCLUDE_TITLES_FILE = REPO_ROOT / "Job Title Exclude.txt"

# Country list we agreed: US + high‑wage markets
HIGH_WAGE_COUNTRIES = ["US", "CH", "LU", "NO", "DK", "SG", "AU"]


def _read_lines_strip(path: Path) -> list[str]:
    try:
        return [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    except FileNotFoundError:
        return []


def _today_et_date() -> datetime.date:
    ny = ZoneInfo("America/New_York")
    return datetime.now(ny).date()


def _default_discovered_gte_iso(last_fetch: datetime | None) -> str:
    """If we’ve fetched before, only ask TheirStack for jobs discovered since then.
       Otherwise default to yesterday 6:00 AM ET in UTC.
    """
    utc = ZoneInfo("UTC")
    if last_fetch:
        return last_fetch.astimezone(utc).isoformat()
    ny = ZoneInfo("America/New_York")
    yday = datetime.now(ny).date() - timedelta(days=1)
    yday_6am = datetime.combine(yday, time(6, 0), tzinfo=ny)
    return yday_6am.astimezone(utc).isoformat()


def build_payload(db: Session) -> dict:
    discovered_gte = _default_discovered_gte_iso(get_last_fetch(db))

    # Base payload with agreed server‑side filters
    payload: dict = {
        "limit": 50,  # agreed
        "order_by": [{"field": "date_posted", "desc": True}],
        "posted_at_max_age_days": 1,  # agreed (last 1 day)
        "discovered_at_gte": discovered_gte,
        "job_location_pattern_or": ["remote"],  # agreed
        "job_country_code_or": HIGH_WAGE_COUNTRIES,  # agreed
        "company_name_not": ["IBM", "Capgemini"],  # agreed
        "include_total_results": False,
    }

    # Optionally read include/exclude titles from text files
    include_titles = _read_lines_strip(INCLUDE_TITLES_FILE)
    exclude_titles = _read_lines_strip(EXCLUDE_TITLES_FILE)

    # Respect settings if provided; otherwise use files
    if settings.FILTER_APPLY_SERVER_SIDE:
        # Title includes: settings first, else from file if present
        if getattr(settings, "FILTER_TITLE_KEYWORDS", None):
            payload["job_title_pattern_or"] = settings.FILTER_TITLE_KEYWORDS
        elif include_titles:
            payload["job_title_pattern_or"] = include_titles

        # Title excludes: we only have "pattern_not" server‑side; use settings or file
        if getattr(settings, "FILTER_TITLE_EXCLUDE", None):
            payload["job_title_pattern_not"] = settings.FILTER_TITLE_EXCLUDE
        elif exclude_titles:
            payload["job_title_pattern_not"] = exclude_titles

        # Optional description keywords (if you’ve configured them)
        if getattr(settings, "FILTER_DESC_KEYWORDS", None):
            payload["job_description_pattern_or"] = settings.FILTER_DESC_KEYWORDS

        # Optional additional company deny list from settings (merged)
        if getattr(settings, "FILTER_COMPANY_DENY", None):
            payload["company_name_not"] = list({
                *(payload.get("company_name_not") or []),
                *settings.FILTER_COMPANY_DENY
            })

        # Optional additional location allows from settings (merged)
        if getattr(settings, "FILTER_LOCATION_ALLOW", None):
            payload["job_location_pattern_or"] = list({
                *(payload.get("job_location_pattern_or") or []),
                *settings.FILTER_LOCATION_ALLOW
            })

    return payload


# ---------- Local post‑fetch filtering (unchanged) ----------

def _text_contains_any(text: str, needles: list[str], require_word_boundaries: bool = False) -> bool:
    t = text or ""
    if not needles:
        return False
    if require_word_boundaries:
        pat = r"\b(?:" + "|".join(re.escape(n) for n in needles) + r")\b"
        return re.search(pat, t, flags=re.IGNORECASE) is not None
    tl = t.lower()
    return any(n.lower() in tl for n in needles)


def _matches_any_regex(text: str, patterns: list[str]) -> bool:
    if not patterns:
        return False
    t = text or ""
    return any(re.search(p, t, flags=re.IGNORECASE) is not None for p in patterns)


def _passes_local_filters(job: dict) -> bool:
    """Apply local allow/deny filters based on settings.

    Permit a job if:
    - Title/desc filters: when any title/desc filter is configured, require that title OR desc matches at least one.
    - Location allow list: when provided, location must match.
    - Company deny list: when provided, company must NOT match.
    """
    title = job.get("job_title") or job.get("title") or ""
    desc = job.get("job_description") or job.get("description") or ""
    company = job.get("company_name") or job.get("company") or ""
    location = job.get("job_location") or job.get("location") or ""

    has_title_filters = bool(settings.FILTER_TITLE_KEYWORDS or settings.FILTER_TITLE_REGEX)
    has_desc_filters = bool(settings.FILTER_DESC_KEYWORDS or settings.FILTER_DESC_REGEX)
    has_any_text_filters = has_title_filters or has_desc_filters

    title_match = False
    if has_title_filters:
        title_kw = _text_contains_any(title, settings.FILTER_TITLE_KEYWORDS, settings.FILTER_REQUIRE_WORD_BOUNDARIES)
        title_rx = _matches_any_regex(title, settings.FILTER_TITLE_REGEX)
        title_match = title_kw or title_rx

    desc_match = False
    if has_desc_filters:
        desc_kw = _text_contains_any(desc, settings.FILTER_DESC_KEYWORDS, settings.FILTER_REQUIRE_WORD_BOUNDARIES)
        desc_rx = _matches_any_regex(desc, settings.FILTER_DESC_REGEX)
        desc_match = desc_kw or desc_rx

    text_ok = (title_match or desc_match) if has_any_text_filters else True
    loc_ok = _text_contains_any(location, settings.FILTER_LOCATION_ALLOW) if settings.FILTER_LOCATION_ALLOW else True
    company_ok = not _text_contains_any(company, settings.FILTER_COMPANY_DENY) if settings.FILTER_COMPANY_DENY else True
    return text_ok and loc_ok and company_ok


# ---------- Main fetch/store ----------

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