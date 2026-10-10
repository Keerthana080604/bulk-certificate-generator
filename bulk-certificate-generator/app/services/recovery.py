"""Startup sweep for jobs interrupted by a restart/crash.

BackgroundTasks work lives in process memory, so a restart silently drops it.
We do NOT resume such jobs. We make the outcome visible: unfinished recipients
are marked FAILED ("interrupted") and the job is finalized.

Assumption: one server process. With several workers this sweep could mark a job
that another worker is still running; a real queue solves that properly.
"""
import logging

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models import GenerationJob
from app.models.status import NON_TERMINAL_JOB_STATUSES
from app.services.status import fail_unfinished_records, finalize_job

logger = logging.getLogger(__name__)

INTERRUPTED_MESSAGE = "Interrupted by server restart before this certificate was generated"


def recover_interrupted_jobs(session_factory: sessionmaker) -> int:
    session = session_factory()
    try:
        job_ids = session.scalars(
            select(GenerationJob.id).where(GenerationJob.status.in_(NON_TERMINAL_JOB_STATUSES))
        ).all()
        for job_id in job_ids:
            n = fail_unfinished_records(session, job_id, INTERRUPTED_MESSAGE)
            finalize_job(session, job_id)
            logger.warning("Recovered interrupted job %s (%d recipients marked FAILED)", job_id, n)
        return len(job_ids)
    finally:
        session.close()
