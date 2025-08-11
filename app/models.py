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
