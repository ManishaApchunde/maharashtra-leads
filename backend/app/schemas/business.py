from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

LeadStatus = Literal["New", "Not Contacted", "Contacted", "Interested", "Follow Up",
                     "Not Interested", "Converted", "Invalid", "Do Not Contact"]
VerificationStatus = Literal["unverified", "verified", "invalid"]


class BusinessCreate(BaseModel):
    """Manual entry. Goes through the same cleaning + duplicate checks as a CSV row."""
    shop_name: str = Field(min_length=1, max_length=255)
    contact_name: str | None = None
    phone: str | None = None
    alternate_phone: str | None = None
    whatsapp_number: str | None = None
    email: str | None = None
    website: str | None = None
    category: str | None = None
    address: str | None = None
    area: str | None = None
    village: str | None = None
    city: str | None = None
    taluka: str | None = None
    district: str | None = None
    pincode: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    google_maps_url: str | None = None
    source: str = "Manual Entry"
    source_url: str | None = None
    notes: str | None = None


class BusinessUpdate(BaseModel):
    """Partial update: only the fields you send are changed."""
    shop_name: str | None = None
    contact_name: str | None = None
    phone: str | None = None
    alternate_phone: str | None = None
    whatsapp_number: str | None = None
    email: str | None = None
    website: str | None = None
    categories: list[str] | None = None
    address: str | None = None
    area: str | None = None
    village: str | None = None
    city: str | None = None
    taluka: str | None = None
    district: str | None = None
    pincode: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    google_maps_url: str | None = None
    verification_status: VerificationStatus | None = None
    lead_status: LeadStatus | None = None
    contacted: bool | None = None
    response_status: str | None = None
    interested: bool | None = None
    demo_given: bool | None = None
    converted: bool | None = None
    notes: str | None = None
    next_followup_date: date | None = None


class BusinessOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    shop_name: str
    contact_name: str | None
    phone: str | None
    normalized_phone: str | None
    phone_valid: bool
    alternate_phone: str | None
    normalized_alternate_phone: str | None
    whatsapp_number: str | None
    email: str | None
    website: str | None
    category: str | None
    category_names: list[str] = []
    address: str | None
    area: str | None
    village: str | None
    city: str | None
    taluka: str | None
    district: str | None
    state: str
    pincode: str | None
    latitude: float | None
    longitude: float | None
    google_maps_url: str | None
    source: str
    source_url: str | None
    source_place_id: str | None
    discovered_keyword: str | None
    rating: float | None
    review_count: int | None
    is_test_data: bool
    verification_status: str
    last_verified_at: datetime | None
    quality_flags: list
    duplicate_status: str
    duplicate_of_id: int | None
    lead_status: str
    lead_score: int
    score_breakdown: list
    contacted: bool
    contacted_at: datetime | None
    response_status: str | None
    interested: bool | None
    demo_given: bool
    converted: bool
    notes: str | None
    next_followup_date: date | None
    nearest_gov_office_id: int | None
    nearest_gov_office_m: float | None
    nearest_gov_office_name: str | None = None
    nearest_gov_office_type: str | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, b) -> "BusinessOut":
        out = cls.model_validate(b)
        out.category_names = sorted(c.name for c in b.categories)
        if b.nearest_gov_office:
            out.nearest_gov_office_name = b.nearest_gov_office.name
            out.nearest_gov_office_type = b.nearest_gov_office.office_type
        return out


class BusinessPage(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[BusinessOut]


class GovOfficeIn(BaseModel):
    name: str
    office_type: Literal["Talathi Office", "Tehsil Office", "Tahsildar Office", "Setu Office",
                         "Sub-Registrar Office", "District Collector Office", "Other Government Office"]
    address: str | None = None
    village: str | None = None
    taluka: str | None = None
    district: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    phone: str | None = None
    source: str | None = "Manual Entry"


class GovOfficeOut(GovOfficeIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    office_type: str
    created_at: datetime


class CollectionRequest(BaseModel):
    district: str
    taluka: str | None = None
    city: str | None = None
    category: str | None = None
    keyword: str
    max_pages: int = Field(default=1, ge=1, le=3)


class TalukaIn(BaseModel):
    name: str
    district_id: int


class LocationIn(BaseModel):
    name: str
    type: Literal["city", "town", "village", "area"] = "city"
    district_id: int
    taluka_id: int | None = None
    pincode: str | None = None
    latitude: float | None = None
    longitude: float | None = None
