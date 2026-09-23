from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.deps import get_db
from app.models.equipment import EquipmentModel
from app.models.evaluation import EvaluationCase, EvaluationRun
from app.schemas.evaluation import (
    EvaluationCaseCreate,
    EvaluationCaseResponse,
    EvaluationCaseUpdate,
    EvaluationRunCreate,
    EvaluationRunResponse,
    EvaluationRunSummaryResponse,
)
from app.services.evaluation import execute_evaluation_run


router = APIRouter(
    prefix="/api/evaluation",
    tags=["evaluation"],
)


def _get_case_or_404(db: Session, case_id: int) -> EvaluationCase:
    case = db.get(EvaluationCase, case_id)
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="evaluation case not found",
        )
    return case


def _ensure_equipment(db: Session, equipment_model_id: int) -> None:
    if db.get(EquipmentModel, equipment_model_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="equipment model not found",
        )


@router.get(
    "/cases",
    response_model=list[EvaluationCaseResponse],
)
def list_cases(
    db: Session = Depends(get_db),
) -> list[EvaluationCase]:
    return list(
        db.scalars(
            select(EvaluationCase).order_by(EvaluationCase.id.desc())
        ).all()
    )


@router.post(
    "/cases",
    response_model=EvaluationCaseResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_case(
    payload: EvaluationCaseCreate,
    db: Session = Depends(get_db),
) -> EvaluationCase:
    _ensure_equipment(db, payload.equipment_model_id)

    case = EvaluationCase(**payload.model_dump())
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


@router.put(
    "/cases/{case_id}",
    response_model=EvaluationCaseResponse,
)
def update_case(
    case_id: int,
    payload: EvaluationCaseUpdate,
    db: Session = Depends(get_db),
) -> EvaluationCase:
    case = _get_case_or_404(db, case_id)
    changes = payload.model_dump(exclude_unset=True)

    if "equipment_model_id" in changes:
        _ensure_equipment(db, changes["equipment_model_id"])

    for key, value in changes.items():
        setattr(case, key, value)

    db.commit()
    db.refresh(case)
    return case


@router.delete(
    "/cases/{case_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_case(
    case_id: int,
    db: Session = Depends(get_db),
) -> Response:
    case = _get_case_or_404(db, case_id)
    db.delete(case)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/runs",
    response_model=list[EvaluationRunSummaryResponse],
)
def list_runs(
    db: Session = Depends(get_db),
) -> list[EvaluationRun]:
    return list(
        db.scalars(
            select(EvaluationRun)
            .order_by(EvaluationRun.id.desc())
            .limit(30)
        ).all()
    )


@router.get(
    "/runs/{run_id}",
    response_model=EvaluationRunResponse,
)
def get_run(
    run_id: int,
    db: Session = Depends(get_db),
) -> EvaluationRun:
    run = db.scalar(
        select(EvaluationRun)
        .options(selectinload(EvaluationRun.results))
        .where(EvaluationRun.id == run_id)
    )
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="evaluation run not found",
        )
    return run


@router.post(
    "/runs",
    response_model=EvaluationRunResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_run(
    payload: EvaluationRunCreate,
    db: Session = Depends(get_db),
) -> EvaluationRun:
    try:
        run = execute_evaluation_run(db=db, payload=payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return get_run(run.id, db)
