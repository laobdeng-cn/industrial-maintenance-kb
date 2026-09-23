from fastapi import FastAPI

from app.api.answer import router as answer_router
from app.api.documents import router as documents_router
from app.api.equipment import router as equipment_router
from app.api.indexing import router as indexing_router
from app.api.ingestion import router as ingestion_router
from app.api.search import router as search_router


app = FastAPI(
    title="Industrial Maintenance Knowledge Base",
    version="0.1.0",
)

app.include_router(answer_router)
app.include_router(documents_router)
app.include_router(equipment_router)
app.include_router(indexing_router)
app.include_router(ingestion_router)
app.include_router(search_router)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "industrial-maintenance-kb",
    }
