from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class EquipmentModel(Base):
    __tablename__ = "equipment_models"

    __table_args__ = (
        UniqueConstraint(
            "manufacturer",
            "model_code",
            name="uq_equipment_manufacturer_model",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    manufacturer: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    model_code: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    category: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    aliases: Mapped[list[str] | None] = mapped_column(
        JSON,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    document_versions = relationship(
        "DocumentVersion",
        secondary="document_version_models",
        back_populates="equipment_models",
    )
