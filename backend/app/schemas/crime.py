from datetime import date, datetime

from pydantic import BaseModel, Field

from app.schemas.entity import EntityCreate, EntityResponse


class PersonBase(BaseModel):
    name: str
    role: str
    age: int | None = None
    address: str | None = None


class PersonCreate(PersonBase):
    pass


class PersonResponse(PersonBase):
    id: int

    model_config = {"from_attributes": True}


class CrimeRecordBase(BaseModel):
    fir_number: str
    crime_type: str
    description: str | None = None
    district: str
    police_station: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    incident_date: date | None = None
    status: str = "open"


class CrimeRecordCreate(CrimeRecordBase):
    persons: list[PersonCreate] = Field(default_factory=list)
    entities: list[EntityCreate] = Field(default_factory=list)


class CrimeRecordResponse(CrimeRecordBase):
    id: int
    created_at: datetime
    persons: list[PersonResponse] = Field(default_factory=list)
    entities: list[EntityResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class CrimeStatsResponse(BaseModel):
    total_crimes: int
    by_type: dict[str, int]
    by_district: dict[str, int]
    open_cases: int
