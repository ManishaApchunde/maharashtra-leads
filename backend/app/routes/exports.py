import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import SessionLocal
from app.models import Business
from app.services.query import BusinessFilters, apply_filters, ordered

router = APIRouter(tags=["export"])

COLUMNS = [
    "id", "shop_name", "contact_name", "phone", "whatsapp_number", "whatsapp_link", "alternate_phone",
    "email", "website", "categories", "address", "area", "village", "city", "taluka", "district",
    "pincode", "latitude", "longitude", "google_maps_url", "lead_score", "score_reasons", "lead_status",
    "contacted", "contacted_at", "response_status", "interested", "demo_given", "converted",
    "next_followup_date", "notes", "nearest_gov_office", "nearest_gov_office_type", "gov_office_distance_m",
    "verification_status", "duplicate_status", "source", "source_url", "rating", "review_count", "created_at",
]


def _row(b: Business) -> list:
    office = b.nearest_gov_office
    return [
        b.id, b.shop_name, b.contact_name or "", b.normalized_phone or b.phone or "", b.whatsapp_number or "",
        f"https://wa.me/91{b.whatsapp_number}" if b.whatsapp_number else "", b.normalized_alternate_phone or "",
        b.email or "", b.website or "", "; ".join(sorted(c.name for c in b.categories)), b.address or "",
        b.area or "", b.village or "", b.city or "", b.taluka or "", b.district or "", b.pincode or "",
        b.latitude if b.latitude is not None else "", b.longitude if b.longitude is not None else "",
        b.google_maps_url or "", b.lead_score, "; ".join(f"{x['factor']} (+{x['points']})" for x in b.score_breakdown or []),
        b.lead_status, "yes" if b.contacted else "no", b.contacted_at.isoformat() if b.contacted_at else "",
        b.response_status or "", "" if b.interested is None else ("yes" if b.interested else "no"),
        "yes" if b.demo_given else "no", "yes" if b.converted else "no",
        b.next_followup_date.isoformat() if b.next_followup_date else "", b.notes or "",
        office.name if office else "", office.office_type if office else "",
        int(b.nearest_gov_office_m) if b.nearest_gov_office_m is not None else "",
        b.verification_status, b.duplicate_status, b.source, b.source_url or "",
        b.rating if b.rating is not None else "", b.review_count if b.review_count is not None else "",
        b.created_at.isoformat() if b.created_at else "",
    ]


@router.get("/export/csv")
def export_csv(f: BusinessFilters = Depends()):
    """Same filters as GET /businesses. Streams in batches, so 100k+ rows are fine.

    Examples:
      /export/csv?district=Pune&category=Xerox
      /export/csv?has_whatsapp=true
      /export/csv?min_score=60&contacted=false
      /export/csv?near_office_m=1000&office_type=Talathi%20Office
    """
    stmt = ordered(apply_filters(select(Business), f), f.sort).options(selectinload(Business.categories))

    def generate():
        # Own session: it must stay open while the response streams.
        db: Session = SessionLocal()
        buf = io.StringIO()
        w = csv.writer(buf)
        buf.write("\ufeff")  # BOM so Excel shows Marathi text correctly
        w.writerow(COLUMNS)
        yield buf.getvalue()
        buf.seek(0); buf.truncate()
        n = 0
        try:
            for b in db.scalars(stmt.execution_options(yield_per=1000)):
                w.writerow(_row(b))
                n += 1
                if n % 500 == 0:
                    yield buf.getvalue()
                    buf.seek(0); buf.truncate()
            yield buf.getvalue()
        finally:
            db.close()

    parts = ["leads"] + [p for p in (f.district, f.taluka, f.city, f.category) if p]
    name = "_".join(p.replace(" ", "-") for p in parts) + f"_{datetime.now():%Y%m%d_%H%M}.csv"
    return StreamingResponse(generate(), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="{name}"'})
