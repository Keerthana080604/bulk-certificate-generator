"""Certificate download endpoint."""
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_output_dir
from app.models import CertificateRecord, RecordStatus

router = APIRouter(prefix="/api/certificates", tags=["certificates"])


def _safe_filename(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")
    return f"certificate_{slug or 'recipient'}.pdf"


@router.get("/{certificate_id}/download/", name="download_certificate")
def download_certificate(
    certificate_id: str,
    db: Session = Depends(get_db),
    output_dir: Path = Depends(get_output_dir),
):
    record = db.get(CertificateRecord, certificate_id)
    # Same 404 for "unknown", "not successful" and "file missing": nothing leaks
    # about which IDs exist.
    not_found = HTTPException(status_code=404, detail="Certificate not found")
    if record is None or record.status != RecordStatus.SUCCESS.value or not record.pdf_path:
        raise not_found

    base = output_dir.resolve()
    path = (base / Path(record.pdf_path).name).resolve()  # .name drops any directories
    if path.parent != base or not path.is_file():
        raise not_found

    return FileResponse(
        path,
        media_type="application/pdf",
        filename=_safe_filename(record.recipient_name),
    )
