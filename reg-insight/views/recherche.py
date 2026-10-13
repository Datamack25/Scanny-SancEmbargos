import pandas as pd
import streamlit as st

from core import screening, storage, ui

ui.setup("Recherche tiers")
st.caption("Filtrage par correspondance approchée sur les noms et alias (translittérations, inversions, "
           "mentions légales ignorées). Un résultat est une **alerte à analyser**, pas une confirmation.")

ent = ui.data("entities")
idx = ui.name_index()

tab1, tab2 = st.tabs(["Recherche unitaire", "Filtrage par lot (CSV)"])

with tab1:
    c = st.columns([3, 1, 1])
    q = c[0].text_input("Nom de la personne ou de la société", placeholder="ex. Ivan Petrov, Acme Trading LLC")
    thr = c[1].slider("Seuil", 70, 100, 85, help="Plus bas = plus d'alertes, plus de faux positifs")
    inc_rad = c[2].toggle("Inclure les radiés", value=False)
    if q:
        base = ent if inc_rad else ent[ent["statut"] != "radié"]
        res = screening.screen(q, base, idx[idx["id"].isin(base["id"])], threshold=thr)
        storage.append("requests", [{"id": "", "date": storage.now(), "utilisateur": ui.current_user(),
                                     "cible": q, "pays": "", "statut": "filtrage", "nb_resultats": str(len(res))}])
        if res.empty:
            st.success(f"Aucune correspondance ≥ {thr} pour « {q} ».", icon=":material/check_circle:")
        else:
            st.warning(f"{len(res)} correspondance(s) à analyser.", icon=":material/warning:")
            for _, r in res.iterrows():
                cols = st.columns([4, 1, 1, 2])
                cols[0].page_link("views/fiche.py", label=f"{r['nom']}", query_params={"id": r["id"]}, icon=":material/badge:")
                cols[1].markdown(ui.badge(r["regime"], ui.REGIME_COLORS.get(r["regime"], "#555")), unsafe_allow_html=True)
                cols[2].metric("Score", f"{r['score']:.0f}", label_visibility="collapsed")
                cols[3].caption(f"via « {r['nom_correspondant']} » · {r['type']} · {r['pays_iso3'] or '—'} · {r['date_naissance'][:20] or 'DDN —'}")
        st.page_link("views/presse.py", label=f"Lancer une recherche de presse négative sur « {q} »",
                     query_params={"q": q}, icon=":material/travel_explore:")

with tab2:
    st.markdown("Importez un CSV avec une colonne **nom** (colonnes facultatives : `date_naissance`, `nationalite`).")
    up = st.file_uploader("Fichier clients / fournisseurs", type=["csv"])
    thr2 = st.slider("Seuil", 70, 100, 88, key="thr_batch")
    if up:
        clients = pd.read_csv(up, dtype=str, keep_default_na=False, sep=None, engine="python")
        col = next((c for c in clients.columns if c.lower() in {"nom", "name", "raison_sociale"}), clients.columns[0])
        base = ent[ent["statut"] != "radié"]
        bidx = idx[idx["id"].isin(base["id"])]
        out = []
        bar = st.progress(0.0)
        for k, r in clients.iterrows():
            hits = screening.screen(r[col], base, bidx, threshold=thr2, limit=3)
            for _, h in hits.iterrows():
                out.append({"client": r[col], "correspondance": h["nom"], "regime": h["regime"], "score": h["score"],
                            "ddn_liste": h["date_naissance"], "ddn_client": r.get("date_naissance", ""),
                            "pays_liste": h["pays_iso3"], "id": h["id"]})
            bar.progress((k + 1) / len(clients))
        res = pd.DataFrame(out)
        st.metric("Clients avec alerte", res["client"].nunique() if not res.empty else 0, f"sur {len(clients)}")
        if not res.empty:
            st.dataframe(res, hide_index=True, width="stretch")
            st.download_button("Exporter les alertes", res.to_csv(index=False).encode("utf-8-sig"),
                               "alertes_filtrage.csv", "text/csv")
        storage.audit(ui.current_user(), "filtrage par lot", "entities", f"{len(clients)} lignes, {len(res)} alertes")
