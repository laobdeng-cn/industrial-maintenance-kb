from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


document_version_models = Table(
    "document_version_models",
    Base.metadata,
    Column(
        "document_version_id",
        ForeignKey(
            "document_versions.id",
            ondelete="CASCADE",
        ),
        primary_key=True,
    ),
    Column(
        "equipment_model_id",
        ForeignKey(
            "equipment_models.id",
            ondelete="CASCADE",
        ),
        primary_key=True,
    ),
)


class DocumentVersion(Base):
    __tablename__ = "document_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    version: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    language: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    source_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    original_filename: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    storage_path: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    file_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="draft",
        server_default="draft",
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    equipment_models = relationship(
        "EquipmentModel",
        secondary=document_version_models,
        back_populates="document_versions",
    )

    blocks = relationship(
        "DocumentBlock",
        back_populates="document_version",
        cascade="all, delete-orphan",
    )

    assets = relationship(
        "DocumentAsset",
        back_populates="document_version",
        cascade="all, delete-orphan",
    )

    ingestion_jobs = relationship(
        "IngestionJob",
        back_populates="document_version",
    )
