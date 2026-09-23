from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class DocumentAsset(Base):
    __tablename__ = "document_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    document_version_id: Mapped[int] = mapped_column(
        ForeignKey(
            "document_versions.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    asset_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
    )

    page_number: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    storage_path: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    mime_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    sha256: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )

    bbox: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    caption: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    document_version = relationship(
        "DocumentVersion",
        back_populates="assets",
    )

    blocks = relationship(
        "DocumentBlock",
        back_populates="asset",
    )


class DocumentBlock(Base):
    __tablename__ = "document_blocks"

    __table_args__ = (
        Index(
            "ix_document_blocks_document_page",
            "document_version_id",
            "page_start",
        ),
        Index(
            "ix_document_blocks_document_type",
            "document_version_id",
            "block_type",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    evidence_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
    )

    document_version_id: Mapped[int] = mapped_column(
        ForeignKey(
            "document_versions.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    block_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    section_path: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    page_start: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    page_end: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    bbox: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    asset_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "document_assets.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    ordinal: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    extra_metadata: Mapped[dict | None] = mapped_column(
        "metadata",
        JSON,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    document_version = relationship(
        "DocumentVersion",
        back_populates="blocks",
    )

    asset = relationship(
        "DocumentAsset",
        back_populates="blocks",
    )
