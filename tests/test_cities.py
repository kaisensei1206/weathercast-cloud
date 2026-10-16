import pytest

from cities import CITIES, find_city


def test_has_22_cities_with_unique_ids():
    assert len(CITIES) == 22
    assert len({c.id for c in CITIES}) == 22


def test_coordinates_are_inside_taiwan():
    # 範圍涵蓋金門（最西）與馬祖（最北），打錯小數點或經緯度對調都會被抓到
    for city in CITIES:
        assert 21.8 <= city.lat <= 26.4, city.id
        assert 118.0 <= city.lon <= 122.1, city.id


@pytest.mark.parametrize(
    ("query", "expected_id"),
    [
        ("Tainan", "tainan"),
        ("tainan", "tainan"),
        ("TAINAN", "tainan"),
        ("  Tainan  ", "tainan"),
        ("臺南市", "tainan"),
        ("臺南", "tainan"),
        ("台南", "tainan"),
        ("台 南", "tainan"),
        ("New Taipei", "new-taipei"),
        ("new-taipei", "new-taipei"),
        ("new_taipei", "new-taipei"),
        ("新北", "new-taipei"),
        ("台北", "taipei"),
        ("台東", "taitung"),
        ("馬祖", "lienchiang"),
        # 只說「新竹」「嘉義」時，指的是市而不是縣
        ("新竹", "hsinchu-city"),
        ("hsinchu", "hsinchu-city"),
        ("新竹縣", "hsinchu-county"),
        ("嘉義", "chiayi-city"),
        ("嘉義縣", "chiayi-county"),
    ],
)
def test_find_city_accepts_common_spellings(query, expected_id):
    assert find_city(query).id == expected_id


@pytest.mark.parametrize(
    "query",
    ["Tokyo", "", "台", "Tainan City Hall", "<script>alert(1)</script>", "' OR 1=1 --", "🌧️"],
)
def test_find_city_returns_none_for_unknown_input(query):
    assert find_city(query) is None
