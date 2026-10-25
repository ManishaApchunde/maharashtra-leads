from sqlalchemy import Double, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class District(Base):
    __tablename__ = "districts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    state: Mapped[str] = mapped_column(String(50), default="Maharashtra")

    talukas: Mapped[list["Taluka"]] = relationship(back_populates="district")


class Taluka(Base):
    __tablename__ = "talukas"
    __table_args__ = (UniqueConstraint("district_id", "name", name="uq_taluka_district_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    district_id: Mapped[int] = mapped_column(ForeignKey("districts.id", ondelete="CASCADE"), index=True)

    district: Mapped[District] = relationship(back_populates="talukas")


class Location(Base):
    """A city, town, village or area inside a taluka."""

    __tablename__ = "locations"
    __table_args__ = (
        UniqueConstraint("district_id", "taluka_id", "name", "type", name="uq_location"),
        Index("ix_locations_district_taluka", "district_id", "taluka_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    type: Mapped[str] = mapped_column(String(20), default="city")  # city | town | village | area
    taluka_id: Mapped[int | None] = mapped_column(ForeignKey("talukas.id", ondelete="SET NULL"))
    district_id: Mapped[int] = mapped_column(ForeignKey("districts.id", ondelete="CASCADE"))
    pincode: Mapped[str | None] = mapped_column(String(6))
    latitude: Mapped[float | None] = mapped_column(Double)
    longitude: Mapped[float | None] = mapped_column(Double)
