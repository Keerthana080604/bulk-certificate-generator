"""Listing and downloading certificates (tests 9, 11, 12)."""
import os

from app.models import CertificateRecord
from tests.conftest import make_payload, recipient
from app.services import pdf as pdf_module


def test_list_results_for_job(submit, client):
    created, _ = submit(make_payload([recipient(1), recipient(2, email="bad")]))
    resp = client.get(f"/api/certificate-jobs/{created['job_id']}/certificates/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "COMPLETED_WITH_ERRORS"
    ok, bad = body["results"]
    assert ok["status"] == "SUCCESS" and ok["certificate_id"] and ok["download_url"]
    assert bad["status"] == "FAILED" and bad["download_url"] is None and bad["error_message"]


def test_download_returns_the_pdf(submit, client, settings):
    _, status = submit(make_payload())
    rec = status["recipients"][0]
    resp = client.get(f"/api/certificates/{rec['certificate_id']}/download/")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert "attachment" in resp.headers["content-disposition"]
    assert "certificate_Keerthana_Bammidi.pdf" in resp.headers["content-disposition"]
    assert resp.content == (settings.output_dir / f"{rec['certificate_id']}.pdf").read_bytes()
    assert resp.content.startswith(b"%PDF-") and b"Keerthana Bammidi" in resp.content


def test_download_url_from_status_response_works(submit, client):
    _, status = submit(make_payload())
    assert client.get(status["recipients"][1]["download_url"]).status_code == 200


def test_unknown_certificate_id_returns_404(client):
    assert client.get("/api/certificates/nope/download/").status_code == 404
    assert client.get("/api/certificates/00000000-0000-0000-0000-000000000000/download/").status_code == 404


def test_failed_certificates_cannot_be_downloaded(monkeypatch, submit, client):
    def boom(path, **kwargs):
        raise RuntimeError("x")

    monkeypatch.setattr(pdf_module, "generate_certificate_pdf", boom)
    _, status = submit(make_payload([recipient(1), recipient(2, email="bad")]))
    for r in status["recipients"]:
        assert r["status"] == "FAILED"
        assert client.get(f"/api/certificates/{r['certificate_id']}/download/").status_code == 404


def test_pending_certificate_cannot_be_downloaded(client, db, submit, settings):
    _, status = submit(make_payload([recipient(1)]))
    cid = status["recipients"][0]["certificate_id"]
    rec = db.get(CertificateRecord, cid)
    rec.status = "PENDING"  # pretend it never finished; the file still exists on disk
    db.commit()
    assert (settings.output_dir / f"{cid}.pdf").exists()
    assert client.get(f"/api/certificates/{cid}/download/").status_code == 404


def test_missing_file_on_disk_returns_404(submit, client, settings):
    _, status = submit(make_payload([recipient(1)]))
    cid = status["recipients"][0]["certificate_id"]
    os.remove(settings.output_dir / f"{cid}.pdf")
    assert client.get(f"/api/certificates/{cid}/download/").status_code == 404


def test_path_traversal_in_stored_path_cannot_escape_output_dir(submit, client, db, tmp_path):
    _, status = submit(make_payload([recipient(1)]))
    cid = status["recipients"][0]["certificate_id"]
    secret = tmp_path / "secret.txt"
    secret.write_text("top secret")
    rec = db.get(CertificateRecord, cid)
    rec.pdf_path = "../secret.txt"  # even a corrupted DB value must not leak files
    db.commit()
    resp = client.get(f"/api/certificates/{cid}/download/")
    assert resp.status_code == 404
    assert b"top secret" not in resp.content
