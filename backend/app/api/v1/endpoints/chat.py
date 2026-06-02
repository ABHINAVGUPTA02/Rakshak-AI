from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.postgres import get_db
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.intelligence.assistant import answer_query

router = APIRouter()


@router.post("", response_model=ChatResponse)
async def chat(payload: ChatRequest, db: Session = Depends(get_db)):
    return await answer_query(db, payload.message, payload.language, payload.history)
