import enum
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.postgres import Base


class PersonRole(str, enum.Enum):
    ACCUSED = "accused"
    VICTIM = "victim"
    WITNESS = "witness"


class CrimeRecord(Base):
    __tablename__ = "crime_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fir_number: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    crime_type: Mapped[str] = mapped_column(String(128), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    district: Mapped[str] = mapped_column(String(128), index=True)
    police_station: Mapped[str | None] = mapped_column(String(128))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    incident_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(64), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    persons: Mapped[list["Person"]] = relationship(back_populates="crime_record")


class Person(Base):
    __tablename__ = "persons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), index=True)
    role: Mapped[PersonRole] = mapped_column(Enum(PersonRole), index=True)
    age: Mapped[int | None] = mapped_column(Integer)
    address: Mapped[str | None] = mapped_column(Text)
    crime_record_id: Mapped[int] = mapped_column(ForeignKey("crime_records.id"), index=True)

    crime_record: Mapped["CrimeRecord"] = relationship(back_populates="persons")
