from app.services.collector import area_label, keyword_category
from app.services.district_job import grid_areas, taluka_areas
from app.utils.maharashtra import DISTRICTS
from app.utils.talukas import MAHARASHTRA_TALUKAS


def test_every_district_has_a_taluka_list():
    assert set(MAHARASHTRA_TALUKAS) == set(DISTRICTS)
    assert sum(len(v) for v in MAHARASHTRA_TALUKAS.values()) > 350
    assert len(MAHARASHTRA_TALUKAS["Akola"]) == 7


def test_taluka_areas_include_hq_town_and_mumbai_fallback():
    names = [(a.taluka, a.city) for a in taluka_areas("Sangli", 3)]
    assert ("Khanapur", "Vita") in names
    assert taluka_areas("Mumbai City", 3) == []  # covered by CITY_AREAS


def test_keyword_category():
    assert keyword_category("cyber cafe") == "Cyber Cafe"
    assert keyword_category("Xerox centre") == "Xerox"
    assert keyword_category("CSC") == "CSC"


def test_grid_cells_cover_viewport():
    vp = {"low": {"latitude": 20.0, "longitude": 76.0}, "high": {"latitude": 20.5, "longitude": 76.5}}
    cells = grid_areas(vp, "Akola", 10, 1)
    assert 25 <= len(cells) <= 49
    assert cells[-1].rectangle["high"] == {"latitude": 20.5, "longitude": 76.5}


def test_area_label():
    assert area_label("Akola", "Akot", "Hiwarkhed") == "Hiwarkhed, Akot taluka, Akola district, Maharashtra"
