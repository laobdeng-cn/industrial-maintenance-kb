from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.deps import get_db
from app.models.equipment import EquipmentModel
from app.schemas.equipment import (
    EquipmentModelCreate,
    EquipmentModelResponse,
    EquipmentModelUpdate,
)


router = APIRouter(
    prefix="/api/equipment-models",
    tags=["equipment-models"],
)


def _get_equipment_or_404(
    db: Session,
    equipment_id: int,
) -> EquipmentModel:
    model = db.get(EquipmentModel, equipment_id)
    if model is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="equipment model not found",
        )
    return model


def _commit_or_conflict(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="manufacturer and model_code must be unique",
        ) from exc


@router.get(
    "",
    response_model=list[EquipmentModelResponse],
)
def list_equipment_models(
    db: Session = Depends(get_db),
) -> list[EquipmentModelResponse]:
    models = db.scalars(
        select(EquipmentModel).order_by(
            EquipmentModel.manufacturer.asc(),
            EquipmentModel.model_code.asc(),
            EquipmentModel.id.asc(),
        )
    ).all()
    return [
        EquipmentModelResponse.model_validate(model)
        for model in models
    ]


@router.post(
    "",
    response_model=EquipmentModelResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_equipment_model(
    payload: EquipmentModelCreate,
    db: Session = Depends(get_db),
) -> EquipmentModelResponse:
    model = EquipmentModel(**payload.model_dump())
    db.add(model)
    _commit_or_conflict(db)
    db.refresh(model)
    return EquipmentModelResponse.model_validate(model)


@router.get(
    "/{equipment_id}",
    response_model=EquipmentModelResponse,
)
def get_equipment_model(
    equipment_id: int,
    db: Session = Depends(get_db),
) -> EquipmentModelResponse:
    return EquipmentModelResponse.model_validate(
        _get_equipment_or_404(db, equipment_id)
    )


@router.patch(
    "/{equipment_id}",
    response_model=EquipmentModelResponse,
)
def update_equipment_model(
    equipment_id: int,
    payload: EquipmentModelUpdate,
    db: Session = Depends(get_db),
) -> EquipmentModelResponse:
    model = _get_equipment_or_404(db, equipment_id)
    changes = payload.model_dump(
        exclude_unset=True,
    )

    for field, value in changes.items():
        setattr(model, field, value)

    _commit_or_conflict(db)
    db.refresh(model)
    return EquipmentModelResponse.model_validate(model)


@router.delete(
    "/{equipment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_equipment_model(
    equipment_id: int,
    db: Session = Depends(get_db),
) -> Response:
    model = _get_equipment_or_404(db, equipment_id)
    db.delete(model)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
