from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    document_version_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "document_versions.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    job_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="parse",
        server_default="parse",
    )

    stage: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="queued",
        server_default="queued",
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="pending",
        server_default="pending",
        index=True,
    )

    input_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )

    idempotency_key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
    )

    parser_config_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    document_version = relationship(
        "DocumentVersion",
        back_populates="ingestion_jobs",
    )
