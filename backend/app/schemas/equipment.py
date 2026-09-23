from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _clean_required(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("must not be empty")
    return cleaned


def _clean_aliases(values: list[str] | None) -> list[str] | None:
    if values is None:
        return None

    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        alias = value.strip()
        if alias and alias not in seen:
            cleaned.append(alias)
            seen.add(alias)
    return cleaned or None


class EquipmentModelCreate(BaseModel):
    manufacturer: str = Field(max_length=100)
    model_code: str = Field(max_length=100)
    category: str | None = Field(default=None, max_length=100)
    aliases: list[str] | None = None

    @field_validator("manufacturer", "model_code")
    @classmethod
    def validate_required(cls, value: str) -> str:
        return _clean_required(value)

    @field_validator("category")
    @classmethod
    def validate_category(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @field_validator("aliases")
    @classmethod
    def validate_aliases(cls, value: list[str] | None) -> list[str] | None:
        return _clean_aliases(value)


class EquipmentModelUpdate(BaseModel):
    manufacturer: str | None = Field(default=None, max_length=100)
    model_code: str | None = Field(default=None, max_length=100)
    category: str | None = Field(default=None, max_length=100)
    aliases: list[str] | None = None

    @field_validator("manufacturer", "model_code")
    @classmethod
    def validate_required_if_present(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _clean_required(value)

    @field_validator("category")
    @classmethod
    def validate_category(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @field_validator("aliases")
    @classmethod
    def validate_aliases(cls, value: list[str] | None) -> list[str] | None:
        return _clean_aliases(value)


class EquipmentModelResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    manufacturer: str
    model_code: str
    category: str | None
    aliases: list[str] | None
    created_at: datetime
