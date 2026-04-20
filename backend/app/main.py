"""
Entry point do FastAPI.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from app.core.config import settings
from app.api import sales, customers, products, insights, etl, auth


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    yield
    # shutdown (cleanup das conexões acontece no DB session)


import os

def get_version():
    try:
        root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        version_file = os.path.join(root_dir, "version")
        with open(version_file, "r") as f:
            return f.read().strip()
    except Exception:
        return "1.0.0"

app = FastAPI(
    title="Vita BI API",
    version=get_version(),
    description="Sales intelligence API for Vita Forte Inc.",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Prometheus
Instrumentator().instrument(app).expose(app)

# Routes
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(sales.router, prefix="/api/sales", tags=["sales"])
app.include_router(customers.router, prefix="/api/customers", tags=["customers"])
app.include_router(products.router, prefix="/api/products", tags=["products"])
app.include_router(insights.router, prefix="/api/insights", tags=["insights"])
app.include_router(etl.router, prefix="/api/etl", tags=["etl"])


@app.get("/health")
async def health():
    return {"status": "ok", "service": settings.APP_NAME}
