import pandas as pd
import streamlit as st

from core import ui

ui.setup("Rapports conformité")

req = ui.data("requests").sort_values("date", ascending=False)
media = ui.data("adverse_media")
changes = ui.data("changes")

c = st.columns(3)
c[0].metric("Recherches enregistrées", len(req))
c[1].metric("Articles validés", int((media["statut"] == "validé").sum()))
c[2].metric("Mouvements de listes", len(changes))

st.markdown("#### Historique des recherches (piste d'audit)")
st.dataframe(req, hide_index=True, width="stretch", height=300)
st.download_button("Exporter l'historique", req.to_csv(index=False).encode("utf-8-sig"), "historique_recherches.csv")

st.markdown("#### Synthèse presse négative par cible")
if media.empty:
    st.caption("Aucune donnée.")
else:
    m = media[media["statut"] != "rejeté"].copy()
    m["score"] = pd.to_numeric(m["score"], errors="coerce").fillna(0)
    syn = m.groupby("cible").agg(articles=("id", "count"), gravite_max=("score", "max"),
                                 valides=("statut", lambda s: (s == "validé").sum()),
                                 categories=("categories", lambda s: ", ".join(sorted({c for x in s for c in x.split(" | ") if c}))),
                                 derniere=("trouve_le", "max")).reset_index().sort_values("gravite_max", ascending=False)
    st.dataframe(syn, hide_index=True, width="stretch")
    st.download_button("Exporter la synthèse", syn.to_csv(index=False).encode("utf-8-sig"), "synthese_presse.csv")

st.caption("Le rapport détaillé d'une entité listée se télécharge depuis sa fiche.")
