from app.services.cleaning import clean_row
from app.services.dedup import name_similarity
from app.utils.phone import normalize_phone
from app.utils.text import canonical_district, core_name, normalize_name, standardize_categories, validate_pincode


def test_phone_formats_resolve_to_same_number():
    for raw in ["+91 98765 43210", "09876543210", "9876543210", "919876543210", "+91-98765-43210", "98765.43210"]:
        assert normalize_phone(raw).normalized == "9876543210", raw


def test_landline_and_invalid():
    r = normalize_phone("020-2445 1234")
    assert r.normalized == "2024451234" and r.is_valid and not r.is_mobile
    assert normalize_phone("12345").problem == "invalid"
    assert normalize_phone("").problem == "missing"
    assert normalize_phone("0000000000").normalized is None


def test_names_normalise_and_core_matches():
    names = ["Om Xerox Center", "Om Xerox Centre", "OM XEROX"]
    cores = {core_name(n) for n in names}
    assert cores == {"om"}
    a, b = names[0], names[2]
    assert name_similarity(normalize_name(a), core_name(a), normalize_name(b), core_name(b)) == 100


def test_districts():
    assert canonical_district("Poona") == ("Pune", True)
    assert canonical_district("Aurangabad District") == ("Chhatrapati Sambhajinagar", True)
    assert canonical_district("Mumbai")[1] is False  # ambiguous, not guessed


def test_pincode():
    assert validate_pincode("411028") == ("411028", None)
    assert validate_pincode("560001") == ("560001", "outside_maharashtra")
    assert validate_pincode("4110") == (None, "invalid")


def test_categories():
    assert set(standardize_categories("xerox & printing")) >= {"Xerox + Printing", "Xerox", "Printing"}
    assert standardize_categories(None, "Sai Aaple Sarkar Seva Kendra") == ["CSC"]
    assert standardize_categories("stationary") == ["Stationery"]
    assert standardize_categories(None, "Ramesh Traders") == ["Other"]


def test_clean_row_never_invents_contact_name():
    r = clean_row({"shop_name": "test shop", "phone": "9876543210", "district": "pune"})
    assert r.record["contact_name"] is None
    assert r.record["district"] == "Pune"
    assert r.record["whatsapp_number"] is None  # not assumed from phone


def test_invalid_rows():
    assert clean_row({"phone": "9876543210"}).invalid_reason == "missing shop_name"
    assert clean_row({"shop_name": "X", "phone": "123"}).record is None


def test_second_phone_moves_to_alternate():
    r = clean_row({"shop_name": "A", "phone": "90000 00002 / 90000 00003"}).record
    assert r["normalized_phone"] == "9000000002" and r["normalized_alternate_phone"] == "9000000003"


def test_generic_words_do_not_make_different_shops_match():
    a, b = "Sai Xerox Centre", "Om Sai Xerox Centre"
    assert name_similarity(normalize_name(a), core_name(a), normalize_name(b), core_name(b)) < 80


def test_numbered_branches_are_not_duplicates():
    a, b = "Om Xerox 2", "Om Xerox 3"
    assert name_similarity(normalize_name(a), core_name(a), normalize_name(b), core_name(b)) <= 50
