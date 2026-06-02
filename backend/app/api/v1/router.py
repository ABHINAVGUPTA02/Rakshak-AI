from fastapi import APIRouter

from app.api.v1.endpoints import analytics, chat, crimes, graph, health, ingestion

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(crimes.router, prefix="/crimes", tags=["crimes"])
api_router.include_router(ingestion.router, prefix="/ingest", tags=["ingestion"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(graph.router, prefix="/graph", tags=["graph"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
