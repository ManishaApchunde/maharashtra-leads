"""Indian phone-number normalisation.

    "+91 98765 43210" -> "9876543210"
    "09876543210"     -> "9876543210"
    "020-2445 1234"   -> "2024451234"   (landline: STD code + number, leading 0 dropped)
"""
import re
from dataclasses import dataclass

_SPLIT = re.compile(r"\s*(?:/|,|;|\|| or )\s*", re.IGNORECASE)


@dataclass
class PhoneResult:
    raw: str | None
    normalized: str | None   # 10 digits, or None if missing/invalid
    is_valid: bool
    is_mobile: bool
    problem: str | None       # "missing" | "invalid" | None


def normalize_phone(raw: str | None) -> PhoneResult:
    if raw is None or not str(raw).strip():
        return PhoneResult(None, None, False, False, "missing")

    raw = str(raw).strip()
    # Excel often turns 9876543210 into "9876543210.0"
    if re.fullmatch(r"\d+\.0", raw):
        raw = raw[:-2]
    digits = re.sub(r"\D", "", raw)

    if digits.startswith("0091") and len(digits) == 14:
        digits = digits[4:]
    elif digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]

    if len(digits) != 10 or digits == digits[0] * 10:
        return PhoneResult(raw, None, False, False, "invalid")

    is_mobile = digits[0] in "6789"
    # Landlines (STD code + number) start with 1-5; 0 is never valid after stripping.
    if digits[0] == "0":
        return PhoneResult(raw, None, False, False, "invalid")
    return PhoneResult(raw, digits, True, is_mobile, None)


def split_phones(raw: str | None) -> list[str]:
    """'98765 43210 / 91234 56789' -> ['98765 43210', '91234 56789']."""
    if raw is None:
        return []
    raw = str(raw).strip()
    if not raw:
        return []
    parts = [p for p in _SPLIT.split(raw) if p.strip()]
    return parts or [raw]
