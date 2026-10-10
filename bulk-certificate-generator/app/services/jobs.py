"""Job creation: validate recipients and persist job + records in ONE transaction."""
from sqlalchemy.orm import Session

from app.models import CertificateRecord, GenerationJob, JobStatus, RecordStatus
from app.models.job import utcnow
from app.schemas.jobs import JobCreateRequest
from app.services.validation import validate_recipients


def create_job(session: Session, payload: JobCreateRequest) -> tuple[GenerationJob, int]:
    """Returns (job, invalid_count). Nothing is stored unless everything is stored."""
    validated = validate_recipients(payload.recipients)
    invalid = sum(1 for v in validated if v.error)

    job = GenerationJob(
        event_name=payload.event_name,
        organization=payload.organization,
        issue_date=payload.issue_date,
        total_recipients=len(validated),
        status=JobStatus.QUEUED.value,
    )
    for v in validated:
        record = CertificateRecord(
            position=v.position,
            recipient_name=v.name,
            recipient_email=v.email,
            certificate_title=v.title,
            status=RecordStatus.FAILED.value if v.error else RecordStatus.PENDING.value,
            error_message=v.error,
            completed_at=utcnow() if v.error else None,
        )
        job.records.append(record)  # sets job_id when the job is flushed

    # Every recipient invalid -> nothing to process; the job is born FAILED.
    if invalid == len(validated):
        job.status = JobStatus.FAILED.value
        job.completed_at = utcnow()

    session.add(job)
    try:
        session.commit()  # job + all records succeed or fail together
    except Exception:
        session.rollback()
        raise
    return job, invalid
