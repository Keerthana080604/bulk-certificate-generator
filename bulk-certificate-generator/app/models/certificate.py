"""CertificateRecord: one recipient inside a job (also the public certificate ID)."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.job import GenerationJob, new_id, utcnow
from app.models.status import RecordStatus


class CertificateRecord(Base):
    __tablename__ = "certificate_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("generation_jobs.id"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)  # order in the original request
    recipient_name: Mapped[str] = mapped_column(String(100))
    recipient_email: Mapped[str] = mapped_column(String(254))
    certificate_title: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(
        String(20), default=RecordStatus.PENDING.value, index=True
    )
    pdf_path: Mapped[str | None] = mapped_column(String(255), nullable=True)  # filename only
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    job: Mapped[GenerationJob] = relationship(back_populates="records")
