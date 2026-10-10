"""Creating jobs and rejecting malformed requests (tests 1, 3, 14)."""
import pytest
from sqlalchemy import select

from app.core.config import MAX_BATCH_SIZE
from app.models import CertificateRecord, GenerationJob
from tests.conftest import make_payload, recipient


def test_create_job_returns_202_and_persists_everything(client, db):
    resp = client.post("/api/certificate-jobs/", json=make_payload())
    assert resp.status_code == 202
    body = resp.json()
    assert body["total_recipients"] == 2
    assert body["invalid_recipients"] == 0
    assert body["status"] in {"QUEUED", "PROCESSING", "COMPLETED"}
    assert body["status_url"].endswith(f"/api/certificate-jobs/{body['job_id']}/")

    job = db.get(GenerationJob, body["job_id"])
    assert job.event_name == "Python Workshop"
    assert job.organization == "ABC Institute"
    assert job.total_recipients == 2
    records = db.scalars(select(CertificateRecord).where(CertificateRecord.job_id == job.id)).all()
    assert len(records) == 2
    assert len({r.id for r in records}) == 2  # unique certificate IDs


def test_job_ids_are_unique(client):
    ids = {client.post("/api/certificate-jobs/", json=make_payload()).json()["job_id"] for _ in range(3)}
    assert len(ids) == 3


@pytest.mark.parametrize(
    "mutation",
    [
        {"event_name": None},                      # missing (removed below)
        {"organization": None},
        {"issue_date": None},
        {"recipients": None},
        {"event_name": "   "},                     # blank
        {"event_name": "x" * 151},                 # too long
        {"organization": "y" * 151},
        {"issue_date": "2026-13-45"},              # invalid date
        {"issue_date": "not-a-date"},
        {"recipients": "not-a-list"},
        {"recipients": [{"name": 123, "email": "a@b.co"}]},  # wrong type
        {"event_name": "Workshop \u0c24\u0c46\u0c32\u0c41\u0c17\u0c41"},  # glyphs the font can't draw
    ],
)
def test_malformed_requests_are_rejected_without_creating_a_job(client, db, mutation):
    payload = make_payload()
    for key, value in mutation.items():
        if value is None:
            payload.pop(key)
        else:
            payload[key] = value
    resp = client.post("/api/certificate-jobs/", json=payload)
    assert resp.status_code == 422
    assert db.scalars(select(GenerationJob)).all() == []  # nothing stored


def test_non_json_body_is_rejected(client):
    resp = client.post("/api/certificate-jobs/", content="hello", headers={"content-type": "application/json"})
    assert resp.status_code == 422


def test_empty_recipient_list_is_rejected(client, db):
    resp = client.post("/api/certificate-jobs/", json=make_payload(recipients=[]))
    assert resp.status_code == 422
    assert db.scalars(select(GenerationJob)).all() == []


def test_batch_size_limit(client, db):
    too_many = [recipient(i) for i in range(MAX_BATCH_SIZE + 1)]
    assert client.post("/api/certificate-jobs/", json=make_payload(too_many)).status_code == 422
    assert db.scalars(select(GenerationJob)).all() == []


def test_batch_exactly_at_limit_is_accepted(client, submit):
    batch = [recipient(i) for i in range(MAX_BATCH_SIZE)]
    created, status = submit(make_payload(batch))
    assert created["total_recipients"] == MAX_BATCH_SIZE
    assert status["status"] == "COMPLETED"
    assert status["successful"] == MAX_BATCH_SIZE
