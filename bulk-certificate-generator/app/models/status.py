"""Status enums. They subclass str so they store/serialize as plain strings."""
from enum import Enum


class RecordStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_ERRORS = "COMPLETED_WITH_ERRORS"
    FAILED = "FAILED"


NON_TERMINAL_JOB_STATUSES = (JobStatus.QUEUED.value, JobStatus.PROCESSING.value)
