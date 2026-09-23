from fastapi import FastAPI

from app.api.documents import router as documents_router
from app.api.ingestion import router as ingestion_router


app = FastAPI(
    title="Industrial Maintenance Knowledge Base",
    version="0.1.0",
)

app.include_router(documents_router)
app.include_router(ingestion_router)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "industrial-maintenance-kb",
    }
