"""Cleaning pipeline: one raw row (CSV / API / form) -> a clean record + quality flags.

Rules:
  * Never invent data. Missing values stay None (contact_name is never guessed).
  * Phone numbers are normalised to 10 digits; invalid ones are flagged, not "fixed".
  * A row is INVALID (not inserted) only if it has no shop name, or no way to
    reach/locate it at all (no valid phone, no address, no coordinates).
"""
from dataclasses import dataclass, field

from app.utils.maharashtra import TEST_DATA_SOURCE
from app.utils.phone import normalize_phone, split_phones
from app.utils.text import (
    canonical_district, canonical_taluka, clean_email, clean_str, core_name, display_name,
    extract_pincode, normalize_address, normalize_name, primary_category,
    standardize_categories, title_place, validate_pincode,
)


@dataclass
class CleanResult:
    record: dict | None
    categories: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    invalid_reason: str | None = None


def _float(value, lo: float, hi: float) -> float | None:
    s = clean_str(value)
    if s is None:
        return None
    try:
        f = float(s)
    except ValueError:
        return None
    return f if lo <= f <= hi else None


def _int(value) -> int | None:
    s = clean_str(value)
    if s is None:
        return None
    try:
        return int(float(s.replace(",", "")))
    except ValueError:
        return None


def clean_row(row: dict, default_source: str = "CSV Import") -> CleanResult:
    flags: list[str] = list(row.get("extra_flags") or [])

    shop_name = display_name(row.get("shop_name"))
    if not shop_name:
        return CleanResult(None, invalid_reason="missing shop_name")

    # --- phones -------------------------------------------------------------
    phone_parts = split_phones(row.get("phone"))
    alt_parts = split_phones(row.get("alternate_phone"))
    primary_raw = phone_parts[0] if phone_parts else None
    extra_raw = phone_parts[1:] + alt_parts
    alternate_raw = extra_raw[0] if extra_raw else None

    phone = normalize_phone(primary_raw)
    alt = normalize_phone(alternate_raw)
    # If the first phone is bad but the alternate is good, promote the alternate.
    if not phone.is_valid and alt.is_valid:
        if phone.problem == "invalid":
            flags.append("invalid_phone")
        phone, alt = alt, phone
    elif phone.problem == "missing":
        flags.append("missing_phone")
    elif phone.problem == "invalid":
        flags.append("invalid_phone")

    wa = normalize_phone(row.get("whatsapp_number"))
    whatsapp = wa.normalized if wa.is_valid and wa.is_mobile else None
    if clean_str(row.get("whatsapp_number")) and not whatsapp:
        flags.append("invalid_whatsapp")
    # Only an explicit yes/true marks the main mobile as WhatsApp; never assumed.
    if not whatsapp and str(row.get("whatsapp_same_as_phone", "")).strip().lower() in {"yes", "y", "true", "1"}:
        if phone.is_valid and phone.is_mobile:
            whatsapp = phone.normalized

    # --- geography ----------------------------------------------------------
    address = clean_str(row.get("address"))
    district, district_ok = canonical_district(row.get("district"))
    if not district:
        flags.append("missing_district")
    elif not district_ok:
        flags.append("unrecognized_district")
    taluka = canonical_taluka(row.get("taluka"))
    city = title_place(row.get("city"))
    village = title_place(row.get("village"))
    area = title_place(row.get("area"))

    pincode, pin_problem = validate_pincode(row.get("pincode"))
    if not pincode and not pin_problem:
        pincode = extract_pincode(address)  # taken from the address text, not guessed
    if pin_problem == "invalid":
        flags.append("invalid_pincode")
    elif pin_problem == "outside_maharashtra":
        flags.append("pincode_outside_maharashtra")
    if not pincode:
        flags.append("missing_pincode")
    if not address:
        flags.append("missing_address")

    lat = _float(row.get("latitude"), 15.5, 22.2)   # Maharashtra bounding box
    lng = _float(row.get("longitude"), 72.5, 81.0)
    if (lat is None) != (lng is None):
        lat = lng = None
    if clean_str(row.get("latitude")) and lat is None:
        flags.append("coordinates_outside_maharashtra")

    if not phone.is_valid and not address and lat is None:
        return CleanResult(None, invalid_reason="no valid phone, address or coordinates")

    # --- categories ---------------------------------------------------------
    categories = standardize_categories(row.get("category"), shop_name)

    source = clean_str(row.get("source")) or default_source
    rating = _float(row.get("rating"), 0, 5)
    review_count = _int(row.get("review_count"))

    record = {
        "shop_name": shop_name,
        "contact_name": clean_str(row.get("contact_name")),
        "phone": clean_str(phone.raw),
        "normalized_phone": phone.normalized,
        "phone_valid": phone.is_valid,
        "alternate_phone": clean_str(alt.raw),
        "normalized_alternate_phone": alt.normalized,
        "whatsapp_number": whatsapp,
        "email": clean_email(row.get("email")),
        "website": clean_str(row.get("website")),
        "category": primary_category(categories),
        "address": address,
        "area": area,
        "village": village,
        "city": city,
        "taluka": taluka,
        "district": district,
        "state": "Maharashtra",
        "pincode": pincode,
        "latitude": lat,
        "longitude": lng,
        "google_maps_url": clean_str(row.get("google_maps_url")),
        "normalized_name": normalize_name(shop_name),
        "core_name": core_name(shop_name),
        "normalized_address": normalize_address(address),
        "source": source,
        "source_url": clean_str(row.get("source_url")),
        "source_place_id": clean_str(row.get("source_place_id")),
        "discovered_keyword": clean_str(row.get("discovered_keyword") or row.get("keyword")),
        "rating": rating,
        "review_count": review_count,
        "is_test_data": source.upper() == TEST_DATA_SOURCE,
        "quality_flags": sorted(set(flags)),
    }
    return CleanResult(record, categories, sorted(set(flags)))
