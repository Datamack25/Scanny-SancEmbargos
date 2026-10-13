"""Éléments d'interface partagés : chargement en cache, style, droits admin."""
from __future__ import annotations

import hmac
import os

import pandas as pd
import streamlit as st

from . import storage
from .geo import name_fr

RISK_COLORS = {"Élevé": "#C8372D", "Vigilance": "#E3A72F", "Standard": "#4E9A6B"}
REGIME_COLORS = {"ONU": "#2F6DB5", "OFAC": "#7A3FB0", "UE": "#1F8A8A", "DÉMO": "#8A8F98"}

CSS = """
<style>
.block-container {padding-top: 1.6rem; max-width: 1400px;}
[data-testid="stSidebar"] .brand {font-weight: 800; letter-spacing: .14em; font-size: 1.15rem; color: #E8EEF8; margin: 0 0 .2rem .2rem;}
[data-testid="stSidebar"] .brand span {color: #6FA8FF;}
.ri-alert {background: #FBECEA; border-left: 4px solid #C8372D; padding: .55rem .9rem; border-radius: 6px; margin: .3rem 0 .8rem 0; color: #5B1A14;}
.ri-alert b {color: #A0281F;}
.ri-badge {display:inline-block; padding: .08rem .5rem; border-radius: 999px; font-size: .78rem; font-weight: 600; color: white; margin-right: .25rem;}
.ri-muted {color: #6B7380; font-size: .85rem;}
.ri-card {border: 1px solid rgba(120,130,150,.25); border-radius: 10px; padding: .9rem 1rem; margin-bottom: .7rem;}
@media (prefers-color-scheme: dark) {
  .ri-alert {background: #3A1B19; color: #F4D6D2;}
  .ri-alert b {color: #FF8E84;}
}
</style>
"""


def setup(title: str, icon: str = "") -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown(f"### {icon} {title}" if icon else f"### {title}")


def badge(text: str, color: str) -> str:
    return f'<span class="ri-badge" style="background:{color}">{text}</span>'


def _mtime(name: str) -> float:
    p = storage.path(name)
    return p.stat().st_mtime if p.exists() else 0.0


@st.cache_data(show_spinner=False)
def _load_cached(name: str, mtime: float) -> pd.DataFrame:
    return storage.load(name)


def data(name: str) -> pd.DataFrame:
    """Lecture en cache, invalidée dès que le fichier change sur disque."""
    return _load_cached(name, _mtime(name)).copy()


def secret(key: str, default: str = "") -> str:
    try:
        if key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return os.environ.get(key, default)


def is_admin() -> bool:
    return bool(st.session_state.get("is_admin"))


def check_password(pwd: str) -> bool:
    expected = secret("ADMIN_PASSWORD")
    return bool(expected) and hmac.compare_digest(pwd.encode(), expected.encode())


def current_user() -> str:
    return "admin" if is_admin() else st.session_state.get("user_name", "utilisateur")


@st.cache_data(show_spinner=False)
def country_table(mt_fatf: float, mt_ent: float, mt_risk: float) -> pd.DataFrame:
    """Une ligne par pays : statut GAFI, niveau de risque, nombre d'inscriptions actives."""
    fatf = storage.load("fatf")
    ent = storage.load("entities")
    ent = ent[(ent["statut"] != "radié") & (ent["pays_iso3"] != "")]
    over = storage.load("country_risk")
    counts = ent.groupby("pays_iso3").agg(nb=("id", "count"),
                                          regimes=("regime", lambda s: ", ".join(sorted(set(s))))).reset_index()
    counts = counts.rename(columns={"pays_iso3": "iso3"})
    iso = sorted(set(counts["iso3"]) | set(fatf["iso3"]) | set(over["iso3"]))
    df = pd.DataFrame({"iso3": iso})
    df = df.merge(fatf[["iso3", "statut", "carences"]], on="iso3", how="left")
    df = df.merge(counts, on="iso3", how="left").merge(over[["iso3", "niveau", "commentaire"]], on="iso3", how="left")
    df = df.fillna({"statut": "", "carences": "", "nb": 0, "regimes": "", "niveau": "", "commentaire": ""})
    df["nb"] = df["nb"].astype(int)

    def level(r):
        if r["niveau"]:
            return r["niveau"]
        if r["statut"] == "noir":
            return "Élevé"
        if r["statut"] == "gris":
            return "Vigilance"
        return "Standard"

    df["risque"] = df.apply(level, axis=1)
    df["pays"] = df["iso3"].map(name_fr)
    df["gafi"] = df["statut"].map({"noir": "Liste noire", "gris": "Liste grise"}).fillna("")
    return df


def countries() -> pd.DataFrame:
    return country_table(_mtime("fatf"), _mtime("entities"), _mtime("country_risk"))


def entity_link(eid: str, label: str, key: str | None = None) -> None:
    st.page_link("views/fiche.py", label=label, query_params={"id": eid}, icon=":material/badge:")


@st.cache_data(show_spinner="Indexation des noms…")
def _index(mtime: float) -> pd.DataFrame:
    from .screening import build_index
    return build_index(storage.load("entities"))


def name_index() -> pd.DataFrame:
    return _index(_mtime("entities"))
