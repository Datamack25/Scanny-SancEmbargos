import plotly.express as px
import streamlit as st

from core import ui

ui.setup("Risque pays — GAFI")
fatf = ui.data("fatf")
hist = ui.data("fatf_history").sort_values("date", ascending=False)
ctry = ui.countries()

last = fatf["mis_a_jour"].max() if not fatf.empty else "—"
st.caption(f"Listes issues des déclarations publiques du GAFI (plénière du 19 juin 2026). "
           f"Dernière mise à jour de la base : {last}. Les plénières ont lieu en février, juin et octobre : "
           "l'administrateur met la table à jour après chacune.")

m = ctry[ctry["gafi"] != ""]
fig = px.choropleth(m, locations="iso3", color="gafi", hover_name="pays",
                    color_discrete_map={"Liste noire": "#1B1F2A", "Liste grise": "#E3A72F"})
fig.update_geos(showframe=False, showcoastlines=False, projection_type="natural earth", showland=True, landcolor="#DDE2EA", lataxis_range=[-56, 84],
                showcountries=True, countrycolor="white", bgcolor="rgba(0,0,0,0)")
fig.update_layout(height=380, margin=dict(l=0, r=0, t=0, b=0), legend_title=None, paper_bgcolor="rgba(0,0,0,0)")
st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

t1, t2 = st.tabs(["Juridictions listées", "Historique des ajouts / retraits"])
with t1:
    for status, label in (("noir", "Liste noire — appel à l'action"), ("gris", "Liste grise — surveillance renforcée")):
        st.markdown(f"##### {label}")
        for _, r in fatf[fatf["statut"] == status].sort_values("pays").iterrows():
            with st.expander(f"{r['pays']} · depuis {r['depuis']}"):
                st.write(r["carences"])
                n = int(ctry.set_index("iso3")["nb"].get(r["iso3"], 0))
                st.caption(f"{n} inscription(s) de sanctions rattachée(s) à ce pays.")
                c1, c2 = st.columns(2)
                c1.link_button("Déclaration GAFI", r["source"])
                c2.page_link("views/listes.py", label="Voir les entités", query_params={"pays": r["iso3"]})
with t2:
    st.dataframe(hist, hide_index=True, width="stretch",
                 column_config={"source": st.column_config.LinkColumn("Source", display_text="GAFI")})
