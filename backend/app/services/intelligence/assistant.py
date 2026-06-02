"""Rakshak AI conversational intelligence — reasoning agent grounded in live DB."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.config import settings
from app.schemas.chat import ChatMessage, ChatResponse, EvidenceItem
from app.services.intelligence.context_builder import build_intelligence_context, context_to_text, get_crime_stats, get_hotspots
from app.services.intelligence.reasoning_agent import detect_intent, retrieve_records, run_reasoning_agent
from app.services.intelligence.reply_formatter import to_markdown_reply

logger = logging.getLogger(__name__)

__all__ = ["answer_query", "get_crime_stats", "get_hotspots"]


async def answer_query(
    db: Session,
    message: str,
    language: str = "en",
    history: list[ChatMessage] | None = None,
) -> ChatResponse:
    history = history or []

    if settings.openai_api_key:
        try:
            from app.services.intelligence.llm_client import generate_llm_reply

            intent = detect_intent(message)
            records = retrieve_records(db, message, intent, limit=10)
            ctx = build_intelligence_context(db, message)
            ctx["matched_records"] = records
            ctx["primary_records"] = records or ctx["recent_records"]

            reply = await generate_llm_reply(message, context_to_text(ctx), history, language)
            evidence = [
                EvidenceItem(source="PostgreSQL", detail=f"{r.fir_number} — {r.crime_type}, {r.district}")
                for r in records[:8]
            ]
            suggestions = run_reasoning_agent(db, message, language).suggested_queries
            return ChatResponse(
                reply=reply,
                evidence=evidence,
                suggested_queries=suggestions,
                mode="llm",
            )
        except Exception as exc:
            logger.warning("LLM reasoning failed, falling back to local agent: %s", exc)
            fallback = run_reasoning_agent(db, message, language)
            fallback.reply = (
                f"> **Note:** AI model unavailable ({type(exc).__name__}). Showing database search results.\n\n"
                f"{to_markdown_reply(fallback.reply)}"
            )
            return ChatResponse(
                reply=fallback.reply,
                evidence=fallback.evidence,
                suggested_queries=fallback.suggested_queries,
                mode="local",
            )

    return run_reasoning_agent(db, message, language)
