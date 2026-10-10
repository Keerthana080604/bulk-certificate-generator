"""Background processing, status/progress, failure isolation (tests 5-8, 13)."""
import os

import pytest
from sqlalchemy import select

from app.models import CertificateRecord, GenerationJob, JobStatus
from app.services import pdf as pdf_module
from app.services.status import derive_job_status
from tests.conftest import make_payload, recipient


def test_multiple_recipients_each_get_their_own_pdf(submit, settings, db):
    created, status = submit(make_payload([recipient(i) for i in range(1, 6)]))
    assert status["status"] == "COMPLETED"
    assert (status["successful"], status["failed"], status["pending"], status["processing"]) == (5, 0, 0, 0)
    assert status["progress_percent"] == 100.0
    assert status["completed_at"] is not None

    files = sorted(p.name for p in settings.output_dir.iterdir())
    ids = sorted(r["certificate_id"] for r in status["recipients"])
    assert files == [f"{i}.pdf" for i in ids]  # one file per recipient, nothing else

    for r in status["recipients"]:
        assert r["status"] == "SUCCESS" and r["download_url"]
        data = (settings.output_dir / f"{r['certificate_id']}.pdf").read_bytes()
        assert data.startswith(b"%PDF-")
        assert r["name"].encode() in data  # each PDF carries ITS recipient's name
        assert r["certificate_id"].encode() in data
    records = db.scalars(select(CertificateRecord)).all()
    assert all(rec.pdf_path == f"{rec.id}.pdf" for rec in records)  # filename only


@pytest.fixture()
def fail_on_name(monkeypatch):
    """Make PDF generation fail for one named recipient (after writing partial data)."""
    real = pdf_module.generate_certificate_pdf

    def flaky(path, **kwargs):
        if kwargs["recipient_name"] == "Person 2":
            path.write_bytes(b"%PDF-partial-garbage")  # simulate a half-written file
            raise RuntimeError("disk exploded")
        return real(path, **kwargs)

    monkeypatch.setattr(pdf_module, "generate_certificate_pdf", flaky)


def test_one_failure_does_not_stop_the_batch(fail_on_name, submit, settings, db):
    created, status = submit(make_payload([recipient(i) for i in range(1, 5)]))

    assert status["status"] == "COMPLETED_WITH_ERRORS"
    assert (status["successful"], status["failed"]) == (3, 1)
    assert status["progress_percent"] == 100.0

    by_name = {r["name"]: r for r in status["recipients"]}
    failed = by_name["Person 2"]
    assert failed["status"] == "FAILED"
    assert "disk exploded" in failed["error_message"]
    assert failed["download_url"] is None
    # recipients AFTER the failing one were still processed
    assert by_name["Person 3"]["status"] == "SUCCESS" and by_name["Person 4"]["status"] == "SUCCESS"

    # no partial / temp file left behind, and no file for the failed certificate
    names = os.listdir(settings.output_dir)
    assert not any(n.endswith(".tmp") for n in names)
    assert f"{failed['certificate_id']}.pdf" not in names
    assert len(names) == 3
    rec = db.get(CertificateRecord, failed["certificate_id"])
    assert rec.pdf_path is None and rec.completed_at is not None


def test_all_generations_failing_gives_failed_job(monkeypatch, submit):
    def boom(path, **kwargs):
        raise ValueError("always broken")

    monkeypatch.setattr(pdf_module, "generate_certificate_pdf", boom)
    _, status = submit(make_payload([recipient(1), recipient(2)]))
    assert status["status"] == "FAILED"
    assert (status["successful"], status["failed"]) == (0, 2)


def test_progress_is_visible_while_processing(monkeypatch, client, settings):
    """Observe the job from inside generation: counts must reflect the live state."""
    real = pdf_module.generate_certificate_pdf
    snapshots = []
    state = {"job_id": None}

    def spying(path, **kwargs):
        if state["job_id"]:  # first call happens before we know the id; ignore
            snapshots.append(client.get(f"/api/certificate-jobs/{state['job_id']}/").json())
        return real(path, **kwargs)

    # Learn the job ID from the DB inside the first generation call instead.
    def spying_first(path, **kwargs):
        if state["job_id"] is None:
            session = client.app.state.session_factory()
            state["job_id"] = session.scalars(select(GenerationJob.id)).first()
            session.close()
        return spying(path, **kwargs)

    monkeypatch.setattr(pdf_module, "generate_certificate_pdf", spying_first)
    resp = client.post("/api/certificate-jobs/", json=make_payload([recipient(i) for i in range(1, 4)]))
    assert resp.status_code == 202

    assert len(snapshots) == 3
    for snap in snapshots:
        assert snap["status"] == "PROCESSING"
        assert snap["processing"] == 1  # the recipient currently being generated
        assert snap["pending"] + snap["processing"] + snap["successful"] + snap["failed"] == 3
    assert [s["successful"] for s in snapshots] == [0, 1, 2]
    assert [s["progress_percent"] for s in snapshots] == [0.0, 33.33, 66.67]


@pytest.mark.parametrize(
    "counts,total,expected",
    [
        ({"PENDING": 3, "PROCESSING": 0, "SUCCESS": 0, "FAILED": 0}, 3, JobStatus.QUEUED),
        ({"PENDING": 1, "PROCESSING": 1, "SUCCESS": 1, "FAILED": 0}, 3, JobStatus.PROCESSING),
        ({"PENDING": 0, "PROCESSING": 1, "SUCCESS": 0, "FAILED": 0}, 1, JobStatus.PROCESSING),
        ({"PENDING": 2, "PROCESSING": 0, "SUCCESS": 0, "FAILED": 1}, 3, JobStatus.PROCESSING),
        ({"PENDING": 0, "PROCESSING": 0, "SUCCESS": 3, "FAILED": 0}, 3, JobStatus.COMPLETED),
        ({"PENDING": 0, "PROCESSING": 0, "SUCCESS": 2, "FAILED": 1}, 3, JobStatus.COMPLETED_WITH_ERRORS),
        ({"PENDING": 0, "PROCESSING": 0, "SUCCESS": 0, "FAILED": 3}, 3, JobStatus.FAILED),
    ],
)
def test_job_status_rules(counts, total, expected):
    assert derive_job_status(counts, total) == expected


def test_counts_in_status_response_match_database(fail_on_name, submit, db):
    created, status = submit(make_payload([recipient(i) for i in range(1, 4)]))
    rows = db.scalars(select(CertificateRecord).where(CertificateRecord.job_id == created["job_id"])).all()
    assert status["successful"] == sum(r.status == "SUCCESS" for r in rows)
    assert status["failed"] == sum(r.status == "FAILED" for r in rows)
    assert status["total_recipients"] == len(rows) == 3


def test_job_status_response_shape(submit):
    _, status = submit(make_payload())
    assert set(status) >= {
        "job_id", "status", "total_recipients", "pending", "processing",
        "successful", "failed", "progress_percent", "recipients",
    }
    assert [r["name"] for r in status["recipients"]] == ["Keerthana Bammidi", "Rahul Kumar"]  # request order


def test_unknown_job_returns_404(client):
    assert client.get("/api/certificate-jobs/does-not-exist/").status_code == 404
    assert client.get("/api/certificate-jobs/does-not-exist/certificates/").status_code == 404
