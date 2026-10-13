import pandas as pd
import streamlit as st

from core import adverse, report, screening, storage, ui
from core.geo import name_fr

st.markdown(ui.CSS, unsafe_allow_html=True)

eid = st.query_params.get("id", "")
ent = ui.data("entities")
if not eid or eid not in set(ent["id"]):
    st.warning("Entité introuvable. Ouvrez une fiche depuis la carte, la recherche ou les listes.")
    st.page_link("views/dashboard.py", label="Retour au tableau de bord", icon=":material/arrow_back:")
    st.stop()

row = ent.set_index("id").loc[eid].to_dict() | {"id": eid}

# ------------------------------------------------------------------ en-tête
st.markdown(f"## {row['nom']}")
status_col = "#C8372D" if row["statut"] != "radié" else "#6B7380"
st.markdown(
    ui.badge(row["regime"], ui.REGIME_COLORS.get(row["regime"], "#555"))
    + ui.badge(row["statut"], status_col) + ui.badge(row["type"], "#3B4A63")
    + (ui.badge("validé admin", "#4E9A6B") if row.get("valide_admin") == "oui" else ""),
    unsafe_allow_html=True)

left, right = st.columns([3, 2])
with left:
    st.markdown("##### Identité")
    pays = row["pays_iso3"]
    items = [("Alias", row["alias"]), ("Nationalité", row["nationalite"]),
             ("Pays rattaché", f"{name_fr(pays)} ({pays})" if pays else ""),
             ("Date de naissance", row["date_naissance"]), ("Lieu de naissance", row["lieu_naissance"]),
             ("Identifiants", row["identifiants"]), ("Fonction", row["fonction"])]
    for k, v in items:
        st.markdown(f"**{k}** : {v or '—'}")
    if row["type"] == "personne" and not row["date_naissance"]:
        st.warning("La fiche officielle ne donne pas de date de naissance : la levée d'homonymie "
                   "devra s'appuyer sur la nationalité, la fonction ou un identifiant unique.",
                   icon=":material/info:")
    st.markdown("##### Motif / griefs")
    st.write(row["motif"] or "Non précisé par la source.")
    if row.get("enrichissement"):
        st.markdown("##### Enrichissement")
        st.info(row["enrichissement"])
    st.markdown(f"**Programme** : {row['programme'] or '—'} · **Désignation** : {row['date_designation'] or '—'} "
                f"· **Mise à jour** : {row['date_maj'] or '—'} · **Réf. source** : {row['source_ref']}")
    if row["source_url"]:
        st.link_button("Source officielle", row["source_url"], icon=":material/open_in_new:")

# ------------------------------------------------- cohérence entre régimes
with right:
    st.markdown("##### Cohérence réglementaire")
    idx = ui.name_index()
    coh = screening.screen(row["nom"], ent, idx, threshold=90, limit=15)
    coh = coh[coh["id"] != eid]
    listed = {r: (r == row["regime"]) or (r in set(coh["regime"])) for r in ["ONU", "OFAC", "UE"]}
    for r, ok in listed.items():
        st.markdown(f"{'✅' if ok else '⬜'} **{r}** — {'inscrit' if ok else 'aucune inscription approchante'}")
    if not all(listed.values()):
        st.caption("Écart de périmètre entre juridictions : à documenter dans l'analyse.")
    for _, c in coh.iterrows():
        st.page_link("views/fiche.py", label=f"{c['regime']} · {c['nom'][:45]} ({c['score']:.0f})",
                     query_params={"id": c["id"]})

    st.markdown("##### Aide à la levée d'homonymie")
    with st.form("homonyme"):
        dob = st.text_input("Date de naissance du client", placeholder="1975-03-14")
        nat = st.text_input("Nationalité du client (code ou nom)", placeholder="RUS")
        ident = st.text_input("Identifiant (INN, passeport…)", placeholder="770123456789")
        go = st.form_submit_button("Comparer")
    if go:
        res = screening.homonym_check(row, dob, nat, ident)
        if not res:
            st.caption("Renseignez au moins un élément.")
        colors = {"concordance": "#C8372D", "partielle": "#E3A72F", "divergence": "#4E9A6B", "non comparable": "#6B7380"}
        for crit, verdict, why in res:
            st.markdown(f"{ui.badge(verdict, colors[verdict])} **{crit}** — {why}", unsafe_allow_html=True)

