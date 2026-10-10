"""Recipient-level validation: bad recipients fail individually (test 2)."""
import pytest

from app.schemas.jobs import RecipientIn
from app.services.validation import validate_recipients
from tests.conftest import make_payload, recipient


def validate_one(**fields):
    base = {"name": "Asha", "email": "asha@example.com", "certificate_title": "Certificate of Completion"}
    base.update(fields)
    return validate_recipients([RecipientIn(**base)])[0]


@pytest.mark.parametrize("email", ["asha@example.com", "a.b+tag@sub.example.co.in", "A@B.COM"])
def test_valid_emails(email):
    assert validate_one(email=email).error is None


@pytest.mark.parametrize("email", ["", "   ", "plain", "a@b", "a@@b.com", "a b@c.com", "@x.com", "a@.com", "a@b..com"])
def test_invalid_emails(email):
    assert validate_one(email=email).error is not None


@pytest.mark.parametrize("name", ["", "   ", None])
def test_blank_or_missing_name(name):
    assert "name is required" in validate_one(name=name).error


def test_too_long_fields():
    assert "name exceeds" in validate_one(name="n" * 101).error
    assert "certificate_title exceeds" in validate_one(certificate_title="t" * 101).error
    assert "email exceeds" in validate_one(email="e" * 250 + "@x.com").error


def test_control_characters_and_unrenderable_glyphs_rejected():
    assert validate_one(name="Line\nBreak").error
    assert "cannot render" in validate_one(name="\u0c15\u0c3f\u0c30\u0c23\u0c4d").error
    assert validate_one(name="Jos\u00e9 M\u00fcller").error is None  # Latin accents are fine


def test_missing_title_gets_default_but_blank_title_is_an_error():
    ok = validate_recipients([RecipientIn(name="A", email="a@x.com")])[0]
    assert ok.error is None and ok.title == "Certificate of Completion"
    assert validate_one(certificate_title="   ").error


def test_stored_values_are_clipped_for_invalid_records():
    v = validate_one(name="n" * 5000)
    assert len(v.name) == 100 and v.error


def test_duplicate_policy_same_email_and_title_case_insensitive():
    recs = [
        RecipientIn(name="A", email="A@x.com", certificate_title="Cert"),
        RecipientIn(name="A again", email="a@X.com", certificate_title="cert"),  # duplicate
        RecipientIn(name="A", email="a@x.com", certificate_title="Other"),       # different title: allowed
    ]
    out = validate_recipients(recs)
    assert [r.error is None for r in out] == [True, False, True]
    assert "duplicate" in out[1].error


def test_invalid_first_occurrence_does_not_block_later_valid_duplicate():
    recs = [
        RecipientIn(name="", email="a@x.com", certificate_title="Cert"),   # invalid (no name)
        RecipientIn(name="A", email="a@x.com", certificate_title="Cert"),  # valid, not a duplicate
    ]
    out = validate_recipients(recs)
    assert out[0].error and out[1].error is None


def test_invalid_recipients_become_failed_records_and_rest_succeed(submit):
    payload = make_payload([
        recipient(1),
        recipient(2, email="nope"),
        recipient(3, name=""),
        recipient(4),
    ])
    created, status = submit(payload)
    assert created["invalid_recipients"] == 2
    assert status["status"] == "COMPLETED_WITH_ERRORS"
    assert (status["successful"], status["failed"], status["pending"]) == (2, 2, 0)
    by_name = {r["name"]: r for r in status["recipients"]}
    assert by_name["Person 2"]["status"] == "FAILED"
    assert "email" in by_name["Person 2"]["error_message"]
    assert by_name["Person 2"]["download_url"] is None
    assert by_name["Person 1"]["status"] == "SUCCESS"


def test_all_recipients_invalid_job_is_failed_and_complete(submit):
    created, status = submit(make_payload([recipient(1, email="bad"), recipient(2, name="")]))
    assert created["status"] == "FAILED"
    assert status["status"] == "FAILED"
    assert status["failed"] == 2 and status["successful"] == 0
    assert status["progress_percent"] == 100.0
    assert status["completed_at"] is not None
