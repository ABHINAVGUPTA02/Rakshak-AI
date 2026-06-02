from pydantic import BaseModel, Field


class EntityCreate(BaseModel):
    kind: str
    value: str
    label: str | None = None
    role: str | None = None


class EntityResponse(BaseModel):
    id: int
    kind: str
    value: str
    label: str | None = None
    role: str | None = None

    model_config = {"from_attributes": True}
