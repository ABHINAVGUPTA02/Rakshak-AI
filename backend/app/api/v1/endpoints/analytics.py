from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.postgres import get_db
from app.schemas.crime import CrimeStatsResponse
from app.schemas.graph import HotspotPoint
from app.services.intelligence.assistant import get_crime_stats, get_hotspots

router = APIRouter()


@router.get("/stats", response_model=CrimeStatsResponse)
def analytics_stats(db: Session = Depends(get_db)):
    return get_crime_stats(db)


@router.get("/hotspots", response_model=list[HotspotPoint])
def hotspots(db: Session = Depends(get_db)):
    return get_hotspots(db)
