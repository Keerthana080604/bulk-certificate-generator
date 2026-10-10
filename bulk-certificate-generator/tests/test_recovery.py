"""Startup recovery of interrupted jobs."""
from datetime import date

from fastapi.testclient import TestClient

from app.main import create_app
from app.models import CertificateRecord, GenerationJob
from app.services.recovery import INTERRUPTED_MESSAGE


def test_interrupted_job_is_marked_failed_on_startup(settings):
    # Simulate a crash: a job left PROCESSING with 1 SUCCESS, 1 PROCESSING, 1 PENDING.
    app1 = create_app(settings)
    with TestClient(app1):
        s = app1.state.session_factory()
        job = GenerationJob(event_name="E", organization="O", issue_date=date(2026, 1, 1),
                            total_recipients=3, status="PROCESSING")
        for i, st in enumerate(["SUCCESS", "PROCESSING", "PENDING"]):
            job.records.append(CertificateRecord(position=i, recipient_name=f"P{i}",
                                                 recipient_email=f"p{i}@x.com",
                                                 certificate_title="T", status=st))
        s.add(job)
        s.commit()
        job_id = job.id
        s.close()

    # "Restart" the server against the same database.
    app2 = create_app(settings)
    with TestClient(app2) as client:
        body = client.get(f"/api/certificate-jobs/{job_id}/").json()
    assert body["status"] == "COMPLETED_WITH_ERRORS"
    assert (body["successful"], body["failed"], body["pending"], body["processing"]) == (1, 2, 0, 0)
    assert body["completed_at"] is not None
    errors = [r["error_message"] for r in body["recipients"] if r["status"] == "FAILED"]
    assert errors == [INTERRUPTED_MESSAGE] * 2


def test_completed_jobs_are_left_alone_on_startup(settings):
    app1 = create_app(settings)
    with TestClient(app1) as c:
        from tests.conftest import make_payload
        job_id = c.post("/api/certificate-jobs/", json=make_payload()).json()["job_id"]
        before = c.get(f"/api/certificate-jobs/{job_id}/").json()
    with TestClient(create_app(settings)) as c:
        after = c.get(f"/api/certificate-jobs/{job_id}/").json()
    assert before == after and after["status"] == "COMPLETED"
