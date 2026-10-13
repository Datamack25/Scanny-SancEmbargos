import pandas as pd
import streamlit as st

from core import ui

ui.setup("Leçons à retenir")
st.caption("Retours d'expérience sur les décisions des autorités : faits, leçon, procédure qui aurait pu éviter la sanction.")

rex = ui.data("rex")
rex["montant_n"] = pd.to_numeric(rex["montant"], errors="coerce")
themes = sorted(rex["theme"].unique())
sel = st.pills("Thème", themes, selection_mode="multi")
if sel:
    rex = rex[rex["theme"].isin(sel)]

for _, r in rex.sort_values("date", ascending=False).iterrows():
    amount = f"{r['montant_n'] / 1e9:.2f} Md {r['devise']}" if r["montant_n"] >= 1e9 else f"{r['montant_n'] / 1e6:.0f} M {r['devise']}"
    with st.container(border=True):
        top = st.columns([3, 1])
        top[0].markdown(f"**{r['etablissement']}** · {r['autorite']} · {r['date']}")
        top[1].markdown(f"### {amount}")
        st.markdown(f"**Faits** — {r['faits']}")
        st.markdown(f"**Leçon** — {r['lecon']}")
        st.markdown(f"**Procédure préventive** — {r['procedure_preventive']}")
        foot = st.columns([1, 3])
        foot[0].link_button("Décision officielle", r["source"])
        if r["verifie"] not in ("True", "oui"):
            foot[1].caption("Montant et faits à vérifier avec la décision officielle avant diffusion client.")
