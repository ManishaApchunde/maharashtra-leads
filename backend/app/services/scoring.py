"""Marketing-priority lead score (0-100).

This is NOT a statistical model. It is a simple, transparent checklist that
puts shops most likely to handle land-record paperwork at the top of the call list.
Every point is shown in `score_breakdown` so you can see why a lead ranks where it does.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Business

RULES = {
    "xerox": 20,          # Xerox / Photocopy shops
    "printing": 10,       # Printing / Digital printing / DTP
    "csc": 15,            # Common Service Centre
    "online_gov": 20,     # Online services / E-Seva / Setu-type centres
    "phone": 10,
    "whatsapp": 10,
    "gov_1km": 10,        # within 1 km of a government office
    "gov_2km": 5,         # within 2 km (only if not already within 1 km)
    "reviews": 5,         # 20+ public reviews (an established, visible shop)
}
GOOD_REVIEW_COUNT = 20


def compute_score(b: Business, categories: list[str] | None = None,
                  office_label: str | None = None) -> tuple[int, list[dict]]:
    cats = set(categories if categories is not None else [c.name for c in b.categories])
    breakdown: list[dict] = []

    def add(key: str, label: str):
        breakdown.append({"factor": label, "points": RULES[key]})

    if cats & {"Xerox", "Photocopy", "Xerox + Printing"}:
        add("xerox", "Xerox / photocopy business")
    if cats & {"Printing", "Digital Printing", "DTP"}:
        add("printing", "Printing / DTP service")
    if "CSC" in cats:
        add("csc", "Common Service Centre (CSC)")
    if cats & {"Online Services", "E-Seva"}:
        add("online_gov", "Online / government document services")
    if b.phone_valid and b.normalized_phone:
        add("phone", "Valid phone number")
    if b.whatsapp_number:
        add("whatsapp", "WhatsApp number available")
    if b.nearest_gov_office_m is not None:
        label = office_label or (b.nearest_gov_office.office_type if b.nearest_gov_office else "government office")
        if b.nearest_gov_office_m <= 1000:
            add("gov_1km", f"Within 1 km of {label} ({int(b.nearest_gov_office_m)} m)")
        elif b.nearest_gov_office_m <= 2000:
            add("gov_2km", f"Within 2 km of {label} ({int(b.nearest_gov_office_m)} m)")
    if (b.review_count or 0) >= GOOD_REVIEW_COUNT:
        add("reviews", f"{b.review_count} public reviews")

    return min(100, sum(x["points"] for x in breakdown)), breakdown


def apply_score(b: Business, categories: list[str] | None = None) -> None:
    b.lead_score, b.score_breakdown = compute_score(b, categories)


def rescore_all(db: Session, batch: int = 2000) -> int:
    """Recalculate every score in batches (safe for hundreds of thousands of rows)."""
    last_id, n = 0, 0
    while True:
        rows = db.scalars(select(Business).where(Business.id > last_id).order_by(Business.id).limit(batch)).all()
        if not rows:
            break
        for b in rows:
            apply_score(b)
        db.commit()
        n += len(rows)
        last_id = rows[-1].id
    return n
