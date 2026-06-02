"""Operational intelligence records: transactions, calls, person registry."""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.postgres import Base


class PersonProfile(Base):
    """Master person record from persons.csv (linked to FIRs via fir_person_links)."""

    __tablename__ = "person_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    external_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(256), index=True)
    age: Mapped[int | None] = mapped_column(Integer)
    address: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(String(32), index=True)
    email: Mapped[str | None] = mapped_column(String(256))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    crime_record_id: Mapped[int] = mapped_column(ForeignKey("crime_records.id"), index=True)
    fir_number: Mapped[str | None] = mapped_column(String(64), index=True)
    amount: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    from_account: Mapped[str | None] = mapped_column(String(128))
    to_account: Mapped[str | None] = mapped_column(String(128))
    upi_id: Mapped[str | None] = mapped_column(String(128))
    transaction_type: Mapped[str | None] = mapped_column(String(64))
    transaction_date: Mapped[date | None] = mapped_column(Date)
    counterparty: Mapped[str | None] = mapped_column(String(256))
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    crime_record: Mapped["CrimeRecord"] = relationship(back_populates="transactions")


class CallLog(Base):
    __tablename__ = "call_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    crime_record_id: Mapped[int | None] = mapped_column(ForeignKey("crime_records.id"), index=True)
    fir_number: Mapped[str | None] = mapped_column(String(64), index=True)
    caller_phone: Mapped[str | None] = mapped_column(String(32), index=True)
    callee_phone: Mapped[str | None] = mapped_column(String(32), index=True)
    call_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    cell_tower: Mapped[str | None] = mapped_column(String(128))
    person_name: Mapped[str | None] = mapped_column(String(256))
    direction: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    crime_record: Mapped["CrimeRecord | None"] = relationship(back_populates="call_logs")


from app.models.crime import CrimeRecord  # noqa: E402

CrimeRecord.transactions = relationship("Transaction", back_populates="crime_record", cascade="all, delete-orphan")
CrimeRecord.call_logs = relationship("CallLog", back_populates="crime_record", cascade="all, delete-orphan")
