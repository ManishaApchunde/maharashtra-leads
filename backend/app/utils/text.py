"""Text normalisation helpers for names, addresses and categories."""
import re
import unicodedata

from app.utils.maharashtra import (
    CATEGORIES, CATEGORY_RULES, DISTRICT_ALIASES, DISTRICTS, MAHARASHTRA_PIN_PREFIXES,
)

_DISTRICT_LOOKUP = {d.lower(): d for d in DISTRICTS} | DISTRICT_ALIASES
_CATEGORY_LOOKUP = {c.lower(): c for c in CATEGORIES}
_COMPILED_RULES = [(re.compile(p), c) for p, c in CATEGORY_RULES]

# Spelling variants unified before comparison
_REPLACEMENTS = [
    (r"\bcentre\b", "center"), (r"\bcentr\b", "center"), (r"\bcntr\b", "center"),
    (r"\bzerox\b", "xerox"), (r"\bxerx\b", "xerox"), (r"\bzeorx\b", "xerox"),
    (r"\bphoto copy\b", "photocopy"), (r"\bstationary\b", "stationery"),
    (r"&", " and "), (r"\bn\b", " and "),
    (r"\bshri\b|\bshree\b|\bsri\b", "shri"),
    (r"\bopp\b\.?", "opposite"), (r"\bnr\b\.?", "near"), (r"\brd\b\.?", "road"),
    (r"\bmarg\b", "road"), (r"\bchowk\b", "chowk"),
]

# Generic words removed to get a shop's "core" name ("Om Xerox Centre" -> "om")
_GENERIC_WORDS = {
    "xerox", "photocopy", "copy", "copier", "center", "shop", "and", "the", "printing", "printers",
    "printer", "print", "prints", "digital", "stationery", "stationers", "cyber", "cafe", "dtp",
    "online", "services", "service", "seva", "e", "computer", "computers", "multi", "point",
    "store", "stores", "enterprises", "enterprise", "agency", "agencies", "works", "zone", "hub",
    "csc", "common", "studio", "solutions", "graphics", "forms", "form", "document", "documents",
}


def clean_str(value) -> str | None:
    """Trim, collapse whitespace; empty/'nan'/'null' -> None. Never invents a value."""
    if value is None:
        return None
    s = unicodedata.normalize("NFKC", str(value)).strip()
    s = re.sub(r"\s+", " ", s)
    if s.lower() in {"", "nan", "none", "null", "na", "n/a", "-", "--"}:
        return None
    return s


def _base_normalize(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).lower()
    for pat, rep in _REPLACEMENTS:
        s = re.sub(pat, rep, s)
    s = re.sub(r"[^\w\s]", " ", s)          # drop punctuation, keep Devanagari letters
    return re.sub(r"\s+", " ", s).strip()


def normalize_name(name: str | None) -> str | None:
    return _base_normalize(name) if name else None


def core_name(name: str | None) -> str | None:
    norm = normalize_name(name)
    if not norm:
        return None
    words = [w for w in norm.split() if w not in _GENERIC_WORDS]
    return " ".join(words) or None


def normalize_address(address: str | None) -> str | None:
    if not address:
        return None
    s = _base_normalize(address)
    s = re.sub(r"\bmaharashtra\b|\bindia\b", " ", s)
    s = re.sub(r"\b\d{6}\b", " ", s)  # pincode is stored separately
    return re.sub(r"\s+", " ", s).strip() or None


def display_name(name: str | None) -> str | None:
    """Tidy the shop name for display without changing its words."""
    s = clean_str(name)
    if not s:
        return None
    if s.isupper() or s.islower():
        s = s.title()
    return s


def title_place(value: str | None) -> str | None:
    s = clean_str(value)
    return s.title() if s else None


def canonical_district(value: str | None) -> tuple[str | None, bool]:
    """Returns (district, recognised). Unrecognised names are kept as typed, not guessed."""
    s = clean_str(value)
    if not s:
        return None, False
    key = re.sub(r"\s+district$", "", s.lower()).strip()
    key = re.sub(r"\s+", " ", key)
    if key in _DISTRICT_LOOKUP:
        return _DISTRICT_LOOKUP[key], True
    return s.title(), False


def canonical_taluka(value: str | None) -> str | None:
    s = clean_str(value)
    if not s:
        return None
    s = re.sub(r"\s+(taluka|tal\.?|tehsil)$", "", s, flags=re.IGNORECASE).strip()
    return s.title() or None


def validate_pincode(value) -> tuple[str | None, str | None]:
    """Returns (pincode, problem). problem is 'invalid' or 'outside_maharashtra'."""
    s = clean_str(value)
    if not s:
        return None, None
    if re.fullmatch(r"\d{6}\.0", s):
        s = s[:-2]
    s = re.sub(r"\s", "", s)
    if not re.fullmatch(r"[1-9]\d{5}", s):
        return None, "invalid"
    if not s.startswith(MAHARASHTRA_PIN_PREFIXES):
        return s, "outside_maharashtra"
    return s, None


def extract_pincode(text: str | None) -> str | None:
    if not text:
        return None
    m = re.search(r"\b(4[0-4]\d{4})\b", text)
    return m.group(1) if m else None


def standardize_categories(raw_category: str | None, shop_name: str | None = None) -> list[str]:
    """Map free text ('xerox & printing', 'Cyber Café') to the standard category list.

    Uses the given category text first; the shop name is also scanned so that
    'Om Xerox & Printers' gets Xerox + Printing even when the category column is blank.
    """
    found: list[str] = []

    def add(c: str):
        if c not in found:
            found.append(c)

    for part in re.split(r"[,;/|]", raw_category or ""):
        part = clean_str(part)
        if not part:
            continue
        if part.lower() in _CATEGORY_LOOKUP:
            add(_CATEGORY_LOOKUP[part.lower()])
            continue
        norm = _base_normalize(part)
        for rx, cat in _COMPILED_RULES:
            if rx.search(norm):
                add(cat)

    if shop_name:
        norm = _base_normalize(shop_name)
        for rx, cat in _COMPILED_RULES:
            if rx.search(norm):
                add(cat)

    # "Xerox + Printing" implies both base categories for filtering
    if "Xerox + Printing" in found:
        add("Xerox")
        add("Printing")
    if not found:
        found.append("Other")
    elif len(found) > 1 and "Other" in found:
        found.remove("Other")
    return found


def primary_category(categories: list[str]) -> str:
    for c in ("Xerox + Printing", "Xerox", "Photocopy", "CSC", "E-Seva", "Online Services",
              "Digital Printing", "Printing", "DTP", "Cyber Cafe", "Stationery", "Computer Shop"):
        if c in categories:
            return c
    return categories[0] if categories else "Other"


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.IGNORECASE)


def clean_email(value) -> str | None:
    s = clean_str(value)
    if not s:
        return None
    s = s.lower()
    return s if EMAIL_RE.match(s) else None
