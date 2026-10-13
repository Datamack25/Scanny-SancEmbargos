"""Conversion des noms / codes pays des listes officielles en ISO3."""
from __future__ import annotations

from functools import lru_cache

import pycountry

# Libellés fréquents dans les listes ONU / OFAC / UE que pycountry ne résout pas seul
MANUAL = {
    "iran (islamic republic of)": "IRN", "iran": "IRN",
    "democratic people's republic of korea": "PRK", "korea, north": "PRK", "north korea": "PRK",
    "korea, south": "KOR", "republic of korea": "KOR", "south korea": "KOR",
    "russia": "RUS", "russian federation": "RUS",
    "syria": "SYR", "syrian arab republic": "SYR",
    "burma": "MMR", "myanmar": "MMR",
    "venezuela": "VEN", "venezuela (bolivarian republic of)": "VEN",
    "bolivia": "BOL", "tanzania": "TZA", "united republic of tanzania": "TZA",
    "congo, democratic republic of the": "COD", "democratic republic of the congo": "COD",
    "congo": "COG", "republic of the congo": "COG",
    "laos": "LAO", "lao people's democratic republic": "LAO",
    "vietnam": "VNM", "viet nam": "VNM",
    "turkey": "TUR", "turkiye": "TUR", "türkiye": "TUR",
    "palestinian": "PSE", "west bank": "PSE", "gaza": "PSE", "palestine": "PSE",
    "kosovo": "XKX", "taiwan": "TWN", "macau": "MAC", "hong kong": "HKG",
    "cote d'ivoire": "CIV", "côte d'ivoire": "CIV", "ivory coast": "CIV",
    "united kingdom": "GBR", "uk": "GBR", "united states": "USA", "usa": "USA",
    "united arab emirates": "ARE", "uae": "ARE",
    "crimea region of ukraine": "UKR", "region: crimea": "UKR",
    "moldova": "MDA", "republic of moldova": "MDA",
    "british virgin islands": "VGB", "virgin islands, british": "VGB",
    "cabo verde": "CPV", "cape verde": "CPV", "eswatini": "SWZ", "swaziland": "SWZ",
    "czech republic": "CZE", "czechia": "CZE", "brunei": "BRN",
}


@lru_cache(maxsize=4096)
def to_iso3(value: str) -> str:
    if not value:
        return ""
    v = str(value).strip().strip(".")
    if not v or v.lower() in {"-0-", "unknown", "nan"}:
        return ""
    low = v.lower()
    if low in MANUAL:
        return MANUAL[low]
    if len(v) == 2:
        c = pycountry.countries.get(alpha_2=v.upper())
        if c:
            return c.alpha_3
    if len(v) == 3:
        c = pycountry.countries.get(alpha_3=v.upper())
        if c:
            return c.alpha_3
    try:
        return pycountry.countries.lookup(v).alpha_3
    except LookupError:
        pass
    try:
        res = pycountry.countries.search_fuzzy(v)
        return res[0].alpha_3 if res else ""
    except LookupError:
        return ""


FR_NAMES_CACHE: dict[str, str] = {}
SHORT_FR = {
    "IRN": "Iran", "PRK": "Corée du Nord", "KOR": "Corée du Sud", "RUS": "Russie", "SYR": "Syrie",
    "MMR": "Myanmar", "BOL": "Bolivie", "COD": "RD Congo", "COG": "Congo", "LAO": "Laos",
    "VEN": "Venezuela", "VNM": "Vietnam", "VGB": "Îles Vierges britanniques", "TZA": "Tanzanie",
    "MDA": "Moldavie", "GBR": "Royaume-Uni", "USA": "États-Unis", "PSE": "Palestine",
    "TWN": "Taïwan", "BLR": "Biélorussie", "CZE": "Tchéquie", "MKD": "Macédoine du Nord",
    "LBY": "Libye", "TUR": "Turquie", "CIV": "Côte d'Ivoire", "XKX": "Kosovo",
}


def name_fr(iso3: str) -> str:
    """Nom lisible du pays (français si disponible, sinon anglais)."""
    if not iso3:
        return ""
    if iso3 in SHORT_FR:
        return SHORT_FR[iso3]
    if iso3 in FR_NAMES_CACHE:
        return FR_NAMES_CACHE[iso3]
    c = pycountry.countries.get(alpha_3=iso3)
    name = iso3
    if c:
        name = getattr(c, "common_name", None) or c.name
        try:
            import gettext
            fr = gettext.translation("iso3166-1", pycountry.LOCALES_DIR, languages=["fr"])
            name = fr.gettext(c.name)
        except Exception:
            pass
    FR_NAMES_CACHE[iso3] = name
    return name
