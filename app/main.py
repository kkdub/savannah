# app/main.py
from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import text
from sqlalchemy.orm import Session

from . import crud, models
from .auth import authenticate_user, get_current_user
from .database import get_db
from .schemas import Token, UserCreate, UserOut, JobResultOut
from .token import create_access_token

from datetime import datetime, date
from zoneinfo import ZoneInfo
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload
from fastapi import Depends, Query, HTTPException, Path

from .database import get_db
from .models import JobResult
from .schemas import JobResultOut

app = FastAPI()

@app.get("/health", tags=["monitoring"])
def health_check(db: Session = Depends(get_db)):
    """
    Checks if the application is healthy, including the database connection.
    """
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "ok"}
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database connection error"
        )

@app.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED, tags=["auth"])
def register(payload: UserCreate, db: Session = Depends(get_db)):
    if crud.get_user_by_email(db, payload.email):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    user = crud.create_user(db, payload.email, payload.password)
    return user

@app.post("/login", response_model=Token, tags=["auth"])
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = authenticate_user(db, form.username, form.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_access_token(subject=user.email)
    return {"access_token": token, "token_type": "bearer"}

@app.get("/me", response_model=UserOut, tags=["auth"])
def me(current_user: models.User = Depends(get_current_user)):
    return current_user

# Jobs endpoints
@app.get("/jobs", response_model=list[JobResultOut], tags=["jobs"])
def list_jobs(
    day: str | None = Query(None, description="ISO date YYYY-MM-DD; defaults to latest day"),
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    from datetime import date
    if day:
        try:
            target_day = date.fromisoformat(day)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid day format; expected YYYY-MM-DD")
    else:
        latest = crud.get_latest_day(db)
        if not latest:
            return []
        target_day = latest

    rows = crud.list_jobs_for_day(db, target_day)
    results: list[JobResultOut] = []
    for job, jr in rows:
        results.append(
            JobResultOut(
                day=jr.day,
                starred=jr.starred,
                job=job,
            )
        )
    return results

@app.post("/jobs/{job_id}/star", status_code=204, tags=["jobs"])
def star_job(job_id: int, db: Session = Depends(get_db), _: models.User = Depends(get_current_user)):
    updated = crud.set_job_star(db, job_id, True)
    if updated == 0:
        raise HTTPException(status_code=404, detail="Job not found")
    return None

@app.post("/jobs/{job_id}/unstar", status_code=204, tags=["jobs"])
def unstar_job(job_id: int, db: Session = Depends(get_db), _: models.User = Depends(get_current_user)):
    updated = crud.set_job_star(db, job_id, False)
    if updated == 0:
        raise HTTPException(status_code=404, detail="Job not found")
    return None

@app.delete("/jobs/{job_id}", status_code=204, tags=["jobs"])
def delete_job(job_id: int, db: Session = Depends(get_db), _: models.User = Depends(get_current_user)):
    ok = crud.delete_job(db, job_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Job not found")
    return None

@app.get("/jobs", response_model=list[JobResultOut])
def list_jobs(
    day: date | None = Query(None, description="YYYY-MM-DD; defaults to today (America/New_York)"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    # Default to "today" in ET
    if day is None:
        day = datetime.now(ZoneInfo("America/New_York")).date()

    stmt = (
        select(JobResult)
        .options(joinedload(JobResult.job))
        .where(JobResult.day == day)
        .order_by(JobResult.id.desc())
        .limit(limit)
    )
    rows = db.execute(stmt).scalars().all()
    return rows

@app.patch("/jobs/{job_result_id}/star", response_model=JobResultOut)
def star_job_result(
    job_result_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
):
    jr = db.get(JobResult, job_result_id)
    if not jr:
        raise HTTPException(status_code=404, detail="JobResult not found")
    jr.starred = True
    db.commit()
    db.refresh(jr)
    return jr

@app.patch("/jobs/{job_result_id}/unstar", response_model=JobResultOut)
def unstar_job_result(
    job_result_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
):
    jr = db.get(JobResult, job_result_id)
    if not jr:
        raise HTTPException(status_code=404, detail="JobResult not found")
    jr.starred = False
    db.commit()
    db.refresh(jr)
    return jr