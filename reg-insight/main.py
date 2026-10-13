"""REG-INSIGHT — plateforme de veille sanctions, risque pays GAFI et presse négative.

Lancement : streamlit run main.py
"""
from pathlib import Path

import streamlit as st

from core import storage

ROOT = Path(__file__).resolve().parent  # fonctionne même si l'app est dans un sous-dossier du dépôt

st.set_page_config(page_title="REG-INSIGHT", page_icon=":material/shield:", layout="wide")
storage.ensure_all()

st.logo(str(ROOT / "assets" / "logo.svg"), size="large")

pages = {
    "Veille": [
        st.Page("views/dashboard.py", title="Tableau de bord", icon=":material/dashboard:", default=True),
        st.Page("views/recherche.py", title="Recherche tiers", icon=":material/person_search:"),
        st.Page("views/listes.py", title="Listes de sanctions", icon=":material/gavel:"),
        st.Page("views/pays.py", title="Risque pays (GAFI)", icon=":material/public:"),
        st.Page("views/presse.py", title="Presse négative", icon=":material/newspaper:"),
        st.Page("views/rapports.py", title="Rapports conformité", icon=":material/description:"),
        st.Page("views/lecons.py", title="Leçons à retenir", icon=":material/school:"),
    ],
    "Administration": [
        st.Page("views/admin.py", title="Espace administrateur", icon=":material/admin_panel_settings:"),
    ],
    "": [
        st.Page("views/fiche.py", title="Fiche entité", icon=":material/badge:", visibility="hidden"),
    ],
}
nav = st.navigation(pages)

with st.sidebar:
    st.divider()
    if st.session_state.get("is_admin"):
        st.caption(":material/verified_user: Connecté en administrateur")
    st.caption("Sources officielles : ONU · OFAC · UE · GAFI. "
               "Outil d'aide à la décision — l'établissement reste responsable de l'analyse de ses clients.")

nav.run()
