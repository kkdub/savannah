from datetime import date
import os
import pytest
from sqlalchemy.orm import Session

from app.crud import ensure_job_result_for_day, upsert_job_from_theirstack
from app.models import Job


def _seed_job(db: Session, title="Engineer") -> Job:
    jsrc = {
        "job_id": "ext-1",
        "job_title": title,
        "company_name": "Acme",
        "job_location": "Remote",
        "job_url": "https://example.com/job/1",
    }
    job = upsert_job_from_theirstack(db, jsrc)
    ensure_job_result_for_day(db, job, date.today())
    db.commit()
    return job


def _auth_headers(client):
    # register and login
    client.post("/register", json={"email": "jobs@example.com", "password": "secret123"})
    tok = client.post(
        "/login",
        data={"username": "jobs@example.com", "password": "secret123"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def test_list_jobs_latest_day(client, db_session):
    _seed_job(db_session)
    headers = _auth_headers(client)
    r = client.get("/jobs", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    item = data[0]
    assert set(["day", "starred", "job"]).issubset(item.keys())
    assert set(["id", "title"]).issubset(item["job"].keys())


def test_star_and_unstar_job(client, db_session):
    job = _seed_job(db_session)
    headers = _auth_headers(client)
    # star
    r = client.post(f"/jobs/{job.id}/star", headers=headers)
    assert r.status_code == 204
    # unstar
    r = client.post(f"/jobs/{job.id}/unstar", headers=headers)
    assert r.status_code == 204


def test_delete_job(client, db_session):
    job = _seed_job(db_session, title="ToDelete")
    headers = _auth_headers(client)
    r = client.delete(f"/jobs/{job.id}", headers=headers)
    assert r.status_code == 204


def test_filter_word_boundaries_env(monkeypatch, db_session):
    # Ensure 'go' does not match 'Django' when boundaries required
    monkeypatch.setenv("FILTER_TITLE_KEYWORDS", "[\"go\"]")
    monkeypatch.setenv("FILTER_REQUIRE_WORD_BOUNDARIES", "true")
    from importlib import reload
    import sys
    # Ensure project root is on path for dynamic import
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if root not in sys.path:
        sys.path.insert(0, root)
    from app import config
    reload(config)
    from app.jobs import fetch_jobs as fj
    reload(fj)
    j1 = {"job_title": "Senior Django Engineer"}
    j2 = {"job_title": "Go Developer"}
    assert fj._passes_local_filters(j1) is False
    assert fj._passes_local_filters(j2) is True


def test_filter_regex_env(monkeypatch, db_session):
    # Use regex to require 'python' and 'fastapi' in description regardless of order
    monkeypatch.setenv("FILTER_DESC_REGEX", "[\"python\",\"fastapi\"]")
    from importlib import reload
    import sys
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if root not in sys.path:
        sys.path.insert(0, root)
    from app import config
    reload(config)
    from app.jobs import fetch_jobs as fj
    reload(fj)
    j1 = {"job_title": "Any", "job_description": "We use Python and FastAPI daily"}
    j2 = {"job_title": "Any", "job_description": "We use Java and Spring"}
    assert fj._passes_local_filters(j1) is True
    assert fj._passes_local_filters(j2) is False
