"""LLM-backed reasoning agent using live intelligence context."""

from __future__ import annotations

import httpx

from app.config import settings
from app.schemas.chat import ChatMessage

SYSTEM_PROMPT = """You are Rakshak AI — an investigative reasoning agent for Karnataka law enforcement.

Your approach (show brief reasoning, then answer):
1. UNDERSTAND — What is the investigator asking? (location, person, FIR, pattern, comparison)
2. RETRIEVE — Use ONLY the LIVE CRIME INTELLIGENCE CONTEXT below
3. REASON — Connect facts: counts, locations, crime types, persons, dates
4. ANSWER — Clear, actionable intelligence briefing with FIR numbers cited

Rules:
- Never invent data not in the context
- Map user terms to database terms (e.g. Bangalore = Bengaluru/Bengaluru City in FIR text)
- If district field says "Unknown" but description mentions Bengaluru/Bangalore, treat it as Bengaluru
- Cite evidence: FIR numbers, police stations, districts
- English or Kannada as appropriate
- Be conversational but precise — like a senior analyst briefing an investigator"""


async def generate_llm_reply(
    message: str,
    context_text: str,
    history: list[ChatMessage],
    language: str = "en",
) -> str:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY not configured")

    lang_note = "Respond in Kannada." if language == "kn" else "Respond in English unless the user writes in Kannada."
    user_content = (
        f"{context_text}\n\n"
        f"---\nInvestigator question: {message}\n\n"
        f"{lang_note}\n"
        "Think step-by-step using the context, then provide your intelligence briefing."
    )

    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for turn in history[-8:]:
        messages.append({"role": turn.role, "content": turn.content})
    messages.append({"role": "user", "content": user_content})

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.llm_model,
                "messages": messages,
                "temperature": 0.3,
                "max_tokens": 1200,
            },
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()
