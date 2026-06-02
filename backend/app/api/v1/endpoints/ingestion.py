from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.db.postgres import get_db
from app.services.ingestion.service import ingest_upload

router = APIRouter()


@router.post("/upload")
async def upload_file(file: UploadFile = File(...), db: Session = Depends(get_db)):
    return await ingest_upload(db, file)
