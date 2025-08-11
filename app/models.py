# app/models.py
from __future__ import annotations
from datetime import datetime
from sqlalchemy import String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # RFC 5321 cap is 320 chars; unique + indexed for login lookups
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, timezone

class IngestState(Base):
    __tablename__ = "ingest_state"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    last_fetch_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime(1970, 1, 1, tzinfo=timezone.utc)
    )
    
    # --- Jobs & Daily Results ---

from sqlalchemy import String, DateTime, Date, ForeignKey, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime

class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    external_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)  # TheirStack job_id
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    company: Mapped[str] = mapped_column(String(512), nullable=True)
    location: Mapped[str] = mapped_column(String(512), nullable=True)
    url: Mapped[str] = mapped_column(String(2048), nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    discovered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # full payload for later use

    results: Mapped[list["JobResult"]] = relationship(back_populates="job", cascade="all, delete-orphan")

class JobResult(Base):
    __tablename__ = "job_results"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True, nullable=False)
    day: Mapped[datetime.date] = mapped_column(Date, index=True, nullable=False)  # the "daily list" tag
    starred: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    job: Mapped[Job] = relationship(back_populates="results")

# make (job_id, day) unique so the same job doesn’t duplicate in one day
Index("uq_job_results_job_day", JobResult.job_id, JobResult.day, unique=True)
