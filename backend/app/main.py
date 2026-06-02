from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.config import settings
from app.db.neo4j import close_neo4j_driver
from app.db.postgres import Base, engine

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Rakshak AI starting — database: %s", settings.database_label)
    Base.metadata.create_all(bind=engine)
    yield
    close_neo4j_driver()


app = FastAPI(
    title="Rakshak AI",
    description="Crime Intelligence & Analytics Platform API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")