# ------------------------------------------------------------ presse négative
st.divider()
st.markdown("##### Presse négative")
media = ui.data("adverse_media")
mine = media[(media["entity_id"] == eid) | (media["cible"].map(adverse.norm) == adverse.norm(row["nom"]))]
validated = mine[mine["statut"] == "validé"]
pending = mine[mine["statut"] == "en_attente"]

b1, b2 = st.columns([1, 3])
if b1.button("Rechercher la presse négative", type="primary", icon=":material/travel_explore:"):
    with st.status(f"Recherche sur « {row['nom']} »…", expanded=True) as s:
        found = adverse.search(row["nom"], entity_id=eid, user=ui.current_user(), country=row["pays_iso3"],
                               api_key=ui.secret("ANTHROPIC_API_KEY"), model=ui.secret("LLM_MODEL", "claude-sonnet-5-5"),
                               log=st.write)
        s.update(label=f"{len(found)} article(s) pertinent(s) — envoyés en validation", state="complete")
    st.rerun()
b2.caption(f"{len(validated)} article(s) validé(s) · {len(pending)} en attente de validation par l'administrateur")

for _, m in validated.sort_values("date_pub", ascending=False).iterrows():
    st.markdown(f"- **[{m['titre']}]({m['url']})** · {m['source']} · {m['date_pub']}  \n"
                f"  <span class='ri-muted'>{m['categories']} · gravité {m['score']}/5"
                f"{' · ' + m['resume_ia'] if m['resume_ia'] else ''}</span>", unsafe_allow_html=True)
if not pending.empty:
    with st.expander(f"Résultats non validés ({len(pending)}) — à confirmer, risque d'homonymie"):
        for _, m in pending.sort_values("score", ascending=False).iterrows():
            st.markdown(f"- [{m['titre']}]({m['url']}) · {m['source']} · {m['date_pub']} · "
                        f"*{m['categories']}* {('· IA : ' + m['pertinence_ia']) if m['pertinence_ia'] else ''}")

with st.expander("Bases d'investigation gratuites (liens pré-remplis)"):
    for name, url, desc in adverse.investigation_links(row["nom"]):
        st.markdown(f"- [{name}]({url}) — {desc}")

# --------------------------------------------------------------- rapport + admin
st.divider()
html = report.entity_report(row, coh, mine, ui.current_user())
st.download_button("Télécharger le rapport de filtrage (HTML)", html, file_name=f"rapport_{eid}.html",
                   mime="text/html", icon=":material/download:")

if ui.is_admin():
    with st.expander("Modifier la fiche (administrateur)", icon=":material/edit:"):
        with st.form("edit_entity"):
            motif = st.text_area("Motif / griefs", row["motif"], height=120)
            enr = st.text_area("Enrichissement (sources fiables uniquement, citez-les)", row.get("enrichissement", ""), height=100)
            idents = st.text_input("Identifiants", row["identifiants"])
            dobv = st.text_input("Date de naissance", row["date_naissance"])
            pays = st.text_input("Pays ISO3", row["pays_iso3"])
            val = st.checkbox("Fiche relue et validée", value=row.get("valide_admin") == "oui")
            if st.form_submit_button("Enregistrer"):
                df = storage.load("entities")
                i = df.index[df["id"] == eid][0]
                for k, v in {"motif": motif, "enrichissement": enr, "identifiants": idents,
                             "date_naissance": dobv, "pays_iso3": pays.upper().strip(),
                             "valide_admin": "oui" if val else ""}.items():
                    df.at[i, k] = v
                storage.save("entities", df)
                storage.audit("admin", "modification fiche", "entities", eid)
                st.success("Fiche mise à jour.")
                st.rerun()
