"""Background processing: generate PDFs one recipient at a time.

Runs inside the web-server process via FastAPI BackgroundTasks. It uses its OWN
database session (the request session is closed once the response is sent) and
commits after every recipient so that:
  * a failure affects only that recipient,
  * progress is visible to the client while the job runs,
  * a crash loses at most the recipient currently being processed.
"""
import logging
import os
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import CertificateRecord, GenerationJob, JobStatus, RecordStatus
from app.models.job import utcnow
from app.services import pdf  # module reference so tests can monkeypatch it
from app.services.status import fail_unfinished_records, finalize_job

logger = logging.getLogger(__name__)

MAX_ERROR_LEN = 500


def _remove_quietly(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.warning("Could not remove file %s", path)


def _process_record(session: Session, job: GenerationJob, record_id: str, output_dir: Path) -> None:
    record = session.get(CertificateRecord, record_id)
    record.status = RecordStatus.PROCESSING.value
    session.commit()

    # File names are built from our own UUID only: clients never influence paths.
    final_path = output_dir / f"{record.id}.pdf"
    tmp_path = output_dir / f"{record.id}.pdf.tmp"
    try:
        pdf.generate_certificate_pdf(
            tmp_path,
            certificate_id=record.id,
            recipient_name=record.recipient_name,
            certificate_title=record.certificate_title,
            event_name=job.event_name,
            organization=job.organization,
            issue_date=job.issue_date,
        )
        os.replace(tmp_path, final_path)  # atomic: no half-written "final" file
        record.status = RecordStatus.SUCCESS.value
        record.pdf_path = final_path.name  # filename only, never a client path
        record.completed_at = utcnow()
        session.commit()
    except Exception as exc:
        session.rollback()
        logger.exception("Certificate %s (job %s) failed", record_id, job.id)
        _remove_quietly(tmp_path)
        _remove_quietly(final_path)  # covers "file written but DB commit failed"
        record = session.get(CertificateRecord, record_id)
        record.status = RecordStatus.FAILED.value
        record.pdf_path = None
        record.error_message = f"Certificate generation failed: {type(exc).__name__}: {exc}"[:MAX_ERROR_LEN]
        record.completed_at = utcnow()
        session.commit()


def process_job(job_id: str, session_factory: sessionmaker, output_dir: Path) -> None:
    """Entry point scheduled with BackgroundTasks."""
    session = session_factory()
    try:
        job = session.get(GenerationJob, job_id)
        if job is None:
            logger.error("process_job: job %s not found", job_id)
            return
        output_dir.mkdir(parents=True, exist_ok=True)

        job.status = JobStatus.PROCESSING.value
        session.commit()
        logger.info("Job %s started (%d recipients)", job_id, job.total_recipients)

        pending_ids = session.scalars(
            select(CertificateRecord.id)
            .where(
                CertificateRecord.job_id == job_id,
                CertificateRecord.status == RecordStatus.PENDING.value,
            )
            .order_by(CertificateRecord.position)
        ).all()

        try:
            for record_id in pending_ids:
                _process_record(session, job, record_id, output_dir)
        except Exception:
            # Something outside a single recipient broke (e.g. the DB itself).
            session.rollback()
            logger.exception("Job %s aborted unexpectedly", job_id)
            fail_unfinished_records(session, job_id, "Job aborted due to an internal error")

        finalized = finalize_job(session, job_id)
        logger.info("Job %s finished with status %s", job_id, finalized.status)
    except Exception:
        logger.exception("Job %s could not be finalized", job_id)
        session.rollback()
    finally:
        session.close()
