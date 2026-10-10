"""Derived counts, job-status rules and job finalization."""
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models import CertificateRecord, GenerationJob, JobStatus, RecordStatus
from app.models.job import utcnow


def count_by_status(session: Session, job_id: str) -> dict[str, int]:
    """Counts come from the records themselves (single GROUP BY), never from cached
    counters, so they cannot drift out of sync."""
    counts = {s.value: 0 for s in RecordStatus}
    rows = session.execute(
        select(CertificateRecord.status, func.count())
        .where(CertificateRecord.job_id == job_id)
        .group_by(CertificateRecord.status)
    ).all()
    for status, n in rows:
        counts[status] = n
    return counts


def progress_percent(counts: dict[str, int], total: int) -> float:
    if total == 0:
        return 100.0
    done = counts[RecordStatus.SUCCESS.value] + counts[RecordStatus.FAILED.value]
    return round(done / total * 100, 2)


def derive_job_status(counts: dict[str, int], total: int) -> JobStatus:
    """Pure function holding the job-status rules (unit tested)."""
    pending = counts[RecordStatus.PENDING.value]
    processing = counts[RecordStatus.PROCESSING.value]
    success = counts[RecordStatus.SUCCESS.value]

    if pending + processing > 0:
        return JobStatus.QUEUED if pending == total else JobStatus.PROCESSING
    if success == total:
        return JobStatus.COMPLETED
    if success == 0:
        return JobStatus.FAILED
    return JobStatus.COMPLETED_WITH_ERRORS


def finalize_job(session: Session, job_id: str) -> GenerationJob:
    """Compute the final status from the records, stamp completed_at, commit."""
    job = session.get(GenerationJob, job_id)
    counts = count_by_status(session, job_id)
    job.status = derive_job_status(counts, job.total_recipients).value
    job.completed_at = utcnow()
    session.commit()
    return job


def fail_unfinished_records(session: Session, job_id: str, reason: str) -> int:
    """Mark PENDING/PROCESSING records FAILED (crash/abort handling)."""
    result = session.execute(
        update(CertificateRecord)
        .where(
            CertificateRecord.job_id == job_id,
            CertificateRecord.status.in_(
                [RecordStatus.PENDING.value, RecordStatus.PROCESSING.value]
            ),
        )
        .values(
            status=RecordStatus.FAILED.value,
            error_message=reason,
            completed_at=utcnow(),
        )
    )
    session.commit()
    return result.rowcount
