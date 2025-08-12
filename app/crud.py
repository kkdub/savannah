from __future__ import annotations
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models, security

def get_user_by_email(db: Session, email: str) -> models.User | None:
    return db.query(models.User).filter(models.User.email == email).first()

def create_user(db: Session, email: str, password: str) -> models.User:
    hashed_pw = security.hash_password(password)
    user = models.User(email=email, hashed_password=hashed_pw)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

def get_last_fetch(db: Session) -> datetime | None:
    row = db.query(models.IngestState).order_by(models.IngestState.id.asc()).first()
    return row.last_fetch_at if row else None

def set_last_fetch(db: Session, when: datetime) -> None:
    row = db.query(models.IngestState).order_by(models.IngestState.id.asc()).first()
    if not row:
        row = models.IngestState(last_fetch_at=when)
        db.add(row)
    else:
        row.last_fetch_at = when
    db.commit()

def upsert_job_from_theirstack(db: Session, j: dict) -> models.Job:
    """
    j is one job dict from TheirStack response. We map the key fields.
    """
    ext_id = str(j.get("job_id") or j.get("id"))
    assert ext_id, "TheirStack job must have job_id"

    row = db.execute(select(models.Job).where(models.Job.external_id == ext_id)).scalar_one_or_none()
    if row is None:
        row = models.Job(external_id=ext_id)
        db.add(row)

    row.title = j.get("job_title") or ""
    row.company = j.get("company_name") or ""
    row.location = j.get("job_location") or ""
    row.url = j.get("job_url") or j.get("url") or None
    row.posted_at = j.get("posted_at")
    row.discovered_at = j.get("discovered_at")
    row.raw = j  # keep full source

    db.flush()  # get row.id if new
    return row

def ensure_job_result_for_day(db: Session, job: models.Job, day_tag: date) -> models.JobResult:
    existing = db.execute(
        select(models.JobResult).where(models.JobResult.job_id == job.id, models.JobResult.day == day_tag)
    ).scalar_one_or_none()
    if existing:
        return existing
    jr = models.JobResult(job_id=job.id, day=day_tag, starred=False)
    db.add(jr)
    db.flush()
    return jr

def prune_old_results(db: Session, keep_days: int = 14) -> int:
    """
    Delete JobResult older than keep_days. Then delete Jobs with no remaining results.
    Returns number of JobResult rows deleted (approx).
    """
    cutoff_day = (datetime.now(timezone.utc).date() - timedelta(days=keep_days))

    # delete old results
    del_results = db.execute(
        models.JobResult.__table__.delete().where(models.JobResult.day < cutoff_day)
    ).rowcount or 0

    # delete orphan jobs
    db.execute(
        models.Job.__table__.delete().where(
            ~models.Job.id.in_(select(models.JobResult.job_id))  # jobs with no results left
        )
    )
    return del_results