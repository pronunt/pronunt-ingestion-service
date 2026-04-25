from fastapi import APIRouter

from app.routes.v1.ingestion import router as ingestion_router

router = APIRouter()
router.include_router(ingestion_router)
