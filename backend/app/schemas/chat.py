from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str


class ChatRequest(BaseModel):
    message: str
    language: str = "en"
    history: list[ChatMessage] = Field(default_factory=list)


class EvidenceItem(BaseModel):
    source: str
    detail: str


class ChatResponse(BaseModel):
    reply: str
    evidence: list[EvidenceItem] = Field(default_factory=list)
    suggested_queries: list[str] = Field(default_factory=list)
    mode: str = "local"  # "llm" when OpenAI succeeds, "local" for template agent
