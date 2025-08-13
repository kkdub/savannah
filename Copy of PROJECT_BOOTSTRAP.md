# Savannah App – Project Bootstrap & Setup Guide

This file serves both as a **memory bootstrap** for ChatGPT if the environment is reset and as a complete **local/deployment guide**.

---

## Section 1 – Project Memory Bootstrap

### Project Summary
FastAPI-based application to show daily, pre-filtered job search results from the TheirStack API.  
Two users share the same job list. Jobs are fetched daily at **6:00 AM ET** using TheirStack server-side filters (RE2 regex) and local filtering based on resume keywords/titles.

### Current State
- **Auth**: JWT-based, `/register`, `/login`, `/me` fully implemented.
- **Database**: SQLAlchemy + Alembic.
- **Models**:
  - `User`
  - `IngestState` – last fetch timestamp
  - `Job` – job details + raw payload
  - `JobResult` – links jobs to a date tag, supports starring
- **CRUD helpers**: users, ingestion state, job upsert, daily tag, prune old jobs
- **Fetch job**:  
  - Path: `app/jobs/fetch_jobs.py`  
  - Uses `discovered_at_gte` from `IngestState`  
  - Saves jobs, tags by day, prunes jobs older than 14 days  
  - Manual run or scheduled in DO
- **Environment variables**:
  - `SECRET_KEY`, `DATABASE_URL`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `THEIRSTACK_API_KEY`, `DB_URL`
- **Retention**: 14 days or manual delete
- **User experience**: star jobs, view in dashboard (frontend TBD)
- **Resume source**: PDF/DOCX, manually processed offline
- **Filtering**:  
  - Server-side: allowed TheirStack regex patterns  
  - Local: resume-derived keywords, titles, disallow lists
- **Run time**: 6:00 AM ET daily (weekends too)

### File Structure
```
<repo-root>/
├── .env
├── requirements.txt
├── app.yaml
├── alembic.ini
├── alembic/
│   ├── env.py
│   └── versions/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── models.py
│   ├── schemas.py
│   ├── crud.py
│   ├── database.py
│   ├── auth.py
│   ├── token.py
│   ├── security.py
│   ├── config.py
│   ├── jobs/
│   │    ├── __init__.py
│   │    └── fetch_jobs.py
└── scripts/
    └── sqlite_to_postgres.py
```

### Decisions
1. Keep fetch job in `app/jobs/fetch_jobs.py`.
2. Use `discovered_at_gte` to fetch only new jobs.
3. Store last fetch in `IngestState`.
4. Save raw TheirStack payload in `Job.raw`.
5. Retain for 14 days, prune daily.
6. One shared job list for both users.
7. Env vars for secrets/DB.

### Outstanding To-Dos
- [ ] `/jobs` API endpoints (list, star/unstar, delete)
- [ ] Local post-fetch filtering
- [ ] Resume keyword/title integration
- [ ] Schedule fetch at 6:00 AM ET in DO
- [ ] Deploy to DO with Managed Postgres
- [ ] Dashboard UI

### Local Quick Run
```powershell
cd "$env:USERPROFILE\Documents\Projects\<your-repo>"
. .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:DATABASE_URL = "sqlite:///./savannah.db"
$env:DB_URL = $env:DATABASE_URL
alembic upgrade head
$env:THEIRSTACK_API_KEY = "<your_theirstack_api_key>"
python -m app.jobs.fetch_jobs
```

---

## Section 2 – Full Setup & Deployment Guide

### 0. Clone Your Repo (Windows)
```powershell
cd "$env:USERPROFILE\Documents\Projects"
git clone https://github.com/<your-username>/<your-repo>.git
cd <your-repo>
```

---

### 1. Environment Setup
```powershell
py -m venv .venv
. .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
Create `.env`:
```
SECRET_KEY=change-me
DATABASE_URL=sqlite:///./savannah.db
ACCESS_TOKEN_EXPIRE_MINUTES=60
```

---

### 2. Verify Local Run (SQLite)
```powershell
uvicorn app.main:app --reload
```
Visit:
- Swagger: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/health

---

### 3. Auth Smoke Test
```powershell
# Register
curl -X POST http://127.0.0.1:8000/register `
  -H "Content-Type: application/json" `
  -d '{"email":"test@example.com","password":"secret123"}'

# Login
$TOKEN = curl -s -X POST http://127.0.0.1:8000/login `
  -H "Content-Type: application/x-www-form-urlencoded" `
  -d "username=test@example.com&password=secret123" | `
  python -c "import sys,json; print(json.load(sys.stdin)['access_token'])"

