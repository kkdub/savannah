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