from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.api.agent import router as agent_router
from app.api.chat import router as chat_router
from app.api.knowledge import router as knowledge_router
from app.api.orders import router as orders_router
from app.api.refunds import router as refunds_router
from app.api.schemas import HealthAliveResponse, HealthResponse, error_responses
from app.config import APP_VERSION
from app.db.connection import check_database

app = FastAPI(title="SmartService", version=APP_VERSION)
app.include_router(agent_router)
app.include_router(knowledge_router)
app.include_router(chat_router)
app.include_router(orders_router)
app.include_router(refunds_router)


@app.get("/health", tags=["health"], response_model=HealthAliveResponse)
def health() -> dict[str, str]:
    return {"status": "ok", "version": APP_VERSION}


@app.get("/health/db", tags=["health"], response_model=HealthResponse, responses=error_responses(503))
def database_health():
    try:
        check_database()
    except (RuntimeError, SQLAlchemyError):
        return JSONResponse(
            status_code=503,
            content={"detail": "Database is not ready", "error_code": "DATABASE_UNAVAILABLE"},
        )
    return {"status": "ok"}
