"""GenerationJob: one bulk request."""
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.status import JobStatus


def utcnow() -> datetime:
    """Naive UTC timestamp (SQLite does not store time zones)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def new_id() -> str:
    return str(uuid.uuid4())


class GenerationJob(Base):
    __tablename__ = "generation_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    event_name: Mapped[str] = mapped_column(String(150))
    organization: Mapped[str] = mapped_column(String(150))
    issue_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(
        String(30), default=JobStatus.QUEUED.value, index=True
    )
    total_recipients: Mapped[int] = mapped_column(Integer)  # fixed at creation
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # One job -> many certificate records. Deleting a job deletes its records.
    records: Mapped[list["CertificateRecord"]] = relationship(  # noqa: F821
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="CertificateRecord.position",
    )
