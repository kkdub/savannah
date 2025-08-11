# app/database.py
from __future__ import annotations
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy.engine.url import make_url

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./savannah.db")

# Decide connect_args based on scheme
connect_args = {}
try:
    url = make_url(DATABASE_URL)
    if url.drivername.startswith("sqlite"):
        # needed for SQLite in single-process dev
        connect_args = {"check_same_thread": False}
    # For Postgres (psycopg or psycopg2), no special connect_args needed.
    # TLS (sslmode=require) should be specified in the DATABASE_URL query string when needed.
except Exception:
    # Fallback (be permissive)
    if DATABASE_URL.startswith("sqlite"):
        connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

class Base(DeclarativeBase):
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
