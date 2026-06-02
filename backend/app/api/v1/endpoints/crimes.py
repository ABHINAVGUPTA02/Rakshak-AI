from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.postgres import get_db
from app.models.crime import CrimeRecord
from app.schemas.crime import CrimeRecordCreate, CrimeRecordResponse, CrimeStatsResponse
from app.services.enrichment.graph_sync import sync_crime_to_graph
from app.services.ingestion.service import ingest_crime_records
from app.services.intelligence.assistant import get_crime_stats
from app.services.intelligence.case_summary import find_similar_cases, summarize_case

router = APIRouter()


@router.get("", response_model=list[CrimeRecordResponse])
def list_crimes(db: Session = Depends(get_db)):
    return db.query(CrimeRecord).order_by(CrimeRecord.created_at.desc()).all()


@router.get("/stats", response_model=CrimeStatsResponse)
def crime_stats(db: Session = Depends(get_db)):
    return get_crime_stats(db)


@router.get("/{crime_id}", response_model=CrimeRecordResponse)
def get_crime(crime_id: int, db: Session = Depends(get_db)):
    crime = db.query(CrimeRecord).filter(CrimeRecord.id == crime_id).first()
    if not crime:
        raise HTTPException(status_code=404, detail="Crime record not found")
    return crime


@router.post("", response_model=CrimeRecordResponse, status_code=201)
def create_crime(payload: CrimeRecordCreate, db: Session = Depends(get_db)):
    created = ingest_crime_records(db, [payload])
    try:
        sync_crime_to_graph(db, created[0].id)
    except Exception:
        pass
    return created[0]


@router.get("/{crime_id}/summary")
def case_summary(crime_id: int, db: Session = Depends(get_db)):
    result = summarize_case(db, crime_id)
    if not result:
        raise HTTPException(status_code=404, detail="Crime record not found")
    return result


@router.get("/{crime_id}/similar")
def similar_cases(crime_id: int, db: Session = Depends(get_db), limit: int = 5):
    crime = db.query(CrimeRecord).filter(CrimeRecord.id == crime_id).first()
    if not crime:
        raise HTTPException(status_code=404, detail="Crime record not found")
    return find_similar_cases(db, crime_id, limit=limit)
