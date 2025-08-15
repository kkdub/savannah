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

    # Base payload with CORRECT TheirStack API parameters (verified from API docs)
    payload: dict = {
        "limit": 50,
        "order_by": [{"field": "date_posted", "desc": True}],
        "posted_at_max_age_days": 1,
        "discovered_at_gte": discovered_gte,
        "remote": True,  # ✅ CORRECT: Boolean flag for remote jobs
        "job_country_code_or": settings.FILTER_TARGET_COUNTRIES,  # ✅ ISO2 country codes
        "min_salary_usd": settings.FILTER_MIN_SALARY_USD,  # ✅ Salary filtering
        "max_salary_usd": settings.FILTER_MAX_SALARY_USD,  # ✅ Salary filtering
        "min_employee_count": settings.FILTER_MIN_EMPLOYEE_COUNT,  # ✅ Company size
        "include_total_results": False,
    }

    # Add max employee count only if specified
    if settings.FILTER_MAX_EMPLOYEE_COUNT is not None:
        payload["max_employee_count"] = settings.FILTER_MAX_EMPLOYEE_COUNT

    # Read include/exclude titles from text files (fallback)
    include_titles = _read_lines_strip(INCLUDE_TITLES_FILE)
    exclude_titles = _read_lines_strip(EXCLUDE_TITLES_FILE)

    if settings.FILTER_APPLY_SERVER_SIDE:
        # ✅ CORRECT: Title exact matches (job_title_or)
        title_keywords = settings.FILTER_TITLE_KEYWORDS or include_titles
        if title_keywords:
            payload["job_title_or"] = title_keywords

        # ✅ CORRECT: Title regex patterns (job_title_pattern_or)
        title_patterns = list(settings.FILTER_TITLE_REGEX) if settings.FILTER_TITLE_REGEX else []
        
        # ✅ CORRECT: Title exclusions (job_title_pattern_not)
        exclude_list = settings.FILTER_TITLE_EXCLUDE or exclude_titles
        if exclude_list:
            payload["job_title_pattern_not"] = exclude_list
        
        # Add regex patterns if any
        if title_patterns:
            payload["job_title_pattern_or"] = title_patterns

        # ✅ CORRECT: Description patterns (job_description_pattern_or)
        if settings.FILTER_DESC_KEYWORDS:
            # Convert keywords to regex with word boundaries if needed
            desc_patterns = []
            for keyword in settings.FILTER_DESC_KEYWORDS:
                if settings.FILTER_REQUIRE_WORD_BOUNDARIES:
                    desc_patterns.append(f"\\b{re.escape(keyword)}\\b")
                else:
                    desc_patterns.append(re.escape(keyword))
            payload["job_description_pattern_or"] = desc_patterns
        
        # Add explicit regex patterns for descriptions
        if settings.FILTER_DESC_REGEX:
            existing_desc = payload.get("job_description_pattern_or", [])
            payload["job_description_pattern_or"] = existing_desc + list(settings.FILTER_DESC_REGEX)

    # ✅ CORRECT: Company exclusions (company_name_not)
    company_blacklist = ["IBM", "Capgemini"]  # Hardcoded base list
    if settings.FILTER_COMPANY_DENY:
        company_blacklist.extend(settings.FILTER_COMPANY_DENY)
    if company_blacklist:
        payload["company_name_not"] = company_blacklist

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