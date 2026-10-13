import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import ui
from core.geo import name_fr

ui.setup("Tableau de bord")

ent = ui.data("entities")
active = ent[ent["statut"] != "radié"]
changes = ui.data("changes")
fatf = ui.data("fatf")
media = ui.data("adverse_media")
ctry = ui.countries()

if ent.empty:
    st.info("La base est vide. Un administrateur peut lancer l'ingestion des listes officielles "
            "(ONU, OFAC, UE) depuis l'**Espace administrateur**, ou charger le jeu de démonstration.",
            icon=":material/database:")

# ---------------------------------------------------------------- alerte du jour
last = changes.sort_values("date", ascending=False).head(1)
if not last.empty:
    r = last.iloc[0]
    verb = "Nouvelle inscription" if r["action"] == "ajout" else "Radiation"
    st.markdown(f'<div class="ri-alert"><b>{verb}</b> · {r["nom"]} · {r["regime"]} · '
                f'<span class="ri-muted">{r["date"][:10]}</span></div>', unsafe_allow_html=True)

# --------------------------------------------------------------------- KPI
recent = changes[(changes["action"] == "ajout")
                 & (pd.to_datetime(changes["date"], errors="coerce") >= pd.Timestamp.now() - pd.Timedelta(days=30))]
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Inscriptions actives", f"{len(active):,}".replace(",", " "))
c2.metric("Ajouts (30 j)", len(recent))
c3.metric("Liste noire GAFI", int((fatf["statut"] == "noir").sum()))
c4.metric("Liste grise GAFI", int((fatf["statut"] == "gris").sum()))
c5.metric("Presse à valider", int((media["statut"] == "en_attente").sum()))

# --------------------------------------------------------------------- carte
regimes = sorted(active["regime"].unique().tolist())
f1, f2 = st.columns([3, 2])
sel_regimes = f1.multiselect("Régimes affichés", regimes, default=regimes, key="dash_regimes")
types = sorted(active["type"].unique().tolist())
sel_types = f2.multiselect("Types", types, default=types, key="dash_types")
view = active[active["regime"].isin(sel_regimes) & active["type"].isin(sel_types)]

counts = view[view["pays_iso3"] != ""].groupby("pays_iso3")
names_by_country = counts["nom"].apply(lambda s: "<br>".join(s.head(6).tolist()) + ("<br>…" if len(s) > 6 else ""))
nb_by_country = counts.size()

left, right = st.columns([3.2, 1])
with left:
    st.markdown("**Dernières sanctions & niveau de risque pays** "
                "<span class='ri-muted'>— cliquez sur un pays ou une bulle pour afficher ses entités</span>",
                unsafe_allow_html=True)
    order = ["Élevé", "Vigilance", "Standard"]
    fig = go.Figure()
    for i, lvl in enumerate(order):
        sub = ctry[ctry["risque"] == lvl]
        if sub.empty:
            continue
        fig.add_trace(go.Choropleth(
            locations=sub["iso3"], z=[i] * len(sub), customdata=sub["iso3"],
            colorscale=[[0, ui.RISK_COLORS[lvl]], [1, ui.RISK_COLORS[lvl]]], showscale=False,
            marker_line_color="white", marker_line_width=0.5, name=lvl, showlegend=True,
            text=sub["pays"] + "<br>" + sub["gafi"].where(sub["gafi"] != "", "Non listé GAFI")
                 + "<br>" + sub["nb"].astype(str) + " inscription(s)",
            hovertemplate="%{text}<extra>" + lvl + "</extra>",
            selected=dict(marker=dict(opacity=1)), unselected=dict(marker=dict(opacity=0.8)),
        ))
    if not nb_by_country.empty:
        bub = pd.DataFrame({"iso3": nb_by_country.index, "nb": nb_by_country.values,
                            "noms": names_by_country.reindex(nb_by_country.index).values})
        bub["pays"] = bub["iso3"].map(name_fr)
        size = (bub["nb"] ** 0.5) * 2.2 + 6
        fig.add_trace(go.Scattergeo(
            locations=bub["iso3"], locationmode="ISO-3", customdata=bub["iso3"],
            marker=dict(size=size.clip(upper=48), color="rgba(20,40,80,.55)",
                        line=dict(color="white", width=1)),
            text="<b>" + bub["pays"] + "</b> — " + bub["nb"].astype(str) + " entité(s)<br>" + bub["noms"],
            name="Entités sanctionnées", hovertemplate="%{text}<extra>Cliquez pour la liste</extra>",
            selected=dict(marker=dict(opacity=1)), unselected=dict(marker=dict(opacity=0.75)),
        ))
    fig.update_geos(showframe=False, showcoastlines=False, projection_type="natural earth",
                    showcountries=True, countrycolor="white", showland=True, landcolor="#DDE2EA",
                    bgcolor="rgba(0,0,0,0)", lataxis_range=[-56, 84])
    fig.update_layout(height=500, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="rgba(0,0,0,0)",
                      legend=dict(orientation="h", y=-0.02, x=0, title=None), clickmode="event+select")
    event = st.plotly_chart(fig, on_select="rerun", selection_mode="points", key="world_map",
                            config={"displayModeBar": False, "scrollZoom": False})

