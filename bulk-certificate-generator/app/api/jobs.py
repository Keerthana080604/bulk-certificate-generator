"""Job endpoints: HTTP concerns only; logic lives in app/services."""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_output_dir
from app.models import CertificateRecord, GenerationJob, RecordStatus
from app.schemas.jobs import (
    JobCreatedResponse,
    JobCreateRequest,
    JobResultsResponse,
    JobStatusResponse,
    RecipientResult,
)
from app.services.jobs import create_job
from app.services.processor import process_job
from app.services.status import count_by_status, progress_percent

router = APIRouter(prefix="/api/certificate-jobs", tags=["certificate jobs"])


def _result(request: Request, rec: CertificateRecord) -> RecipientResult:
    ok = rec.status == RecordStatus.SUCCESS.value
    return RecipientResult(
        certificate_id=rec.id,
        name=rec.recipient_name,
        email=rec.recipient_email,
        certificate_title=rec.certificate_title,
        status=rec.status,
        error_message=rec.error_message,
        download_url=str(request.url_for("download_certificate", certificate_id=rec.id)) if ok else None,
        completed_at=rec.completed_at,
    )


def _get_job_or_404(db: Session, job_id: str) -> GenerationJob:
    job = db.get(GenerationJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/", status_code=status.HTTP_202_ACCEPTED, response_model=JobCreatedResponse)
def create_certificate_job(
    payload: JobCreateRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    output_dir=Depends(get_output_dir),
):
    job, invalid = create_job(db, payload)
    if invalid < job.total_recipients:  # at least one valid recipient to process
        background_tasks.add_task(
            process_job, job.id, request.app.state.session_factory, output_dir
        )
    return JobCreatedResponse(
        job_id=job.id,
        status=job.status,
        total_recipients=job.total_recipients,
        invalid_recipients=invalid,
        status_url=str(request.url_for("get_job_status", job_id=job.id)),
    )


@router.get("/{job_id}/", response_model=JobStatusResponse)
def get_job_status(job_id: str, request: Request, db: Session = Depends(get_db)):
    job = _get_job_or_404(db, job_id)
    counts = count_by_status(db, job.id)
    return JobStatusResponse(
        job_id=job.id,
        event_name=job.event_name,
        organization=job.organization,
        issue_date=job.issue_date,
        status=job.status,
        total_recipients=job.total_recipients,
        pending=counts["PENDING"],
        processing=counts["PROCESSING"],
        successful=counts["SUCCESS"],
        failed=counts["FAILED"],
        progress_percent=progress_percent(counts, job.total_recipients),
        created_at=job.created_at,
        completed_at=job.completed_at,
        recipients=[_result(request, r) for r in job.records],
    )


@router.get("/{job_id}/certificates/", response_model=JobResultsResponse)
def list_job_certificates(job_id: str, request: Request, db: Session = Depends(get_db)):
    job = _get_job_or_404(db, job_id)
    return JobResultsResponse(
        job_id=job.id,
        status=job.status,
        results=[_result(request, r) for r in job.records],
    )
