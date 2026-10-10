"""Pydantic request/response shapes.

Policy: the request *envelope* is validated strictly here (-> 422, no job created).
Recipient *content* is validated leniently in services/validation.py so that one bad
recipient is recorded as FAILED instead of rejecting the whole batch.
"""
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.config import MAX_BATCH_SIZE, MAX_EVENT_LEN, MAX_ORG_LEN


def _check_header_text(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("must not be blank")
    if not value.isprintable():
        raise ValueError("must not contain control characters")
    try:
        value.encode("cp1252")  # the PDF font (Helvetica) is WinAnsi/Latin based
    except UnicodeEncodeError:
        raise ValueError("contains characters the certificate font cannot render")
    return value


class RecipientIn(BaseModel):
    """Loose on purpose: content problems become per-recipient failures."""

    model_config = ConfigDict(extra="ignore")

    name: str | None = None
    email: str | None = None
    certificate_title: str | None = None  # None -> default title


class JobCreateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    event_name: str = Field(max_length=MAX_EVENT_LEN)
    organization: str = Field(max_length=MAX_ORG_LEN)
    issue_date: date
    recipients: list[RecipientIn] = Field(min_length=1, max_length=MAX_BATCH_SIZE)

    @field_validator("event_name", "organization")
    @classmethod
    def _clean(cls, v: str) -> str:
        return _check_header_text(v)


class JobCreatedResponse(BaseModel):
    job_id: str
    status: str
    total_recipients: int
    invalid_recipients: int
    status_url: str


class RecipientResult(BaseModel):
    certificate_id: str
    name: str
    email: str
    certificate_title: str
    status: str
    error_message: str | None = None
    download_url: str | None = None  # only set when status == SUCCESS
    completed_at: datetime | None = None


class JobStatusResponse(BaseModel):
    job_id: str
    event_name: str
    organization: str
    issue_date: date
    status: str
    total_recipients: int
    pending: int
    processing: int
    successful: int
    failed: int
    progress_percent: float
    created_at: datetime
    completed_at: datetime | None = None
    recipients: list[RecipientResult]


class JobResultsResponse(BaseModel):
    job_id: str
    status: str
    results: list[RecipientResult]
