from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.postgres import get_db
from app.schemas.graph import GraphResponse
from app.services.enrichment.graph_sync import get_network_graph, sync_all_crimes

router = APIRouter()


@router.get("/network", response_model=GraphResponse)
def network_graph(limit: int = 50):
    data = get_network_graph(limit=limit)
    return GraphResponse(**data)


@router.post("/sync")
def sync_graph(db: Session = Depends(get_db)):
    count = sync_all_crimes(db)
    return {"synced": count}
