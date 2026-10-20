"""Health check: lets the frontend, Render and the "Waking up Dawat AI…" loader
confirm the backend is alive without touching the database or an LLM."""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="dawat-backend", version="0.1.0")