with right:
    st.markdown("**Pays à risque élevé**")
    high = ctry[ctry["risque"] == "Élevé"].sort_values("nb", ascending=False)
    for _, r in high.iterrows():
        st.markdown(f"{ui.badge('■', ui.RISK_COLORS['Élevé'])} {r['pays']} "
                    f"<span class='ri-muted'>({r['nb']})</span>", unsafe_allow_html=True)
    st.markdown("**Vigilance (liste grise)**")
    st.caption(", ".join(ctry[ctry["risque"] == "Vigilance"]["pays"].tolist()))

# ------------------------------------------------- pays sélectionné → entités
picked = None
try:
    pts = event.selection.points if event and event.selection else []
    if pts:
        p = pts[0]
        picked = p.get("customdata") or p.get("location")
        if isinstance(picked, list):
            picked = picked[0]
except AttributeError:
    pass
fallback = st.selectbox("…ou choisissez un pays", [""] + sorted(ctry["iso3"].tolist()),
                        format_func=lambda i: ctry.set_index("iso3")["pays"].get(i, i) if i else "—",
                        key="dash_country")
picked = picked or fallback or None

if picked:
    row = ctry.set_index("iso3").loc[picked] if picked in set(ctry["iso3"]) else None
    title = row["pays"] if row is not None else picked
    sub = view[view["pays_iso3"] == picked].sort_values("date_designation", ascending=False)
    st.markdown(f"#### {title} — {len(sub)} entité(s)")
    if row is not None:
        cols = st.columns([1, 3])
        cols[0].markdown(ui.badge(row["risque"], ui.RISK_COLORS[row["risque"]])
                         + (ui.badge(row["gafi"], "#3B4A63") if row["gafi"] else ""), unsafe_allow_html=True)
        if row["carences"]:
            cols[1].caption(f"Carences GAFI : {row['carences']}")
        if row["commentaire"]:
            cols[1].caption(f"Note administrateur : {row['commentaire']}")
    grid = st.columns(3)
    for k, (_, e) in enumerate(sub.head(60).iterrows()):
        with grid[k % 3]:
            st.page_link("views/fiche.py", label=f"{e['nom'][:60]} · {e['regime']}",
                         query_params={"id": e["id"]}, icon=":material/badge:")
    if len(sub) > 60:
        st.page_link("views/listes.py", label=f"Voir les {len(sub)} entités dans les listes",
                     query_params={"pays": picked}, icon=":material/list:")

# ------------------------------------------------------ dernières inscriptions
st.markdown("#### Dernières sanctions & mises à jour")
tbl = active.copy()
tbl["_d"] = pd.to_datetime(tbl["date_designation"], errors="coerce", format="mixed")
tbl = tbl.sort_values("_d", ascending=False).head(12)
if tbl.empty:
    st.caption("Aucune donnée.")
for _, e in tbl.iterrows():
    c = st.columns([4, 1, 3, 1.3])
    c[0].page_link("views/fiche.py", label=e["nom"][:70], query_params={"id": e["id"]})
    c[1].markdown(ui.badge(e["regime"], ui.REGIME_COLORS.get(e["regime"], "#555")), unsafe_allow_html=True)
    c[2].caption((e["programme"] or e["motif"])[:80])
    c[3].caption(e["date_designation"][:10])
