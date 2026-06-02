from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload

from app.db.postgres import get_db
from app.models.crime import CrimeRecord
from app.schemas.graph import GraphResponse
from app.services.enrichment.graph_sync import get_network_graph, sync_all_crimes, sync_crime_to_graph
from app.services.ingestion.fir_parser import ensure_crime_entities, ensure_crime_persons

router = APIRouter()


@router.get("/network", response_model=GraphResponse)
def network_graph(limit: int = 500, db: Session = Depends(get_db)):
    # Backfill persons from FIR text for records uploaded before parser fix
    crimes = (
        db.query(CrimeRecord)
        .options(joinedload(CrimeRecord.persons), joinedload(CrimeRecord.entities))
        .all()
    )
    for crime in crimes:
        changed = False
        if not crime.persons and crime.description:
            ensure_crime_persons(db, crime)
            changed = True
        if not crime.entities and crime.description:
            ensure_crime_entities(db, crime)
            changed = True
        if changed:
            sync_crime_to_graph(db, crime.id)

    data = get_network_graph(limit=limit)
    return GraphResponse(**data)


@router.post("/sync")
def sync_graph(rebuild: bool = True, db: Session = Depends(get_db)):
    """Rebuild Neo4j from PostgreSQL (default: clear stale nodes first)."""
    count = sync_all_crimes(db, rebuild=rebuild)
    return {"synced": count, "rebuilt": rebuild}
