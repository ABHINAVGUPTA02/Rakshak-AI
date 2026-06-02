import enum

from sqlalchemy import Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.postgres import Base


class EntityKind(str, enum.Enum):
    PHONE = "phone"
    EMAIL = "email"
    VEHICLE = "vehicle"
    ACCOUNT = "account"
    PROPERTY = "property"
    DOCUMENT = "document"


class CrimeEntity(Base):
    __tablename__ = "crime_entities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[EntityKind] = mapped_column(Enum(EntityKind), index=True)
    value: Mapped[str] = mapped_column(String(256), index=True)
    label: Mapped[str | None] = mapped_column(String(512))
    role: Mapped[str | None] = mapped_column(String(64))
    crime_record_id: Mapped[int] = mapped_column(ForeignKey("crime_records.id"), index=True)

    crime_record: Mapped["CrimeRecord"] = relationship(back_populates="entities")
