from datetime import date, datetime

from sqlalchemy import (
    JSON, Boolean, Date, Double, ForeignKey, Index, Integer, String, Text, func, text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, UTCDateTime

# MySQL notes:
#  * Double for coordinates/distances: MySQL FLOAT is single precision.
#  * JSON columns default to an empty array via an expression default (MySQL 8.0.13+).
#  * Booleans are TINYINT(1); server defaults are "0"/"1".
EMPTY_JSON_ARRAY = text("(JSON_ARRAY())")
FALSE = text("0")


class DataSource(Base):
    __tablename__ = "data_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_name: Mapped[str] = mapped_column(String(150), unique=True)
    source_type: Mapped[str] = mapped_column(String(50), default="other")  # api | csv | manual | directory | test | other
    source_url: Mapped[str | None] = mapped_column(Text)
    collection_method: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)


class BusinessCategory(Base):
    __tablename__ = "business_categories"

    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"), primary_key=True, index=True)


class Business(Base):
    __tablename__ = "businesses"
    __table_args__ = (
        Index("ix_biz_district_taluka_city", "district", "taluka", "city"),
        Index("ix_biz_district_lead_status_score", "district", "lead_status", "lead_score"),
        Index("ix_biz_lat_lng", "latitude", "longitude"),
        Index("ix_biz_source_place", "source", "source_place_id"),
        # Name similarity is computed in Python (rapidfuzz) on rows pre-filtered by pincode/city,
        # so MySQL needs no trigram index. Text comparisons are case-insensitive through the
        # utf8mb4_unicode_ci collation, so plain indexes on city/taluka serve case-insensitive lookups.
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # Identity / contact
    shop_name: Mapped[str] = mapped_column(String(255))
    contact_name: Mapped[str | None] = mapped_column(String(150))
    phone: Mapped[str | None] = mapped_column(String(40), index=True)
    normalized_phone: Mapped[str | None] = mapped_column(String(10), index=True)
    phone_valid: Mapped[bool] = mapped_column(Boolean, default=False)
    alternate_phone: Mapped[str | None] = mapped_column(String(40))
    normalized_alternate_phone: Mapped[str | None] = mapped_column(String(10), index=True)
    whatsapp_number: Mapped[str | None] = mapped_column(String(10), index=True)
    email: Mapped[str | None] = mapped_column(String(255))
    website: Mapped[str | None] = mapped_column(Text)

    # Primary (display) category; full list lives in business_categories
    category: Mapped[str | None] = mapped_column(String(50), index=True)

    # Address / geography
    address: Mapped[str | None] = mapped_column(Text)
    area: Mapped[str | None] = mapped_column(String(150))
    village: Mapped[str | None] = mapped_column(String(150))
    city: Mapped[str | None] = mapped_column(String(150), index=True)
    taluka: Mapped[str | None] = mapped_column(String(100), index=True)
    district: Mapped[str | None] = mapped_column(String(100), index=True)
    state: Mapped[str] = mapped_column(String(50), default="Maharashtra", server_default="Maharashtra")
    pincode: Mapped[str | None] = mapped_column(String(6), index=True)
    latitude: Mapped[float | None] = mapped_column(Double)
    longitude: Mapped[float | None] = mapped_column(Double)
    google_maps_url: Mapped[str | None] = mapped_column(Text)
    district_id: Mapped[int | None] = mapped_column(ForeignKey("districts.id", ondelete="SET NULL"), index=True)
    taluka_id: Mapped[int | None] = mapped_column(ForeignKey("talukas.id", ondelete="SET NULL"), index=True)
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id", ondelete="SET NULL"), index=True)

    # Normalised helpers for search + dedup
    normalized_name: Mapped[str | None] = mapped_column(String(255))
    core_name: Mapped[str | None] = mapped_column(String(255))  # name without generic words ("om" for "Om Xerox Centre")
    normalized_address: Mapped[str | None] = mapped_column(Text)

    # Source tracking
    source: Mapped[str] = mapped_column(String(150), index=True)
    data_source_id: Mapped[int | None] = mapped_column(ForeignKey("data_sources.id", ondelete="SET NULL"), index=True)
    source_url: Mapped[str | None] = mapped_column(Text)
    source_place_id: Mapped[str | None] = mapped_column(String(255))
    discovered_keyword: Mapped[str | None] = mapped_column(String(100))
    collection_run_id: Mapped[int | None] = mapped_column(ForeignKey("collection_runs.id", ondelete="SET NULL"))
    rating: Mapped[float | None] = mapped_column(Double)
    review_count: Mapped[int | None] = mapped_column(Integer)
    is_test_data: Mapped[bool] = mapped_column(Boolean, default=False, server_default=FALSE, index=True)

    # Quality / verification / dedup
    verification_status: Mapped[str] = mapped_column(String(20), default="unverified", server_default="unverified", index=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    quality_flags: Mapped[list] = mapped_column(JSON, default=list, server_default=EMPTY_JSON_ARRAY)
    duplicate_status: Mapped[str] = mapped_column(String(25), default="unique", server_default="unique", index=True)
    duplicate_of_id: Mapped[int | None] = mapped_column(ForeignKey("businesses.id", ondelete="SET NULL"))

    # Marketing
    lead_status: Mapped[str] = mapped_column(String(25), default="New", server_default="New", index=True)
    lead_score: Mapped[int] = mapped_column(Integer, default=0, server_default="0", index=True)
    score_breakdown: Mapped[list] = mapped_column(JSON, default=list, server_default=EMPTY_JSON_ARRAY)
    contacted: Mapped[bool] = mapped_column(Boolean, default=False, server_default=FALSE)
    contacted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    response_status: Mapped[str | None] = mapped_column(String(50))
    interested: Mapped[bool | None] = mapped_column(Boolean)
    demo_given: Mapped[bool] = mapped_column(Boolean, default=False, server_default=FALSE)
    converted: Mapped[bool] = mapped_column(Boolean, default=False, server_default=FALSE)
    notes: Mapped[str | None] = mapped_column(Text)
    next_followup_date: Mapped[date | None] = mapped_column(Date, index=True)

    # Government-office proximity (filled by the proximity job)
    nearest_gov_office_id: Mapped[int | None] = mapped_column(ForeignKey("government_offices.id", ondelete="SET NULL"))
    nearest_gov_office_m: Mapped[float | None] = mapped_column(Double, index=True)

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now(), onupdate=func.now())

    categories: Mapped[list[Category]] = relationship(secondary="business_categories", lazy="selectin")
    nearest_gov_office: Mapped["GovernmentOffice | None"] = relationship(lazy="joined")


class DuplicateCandidate(Base):
    """A suspected pair: `business_id` (newer record) may duplicate `matched_business_id`."""

    __tablename__ = "duplicate_candidates"
    __table_args__ = (Index("ix_dupcand_pair", "business_id", "matched_business_id", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    matched_business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    match_score: Mapped[int] = mapped_column(Integer)
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending", index=True)  # pending | confirmed | rejected
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    business: Mapped[Business] = relationship(foreign_keys=[business_id], lazy="joined")
    matched_business: Mapped[Business] = relationship(foreign_keys=[matched_business_id], lazy="joined")


class GovernmentOffice(Base):
    __tablename__ = "government_offices"
    __table_args__ = (Index("ix_gov_lat_lng", "latitude", "longitude"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    office_type: Mapped[str] = mapped_column(String(50), index=True)
    address: Mapped[str | None] = mapped_column(Text)
    village: Mapped[str | None] = mapped_column(String(150))
    taluka: Mapped[str | None] = mapped_column(String(100))
    district: Mapped[str | None] = mapped_column(String(100), index=True)
    latitude: Mapped[float | None] = mapped_column(Double)
    longitude: Mapped[float | None] = mapped_column(Double)
    phone: Mapped[str | None] = mapped_column(String(40))
    source: Mapped[str | None] = mapped_column(String(150))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())


class CollectionRun(Base):
    """One batch of collected data: a CSV upload or an API search for an area + keyword."""

    __tablename__ = "collection_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_type: Mapped[str] = mapped_column(String(20))  # csv | api | manual
    source: Mapped[str] = mapped_column(String(150))
    district: Mapped[str | None] = mapped_column(String(100))
    taluka: Mapped[str | None] = mapped_column(String(100))
    city: Mapped[str | None] = mapped_column(String(150))
    category: Mapped[str | None] = mapped_column(String(50))
    keyword: Mapped[str | None] = mapped_column(String(100))
    search_area: Mapped[str | None] = mapped_column(String(300))
    file_name: Mapped[str | None] = mapped_column(String(255))
    total_results: Mapped[int] = mapped_column(Integer, default=0)
    new_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    possible_duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    invalid_count: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="completed")
    message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())
