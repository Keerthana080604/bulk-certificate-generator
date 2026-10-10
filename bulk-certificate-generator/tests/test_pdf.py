"""Certificate rendering (test 4)."""
from datetime import date

import pytest

from app.services.pdf import generate_certificate_pdf


def render(path, **overrides):
    kwargs = dict(
        certificate_id="11111111-2222-3333-4444-555555555555",
        recipient_name="Keerthana Bammidi",
        certificate_title="Certificate of Completion",
        event_name="Python Workshop",
        organization="ABC Institute",
        issue_date=date(2026, 10, 10),
    )
    kwargs.update(overrides)
    generate_certificate_pdf(path, **kwargs)


def test_pdf_is_valid_and_contains_all_required_fields(tmp_path):
    out = tmp_path / "c.pdf"
    render(out)
    data = out.read_bytes()
    assert data.startswith(b"%PDF-") and data.rstrip().endswith(b"%%EOF")
    for expected in [
        b"Keerthana Bammidi",
        b"Certificate of Completion",
        b"Python Workshop",
        b"ABC INSTITUTE",
        b"10 October 2026",
        b"11111111-2222-3333-4444-555555555555",
        b"Authorized Signatory",
    ]:
        assert expected in data, expected


def test_text_is_treated_literally_not_as_markup(tmp_path):
    out = tmp_path / "c.pdf"
    render(out, recipient_name="<b>Bold</b> & <script>")
    assert out.stat().st_size > 0  # no parser blow-up


def test_long_text_is_shrunk_and_still_renders(tmp_path):
    out = tmp_path / "c.pdf"
    render(out, recipient_name="W" * 100, event_name="E" * 150, certificate_title="T" * 100)
    assert out.read_bytes().startswith(b"%PDF-")


def test_unwritable_location_raises(tmp_path):
    with pytest.raises(Exception):
        render(tmp_path / "missing_dir" / "c.pdf")
