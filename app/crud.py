from sqlalchemy.orm import Session
from . import models
from .security import hash_password

def get_user_by_email(db: Session, email: str) -> models.User | None:
    return db.query(models.User).filter(models.User.email == email).first()

def create_user(db: Session, email: str, password: str) -> models.User:
    user = models.User(email=email, hashed_password=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
    from datetime import datetime
from sqlalchemy.orm import Session
from .models import IngestState

def get_last_fetch(db: Session) -> datetime | None:
    row = db.query(IngestState).order_by(IngestState.id.asc()).first()
    return row.last_fetch_at if row else None

def set_last_fetch(db: Session, when: datetime) -> None:
    row = db.query(IngestState).order_by(IngestState.id.asc()).first()
    if not row:
        row = IngestState(last_fetch_at=when)
        db.add(row)
    else:
        row.last_fetch_at = when
    db.commit()
    
    # --- Jobs & Daily Results ---

from datetime import date
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import Job, JobResult

def upsert_job_from_theirstack(db: Session, j: dict) -> Job:
    """
    j is one job dict from TheirStack response. We map the key fields.
    """
    ext_id = str(j.get("job_id") or j.get("id"))
    assert ext_id, "TheirStack job must have job_id"

    row = db.execute(select(Job).where(Job.external_id == ext_id)).scalar_one_or_none()
    if row is None:
        row = Job(external_id=ext_id)
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

def ensure_job_result_for_day(db: Session, job: Job, day_tag: date) -> JobResult:
    existing = db.execute(
        select(JobResult).where(JobResult.job_id == job.id, JobResult.day == day_tag)
    ).scalar_one_or_none()
    if existing:
        return existing
    jr = JobResult(job_id=job.id, day=day_tag, starred=False)
    db.add(jr)
    db.flush()
    return jr

def prune_old_results(db: Session, keep_days: int = 14) -> int:
    """
    Delete JobResult older than keep_days. Then delete Jobs with no remaining results.
    Returns number of JobResult rows deleted (approx).
    """
    from datetime import timedelta, datetime as dt
    cutoff_day = (dt.utcnow().date() - timedelta(days=keep_days))

    # delete old results
    del_results = db.execute(
        JobResult.__table__.delete().where(JobResult.day < cutoff_day)
    ).rowcount or 0

    # delete orphan jobs
    db.execute(
        Job.__table__.delete().where(
            ~Job.id.in_(select(JobResult.job_id))  # jobs with no results left
        )
    )
    return del_results