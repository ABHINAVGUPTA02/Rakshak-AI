from pydantic import BaseModel, Field


class GraphNode(BaseModel):
    id: str
    label: str
    type: str
    meta: dict[str, str | None] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    source: str
    target: str
    relationship: str
    label: str | None = None


class GraphInsights(BaseModel):
    cases: int = 0
    people: int = 0
    phones: int = 0
    shared_phones: int = 0
    co_suspect_links: int = 0


class GraphResponse(BaseModel):
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    insights: GraphInsights = Field(default_factory=GraphInsights)


class HotspotPoint(BaseModel):
    district: str
    latitude: float
    longitude: float
    crime_count: int
    crime_type: str | None = None
