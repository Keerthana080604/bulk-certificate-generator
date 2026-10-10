"""Certificate PDF rendering with ReportLab (the single predefined template).

The template is *code*: coordinates and fonts below. Dynamic values are drawn with
canvas.drawCentredString, which treats text literally (no markup parsing).
"""
from datetime import date
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

PAGE_W, PAGE_H = landscape(A4)  # 841.9 x 595.3 points
NAVY = HexColor("#1F3A5F")
GOLD = HexColor("#B8860B")
GREY = HexColor("#555555")
TEXT_MAX_WIDTH = PAGE_W - 2 * 90  # keep text inside the margins


def _fit_font_size(text: str, font: str, start: float, max_width: float, minimum: float = 8) -> float:
    """Shrink the font until the text fits the available width."""
    size = start
    while size > minimum and stringWidth(text, font, size) > max_width:
        size -= 1
    return size


def _centered(c: canvas.Canvas, y: float, text: str, font: str, size: float, color) -> None:
    size = _fit_font_size(text, font, size, TEXT_MAX_WIDTH)
    c.setFont(font, size)
    c.setFillColor(color)
    c.drawCentredString(PAGE_W / 2, y, text)


def _format_date(d: date) -> str:
    return f"{d.day} {d:%B %Y}"  # locale independent


def generate_certificate_pdf(
    output_path: Path,
    *,
    certificate_id: str,
    recipient_name: str,
    certificate_title: str,
    event_name: str,
    organization: str,
    issue_date: date,
) -> None:
    """Render one certificate to output_path. Raises on any problem."""
    # pageCompression=0 keeps the (tiny) content stream readable so tests can
    # assert that the recipient's name really is in the file.
    c = canvas.Canvas(str(output_path), pagesize=(PAGE_W, PAGE_H), pageCompression=0)
    c.setTitle(f"{certificate_title} - {recipient_name}")
    c.setAuthor(organization)

    # Double border
    c.setStrokeColor(NAVY)
    c.setLineWidth(4)
    c.rect(30, 30, PAGE_W - 60, PAGE_H - 60)
    c.setStrokeColor(GOLD)
    c.setLineWidth(1.5)
    c.rect(42, 42, PAGE_W - 84, PAGE_H - 84)

    # Text blocks, top to bottom
    _centered(c, 465, organization.upper(), "Helvetica-Bold", 16, GREY)
    _centered(c, 405, certificate_title, "Times-Bold", 38, NAVY)
    _centered(c, 365, "This certificate is proudly presented to", "Helvetica", 14, GREY)
    _centered(c, 305, recipient_name, "Times-BoldItalic", 36, GOLD)

    name_w = min(stringWidth(recipient_name, "Times-BoldItalic",
                             _fit_font_size(recipient_name, "Times-BoldItalic", 36, TEXT_MAX_WIDTH)),
                 TEXT_MAX_WIDTH)
    c.setStrokeColor(GOLD)
    c.setLineWidth(1)
    c.line(PAGE_W / 2 - name_w / 2 - 20, 292, PAGE_W / 2 + name_w / 2 + 20, 292)

    _centered(c, 258, "in recognition of their participation in", "Helvetica", 14, GREY)
    _centered(c, 225, event_name, "Helvetica-Bold", 22, NAVY)

    # Footer: date (left), signature placeholder (right), certificate ID (centre)
    c.setFillColor(NAVY)
    c.setFont("Helvetica", 12)
    c.drawString(90, 120, f"Date of Issue: {_format_date(issue_date)}")

    c.setStrokeColor(NAVY)
    c.setLineWidth(1)
    c.line(PAGE_W - 270, 120, PAGE_W - 90, 120)
    c.setFont("Helvetica", 11)
    c.drawCentredString(PAGE_W - 180, 104, "Authorized Signatory")

    c.setFillColor(GREY)
    c.setFont("Helvetica", 9)
    c.drawCentredString(PAGE_W / 2, 62, f"Certificate ID: {certificate_id}")

    c.showPage()
    c.save()
