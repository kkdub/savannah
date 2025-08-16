# app/main.py
from fastapi import Depends, FastAPI, HTTPException, Query, status, Path, Request, Form
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text, select
from sqlalchemy.orm import Session, joinedload
from datetime import datetime, date
from zoneinfo import ZoneInfo

from . import crud, models
from .auth import authenticate_user, get_current_user, get_current_user_api
from .database import get_db
from .schemas import Token, UserCreate, UserOut, JobResultOut
from .token import create_access_token
from .models import JobResult
from .config import settings
from .jobs.fetch_jobs import build_payload


app = FastAPI()
templates = Jinja2Templates(directory="app/templates")

# Initialize database on startup
@app.on_event("startup")
async def startup_event():
    from .database import engine, Base
    # Create tables if they don't exist
    Base.metadata.create_all(bind=engine)

@app.get("/", response_class=HTMLResponse)
def read_root(request: Request):
    return RedirectResponse(url="/login", status_code=302)

@app.get("/debug/theirstack-payload")
def debug_theirstack_payload(db: Session = Depends(get_db)):
    if not settings.DEBUG:
        raise HTTPException(status_code=404, detail="Not found")
    return build_payload(db)  # returns the JSON payload

@app.get("/debug/auth")
def debug_auth(request: Request, db: Session = Depends(get_db)):
    if not settings.DEBUG:
        raise HTTPException(status_code=404, detail="Not found")
    
    from .auth import get_token_from_cookie_or_header
    token = get_token_from_cookie_or_header(request)
    
    return {
        "has_cookie": "access_token" in request.cookies,
        "cookie_value": request.cookies.get("access_token", "None")[:50] + "..." if request.cookies.get("access_token") else None,
        "has_auth_header": "Authorization" in request.headers,
        "extracted_token": token[:20] + "..." if token else None,
        "token_length": len(token) if token else 0
    }

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

@app.post("/api/register", response_model=UserOut, status_code=status.HTTP_201_CREATED, tags=["auth"])
def register_api(payload: UserCreate, db: Session = Depends(get_db)):
    if crud.get_user_by_email(db, payload.email):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    user = crud.create_user(db, payload.email, payload.password)
    return user

@app.post("/api/login", response_model=Token, tags=["auth"])
def login_api(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = authenticate_user(db, form.username, form.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_access_token(subject=user.email)
    return {"access_token": token, "token_type": "bearer"}

@app.get("/api/me", response_model=UserOut, tags=["auth"])
def me(current_user: models.User = Depends(get_current_user)):
    return current_user

# Jobs endpoints
@app.get("/api/jobs", response_model=list[JobResultOut], tags=["jobs"])
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
        # Exclude applied jobs from main job listings
        if jr.applied_at is None:
            results.append(
                JobResultOut(
                    id=jr.id,
                    day=jr.day,
                    starred=jr.starred,
                    applied_at=jr.applied_at,
                    job=job,
                )
            )
    return results

@app.post("/api/jobs/{job_id}/star", status_code=204, tags=["jobs"])
def star_job(job_id: int, db: Session = Depends(get_db), _: models.User = Depends(get_current_user)):
    updated = crud.set_job_star(db, job_id, True)
    if updated == 0:
        raise HTTPException(status_code=404, detail="Job not found")
    return None

@app.post("/api/jobs/{job_id}/unstar", status_code=204, tags=["jobs"])
def unstar_job(job_id: int, db: Session = Depends(get_db), _: models.User = Depends(get_current_user)):
    updated = crud.set_job_star(db, job_id, False)
    if updated == 0:
        raise HTTPException(status_code=404, detail="Job not found")
    return None

@app.delete("/api/jobs/{job_id}", status_code=204, tags=["jobs"])
def delete_job(job_id: int, db: Session = Depends(get_db), _: models.User = Depends(get_current_user)):
    ok = crud.delete_job(db, job_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Job not found")
    return None

@app.post("/api/fetch-jobs", tags=["jobs"])
def fetch_jobs_manual(db: Session = Depends(get_db), _: models.User = Depends(get_current_user)):
    """Manual job fetch endpoint for authenticated users"""
    try:
        from .jobs.fetch_jobs import fetch_and_store_jobs
        fetch_and_store_jobs()
        return {"status": "success", "message": "Successfully pulled new jobs from TheirStack API"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch jobs: {str(e)}")

@app.post("/api/jobs/{job_id}/apply", status_code=204, tags=["jobs"])
def mark_job_applied(job_id: int, db: Session = Depends(get_db), _: models.User = Depends(get_current_user)):
    """Mark a job as applied with timestamp"""
    success = crud.mark_job_applied(db, job_id)
    if not success:
        raise HTTPException(status_code=404, detail="Job not found")
    return None

@app.get("/api/applied-jobs", response_model=list[JobResultOut], tags=["jobs"])
def list_applied_jobs(db: Session = Depends(get_db), _: models.User = Depends(get_current_user)):
    """Get all applied jobs with timestamps"""
    rows = crud.list_applied_jobs(db)
    results: list[JobResultOut] = []
    for job, jr in rows:
        results.append(
            JobResultOut(
                id=jr.id,
                day=jr.day,
                starred=jr.starred,
                applied_at=jr.applied_at,
                job=job,
            )
        )
    return results

@app.post("/cron/fetch-jobs", tags=["cron"])
def fetch_jobs_cron(cron_secret: str = Query(...), db: Session = Depends(get_db)):
    if cron_secret != settings.SECRET_KEY:
        raise HTTPException(status_code=401, detail="Invalid cron secret")
    
    from .jobs.fetch_jobs import fetch_and_store_jobs
    fetch_and_store_jobs()
    return {"status": "success", "message": "Jobs fetched successfully"}

# Frontend Routes
@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login", response_class=HTMLResponse)
def login_form(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = authenticate_user(db, username, password)
    if not user:
        return templates.TemplateResponse("login.html", {
            "request": request, 
            "messages": [{"type": "danger", "content": "Invalid email or password"}]
        })
    
    token = create_access_token(subject=user.email)
    response = RedirectResponse(url="/dashboard", status_code=302)
    response.set_cookie(key="access_token", value=f"Bearer {token}", httponly=True)
    return response

@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.post("/register", response_class=HTMLResponse)
def register_form(request: Request, email: str = Form(...), password: str = Form(...), confirm_password: str = Form(...), db: Session = Depends(get_db)):
    if password != confirm_password:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "messages": [{"type": "danger", "content": "Passwords do not match"}]
        })
    
    if len(password) < 8:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "messages": [{"type": "danger", "content": "Password must be at least 8 characters"}]
        })
    
    if crud.get_user_by_email(db, email):
        return templates.TemplateResponse("register.html", {
            "request": request,
            "messages": [{"type": "danger", "content": "Email already registered"}]
        })
    
    # Create user and auto-login
    user = crud.create_user(db, email, password)
    token = create_access_token(subject=user.email)
    response = RedirectResponse(url="/dashboard", status_code=302)
    response.set_cookie(key="access_token", value=f"Bearer {token}", httponly=True)
    return response

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})

@app.get("/applied", response_class=HTMLResponse)
def applied_jobs_page(request: Request):
    return templates.TemplateResponse("applied.html", {"request": request})

@app.get("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(key="access_token")
    return response