# Protected route
curl http://127.0.0.1:8000/me -H "Authorization: Bearer $TOKEN"
```

---

### 4. Switch to Local Postgres
```powershell
docker run --name savannah-db -e POSTGRES_PASSWORD=postgres -p 5432:5432 -d postgres:16
$env:DATABASE_URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/postgres"
$env:DB_URL = $env:DATABASE_URL
alembic upgrade head
alembic current
```

---

### 5. Optional Data Migration
```powershell
$env:SQLITE_URL="sqlite:///./savannah.db"
$env:PG_URL="postgresql+psycopg2://postgres:postgres@localhost:5432/postgres"
$env:DB_URL=$env:PG_URL
alembic upgrade head
python scripts/sqlite_to_postgres.py
```

---

### 6. Alembic Conflict Resolution

**If `alembic/env.py` has a merge conflict:**

#### Final `alembic/env.py`
```python
from __future__ import annotations
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Load .env locally; no-op in prod
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# Alembic Config
config = context.config

# Set DB URL from env (SQLite locally; Postgres in prod)
db_url = os.getenv("DATABASE_URL", "sqlite:///./savannah.db")
config.set_main_option("sqlalchemy.url", db_url)

# Logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata (import Base + ensure models are registered)
from app.database import Base  # noqa: E402
from app import models as _models  # noqa: F401,E402

target_metadata = Base.metadata

def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

**Conflict resolution steps:**
1. Pull latest from GitHub.
2. Open `alembic/env.py` → select all → paste the above.
3. Remove merge markers (`<<<<<<<`, `=======`, `>>>>>>>`).
4. Mark resolved → commit → push.

---

### 7. First Alembic Run After Conflict
```powershell
.venv\Scripts\activate
$env:DB_URL=$env:DATABASE_URL

# Create migration if none exists
alembic revision --autogenerate -m "init schema"

# Apply
alembic upgrade head

# Verify
alembic current
```

---

### 8. Deploy to DO App Platform
1. Push to GitHub.
2. Ensure `app.yaml` contains env vars and run command:
   ```
   run_command: uvicorn app.main:app --host 0.0.0.0 --port $PORT
   ```
3. Create Managed Postgres in DO, copy connection string, update `DATABASE_URL` in App Platform.
4. Deploy.
5. Run migrations in DO console:
   ```bash
   alembic upgrade head
   ```
6. Test:
   - `https://<your-app>/health`
   - `https://<your-app>/docs`

---

### Final Expected Directory Tree
```
<repo-root>/
├── .env                  # local only, not committed
├── requirements.txt      # pinned versions
├── app.yaml              # DO App Platform config
├── alembic.ini
├── alembic/
│   ├── env.py
│   ├── versions/
│   │   └── <migration>.py
│
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── models.py
│   ├── schemas.py
│   ├── crud.py
│   ├── database.py
│   ├── auth.py
│   ├── token.py
│   ├── security.py
│   ├── config.py
│   ├── jobs/
│   │    ├── __init__.py
│   │    └── fetch_jobs.py
│
└── scripts/
    └── sqlite_to_postgres.py
```

---

### Windows Quick Steps (PowerShell)
```powershell
# 0) Go to your repo
cd "$env:USERPROFILE\Documents\Projects\<your-repo>"

# 1) Activate venv (create if missing)
if (-not (Test-Path .venv)) { py -m venv .venv }
. .\.venv\Scripts\Activate.ps1

# 2) Install dependencies
pip install -r requirements.txt

# 3) Choose DB
# SQLite (default):
$env:DATABASE_URL = "sqlite:///./savannah.db"

# OR Postgres (optional):
# $env:DATABASE_URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/postgres"

# 4) Alembic migrations
$env:DB_URL = $env:DATABASE_URL
# Create migration (if not already created):
# alembic revision --autogenerate -m "jobs + job_results + ingest_state"
alembic upgrade head
alembic current   # should show 'head'

# 5) Run API locally
uvicorn app.main:app --reload
# Visit http://127.0.0.1:8000/health and /docs
# Ctrl+C to stop the server

# 6) Run fetch job manually
$env:THEIRSTACK_API_KEY = "<your_theirstack_api_key>"
python -m app.jobs.fetch_jobs

# 7) Quick auth smoke test
# Register
curl -X POST http://127.0.0.1:8000/register `
  -H "Content-Type: application/json" `
  -d '{"email":"test@example.com","password":"secret123"}'

# Login
$TOKEN = curl -s -X POST http://127.0.0.1:8000/login `
  -H "Content-Type: application/x-www-form-urlencoded" `
  -d "username=test@example.com&password=secret123" | `
  python -c "import sys,json; print(json.load(sys.stdin)['access_token'])"

# Protected route
curl http://127.0.0.1:8000/me -H "Authorization: Bearer $TOKEN"

# 8) Re-run fetch as needed (uses saved state)
python -m app.jobs.fetch_jobs
```
