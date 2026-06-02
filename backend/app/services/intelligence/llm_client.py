"""LLM-backed reasoning agent using live intelligence context."""

from __future__ import annotations

import logging
import ssl

import certifi
import httpx

try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass

from app.config import settings
from app.schemas.chat import ChatMessage

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are Rakshak AI — an investigative reasoning agent for Karnataka law enforcement.

Use ONLY the LIVE CRIME INTELLIGENCE CONTEXT provided. Never invent FIRs, persons, or statistics.

Reply in clean Markdown with this structure (do not label steps as UNDERSTAND/RETRIEVE/REASON):

## Summary
2–4 sentences: direct answer to the investigator's question first.

## Key findings
- Bullet points with **FIR numbers**, districts, crime types, persons, phones/accounts when relevant
- If no records match, say so clearly and state total records in the database

## Suggested next steps
- One or two short follow-up questions they could ask (optional; omit if empty database)

Formatting rules:
- Use ## for section headings exactly as above (Summary, Key findings, Suggested next steps)
- Use **bold** for FIR numbers and important names
- Use bullet lists, not numbered UNDERSTAND/RETRIEVE chains
- Map Bangalore → Bengaluru; use description text when district is Unknown
- English or Kannada as appropriate; keep tone professional and concise"""


async def generate_llm_reply(
    message: str,
    context_text: str,
    history: list[ChatMessage],
    language: str = "en",
) -> str:
    api_key = settings.openai_api_key
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not configured")

    lang_note = "Respond in Kannada." if language == "kn" else "Respond in English unless the user writes in Kannada."
    user_content = (
        f"{context_text}\n\n"
        f"---\nInvestigator question: {message}\n\n"
        f"{lang_note}\n"
        "Reply using the Markdown structure from your instructions."
    )

    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for turn in history[-8:]:
        messages.append({"role": turn.role, "content": turn.content})
    messages.append({"role": "user", "content": user_content})

    # macOS/Homebrew Python: truststore uses system keychain; certifi as fallback verify path
    verify: ssl.SSLContext | str = ssl.create_default_context(cafile=certifi.where())
    async with httpx.AsyncClient(timeout=60.0, verify=verify) as client:
        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.llm_model,
                "messages": messages,
                "temperature": 0.3,
                "max_tokens": 1200,
            },
        )
        if response.status_code == 401:
            raise RuntimeError("OpenAI rejected the API key (401). Check OPENAI_API_KEY in .env.")
        response.raise_for_status()
        data = response.json()
        reply = data["choices"][0]["message"]["content"].strip()
        logger.info("OpenAI chat completion ok (model=%s)", settings.llm_model)
        return reply
