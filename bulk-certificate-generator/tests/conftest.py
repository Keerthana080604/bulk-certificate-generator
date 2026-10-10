"""Shared fixtures: every test gets its OWN temp database and output directory."""
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture()
def settings(tmp_path):
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        output_dir=tmp_path / "certs",
    )


@pytest.fixture()
def app(settings):
    return create_app(settings)


@pytest.fixture()
def client(app):
    # `with` runs the lifespan (creates tables + startup recovery). TestClient executes
    # BackgroundTasks before returning, so tests are deterministic (no sleeping).
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def db(app):
    session = app.state.session_factory()
    yield session
    session.close()


def make_payload(recipients=None, **overrides):
    payload = {
        "event_name": "Python Workshop",
        "organization": "ABC Institute",
        "issue_date": "2026-10-10",
        "recipients": recipients
        if recipients is not None
        else [
            {"name": "Keerthana Bammidi", "email": "keerthana@example.com",
             "certificate_title": "Certificate of Completion"},
            {"name": "Rahul Kumar", "email": "rahul@example.com",
             "certificate_title": "Certificate of Participation"},
        ],
    }
    payload.update(overrides)
    return payload


def recipient(n: int, **overrides):
    r = {"name": f"Person {n}", "email": f"person{n}@example.com",
         "certificate_title": "Certificate of Completion"}
    r.update(overrides)
    return r


@pytest.fixture()
def submit(client):
    """POST a job and return (created_json, final_status_json)."""
    def _submit(payload):
        resp = client.post("/api/certificate-jobs/", json=payload)
        assert resp.status_code == 202, resp.text
        created = resp.json()
        status = client.get(f"/api/certificate-jobs/{created['job_id']}/").json()
        return created, status
    return _submit
