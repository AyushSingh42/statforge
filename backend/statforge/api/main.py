"""Starter FastAPI app. GET /fields, GET /seasons and POST /evaluate arrive in Week 3.

uvicorn statforge.api.main:app --reload
"""

from fastapi import FastAPI
from pydantic import BaseModel

from statforge import __version__
from statforge.config import data_source_name

app = FastAPI(title="StatForge API", version=__version__)


class HealthResponse(BaseModel):
    status: str
    version: str
    data_source: str


@app.get("/health")
def health() -> HealthResponse:
    return HealthResponse(status="ok", version=__version__, data_source=data_source_name())
