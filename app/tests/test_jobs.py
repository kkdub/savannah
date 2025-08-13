from datetime import date
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
