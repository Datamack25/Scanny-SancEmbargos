import json

import streamlit as st

from core import ui

ui.setup("Listes de sanctions")
ent = ui.data("entities")

c = st.columns(5)
reg = c[0].multiselect("Régime", sorted(ent["regime"].unique()))
typ = c[1].multiselect("Type", sorted(ent["type"].unique()))
pays_default = st.query_params.get("pays", "")
pays = c[2].text_input("Pays (ISO3)", pays_default).upper().strip()
stat = c[3].selectbox("Statut", ["actif", "radié", "tous"])
txt = c[4].text_input("Mot-clé (nom, programme, motif)")

df = ent
if reg:
    df = df[df["regime"].isin(reg)]
if typ:
    df = df[df["type"].isin(typ)]
if pays:
    df = df[df["pays_iso3"] == pays]
if stat != "tous":
    df = df[df["statut"] == stat]
if txt:
    m = txt.lower()
    df = df[df[["nom", "alias", "programme", "motif"]].apply(lambda s: s.str.lower().str.contains(m, regex=False)).any(axis=1)]

st.caption(f"{len(df):,} inscription(s)".replace(",", " "))
show = df[["id", "nom", "regime", "type", "programme", "pays_iso3", "date_designation", "statut"]].copy()
show.insert(0, "fiche", "/fiche?id=" + show["id"])
st.dataframe(show.head(5000), hide_index=True, width="stretch", height=520,
             column_config={"fiche": st.column_config.LinkColumn("Fiche", display_text="Ouvrir")})
if len(df) > 5000:
    st.caption("Affichage limité aux 5 000 premières lignes — l'export contient tout.")

e1, e2 = st.columns(2)
e1.download_button("Exporter en CSV", df.to_csv(index=False).encode("utf-8-sig"), "reg_insight_sanctions.csv", "text/csv",
                   icon=":material/download:")
e2.download_button("Exporter en JSON", json.dumps(df.to_dict("records"), ensure_ascii=False, indent=1),
                   "reg_insight_sanctions.json", "application/json", icon=":material/data_object:")

st.markdown("#### Journal des ajouts et radiations")
ch = ui.data("changes").sort_values("date", ascending=False)
st.dataframe(ch.head(500), hide_index=True, width="stretch")
