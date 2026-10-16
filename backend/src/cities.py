"""台灣 22 縣市座標表。

Open-Meteo 只接受經緯度，所以城市名稱在這裡轉成座標。
用固定白名單而不是 Geocoding API：少一次外部呼叫、不會比對到國外同名地點，
也順便擋掉任意輸入。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class City:
    id: str
    name_zh: str
    name_en: str
    lat: float
    lon: float
    aliases: tuple[str, ...] = ()


CITIES: tuple[City, ...] = (
    City("taipei", "臺北市", "Taipei", 25.0375, 121.5637, ("臺北",)),
    City("new-taipei", "新北市", "New Taipei", 25.0120, 121.4657, ("新北",)),
    City("taoyuan", "桃園市", "Taoyuan", 24.9936, 121.3010, ("桃園",)),
    City("taichung", "臺中市", "Taichung", 24.1477, 120.6736, ("臺中",)),
    City("tainan", "臺南市", "Tainan", 22.9999, 120.2270, ("臺南",)),
    City("kaohsiung", "高雄市", "Kaohsiung", 22.6273, 120.3014, ("高雄",)),
    City("keelung", "基隆市", "Keelung", 25.1276, 121.7392, ("基隆",)),
    City("hsinchu-city", "新竹市", "Hsinchu City", 24.8138, 120.9675, ("新竹", "hsinchu")),
    City("hsinchu-county", "新竹縣", "Hsinchu County", 24.8387, 121.0177),
    City("miaoli", "苗栗縣", "Miaoli", 24.5602, 120.8214, ("苗栗",)),
    City("changhua", "彰化縣", "Changhua", 24.0518, 120.5161, ("彰化",)),
    City("nantou", "南投縣", "Nantou", 23.9157, 120.6869, ("南投",)),
    City("yunlin", "雲林縣", "Yunlin", 23.7092, 120.4313, ("雲林",)),
    City("chiayi-city", "嘉義市", "Chiayi City", 23.4801, 120.4491, ("嘉義", "chiayi")),
    City("chiayi-county", "嘉義縣", "Chiayi County", 23.4518, 120.2555),
    City("pingtung", "屏東縣", "Pingtung", 22.6690, 120.4862, ("屏東",)),
    City("yilan", "宜蘭縣", "Yilan", 24.7021, 121.7378, ("宜蘭",)),
    City("hualien", "花蓮縣", "Hualien", 23.9872, 121.6015, ("花蓮",)),
    City("taitung", "臺東縣", "Taitung", 22.7583, 121.1444, ("臺東",)),
    City("penghu", "澎湖縣", "Penghu", 23.5711, 119.5793, ("澎湖",)),
    City("kinmen", "金門縣", "Kinmen", 24.4321, 118.3171, ("金門",)),
    City("lienchiang", "連江縣", "Lienchiang", 26.1608, 119.9517, ("連江", "馬祖", "matsu")),
)


def _normalize(text: str) -> str:
    """統一大小寫、去掉空白與連字號，並把「台」視為「臺」。"""
    return "".join(text.split()).replace("-", "").replace("_", "").replace("台", "臺").lower()


_LOOKUP: dict[str, City] = {}
for _city in CITIES:
    for _key in (_city.id, _city.name_zh, _city.name_en, *_city.aliases):
        _LOOKUP[_normalize(_key)] = _city


def find_city(query: str) -> City | None:
    return _LOOKUP.get(_normalize(query))
