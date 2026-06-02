from pydantic import BaseModel, Field


class GraphNode(BaseModel):
    id: str
    label: str
    type: str


class GraphEdge(BaseModel):
    source: str
    target: str
    relationship: str


class GraphResponse(BaseModel):
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)


class HotspotPoint(BaseModel):
    district: str
    latitude: float
    longitude: float
    crime_count: int
    crime_type: str | None = None
