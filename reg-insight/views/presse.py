import streamlit as st

from core import adverse, storage, ui

ui.setup("Presse négative")
st.caption("Demandez à la plateforme de chercher la presse négative sur n'importe quelle personne ou société "
           "(sanctionnée ou non). Sources : Google News (FR/EN) et GDELT (presse mondiale). "
           "Chaque résultat est classé par catégorie LCB-FT et part en validation administrateur.")

ai_on = bool(ui.secret("ANTHROPIC_API_KEY"))
with st.form("adverse"):
    c = st.columns([3, 1])
    target = c[0].text_input("Entité à rechercher", st.query_params.get("q", ""),
                             placeholder="Nom complet de la personne ou raison sociale")
    country = c[1].text_input("Pays (facultatif)", placeholder="FRA")
    o = st.columns(3)
    use_gdelt = o[0].checkbox("Inclure GDELT (presse mondiale)", value=True)
    watch = o[1].checkbox("Ajouter à la veille récurrente")
    o[2].caption(f"Qualification IA : {'activée' if ai_on else 'désactivée (pas de clé API)'}")
    launched = st.form_submit_button("Lancer la recherche", type="primary", icon=":material/travel_explore:")

if launched and target.strip():
    if len(target.strip()) < 4:
        st.error("Saisissez un nom plus précis (au moins 4 caractères).")
        st.stop()
    with st.status(f"Recherche sur « {target} »…", expanded=True) as s:
        results = adverse.search(target, user=ui.current_user(), country=country.upper(),
                                 api_key=ui.secret("ANTHROPIC_API_KEY"),
                                 model=ui.secret("LLM_MODEL", "claude-sonnet-5-5"),
                                 use_gdelt=use_gdelt, log=st.write)
        s.update(label=f"{len(results)} article(s) retenu(s)", state="complete")
    if watch:
        wl = storage.load("watchlist")
        if adverse.norm(target) not in set(wl["cible"].map(adverse.norm)):
            storage.append("watchlist", [{"cible": target.strip(), "ajoute_le": storage.now(), "derniere_recherche": storage.now()}])
    st.session_state["last_target"] = target.strip()

tgt = st.session_state.get("last_target") or st.query_params.get("q", "")
if tgt:
    media = ui.data("adverse_media")
    res = media[(media["cible"].map(adverse.norm) == adverse.norm(tgt)) & (media["statut"] != "rejeté")]
    st.markdown(f"#### Résultats pour « {tgt} » — {len(res)}")
    if res.empty:
        st.success("Aucun article négatif retenu. Complétez par les bases d'investigation ci-dessous.",
                   icon=":material/check_circle:")
    by_cat = res["categories"].str.split(" \\| ").explode().value_counts()
    if not by_cat.empty:
        st.markdown(" ".join(ui.badge(f"{c} · {n}", "#3B4A63") for c, n in by_cat.items()), unsafe_allow_html=True)
    for _, m in res.sort_values(["score", "date_pub"], ascending=False).iterrows():
        sev = int(m["score"] or 0)
        color = "#C8372D" if sev >= 4 else "#E3A72F" if sev == 3 else "#6B7380"
        tag = ui.badge("validé", "#4E9A6B") if m["statut"] == "validé" else ui.badge("à valider", "#8A8F98")
        st.markdown(
            f"<div class='ri-card'>{ui.badge(f'gravité {sev}/5', color)}{tag} "
            f"<b><a href='{m['url']}' target='_blank'>{m['titre']}</a></b><br>"
            f"<span class='ri-muted'>{m['source']} · {m['date_pub']} · {m['categories']}"
            f"{' · IA : ' + m['pertinence_ia'] if m['pertinence_ia'] else ''}</span>"
            f"{'<br>' + m['resume_ia'] if m['resume_ia'] else ''}</div>", unsafe_allow_html=True)
    st.markdown("##### Bases d'investigation gratuites")
    cols = st.columns(3)
    for k, (name, url, desc) in enumerate(adverse.investigation_links(tgt)):
        cols[k % 3].markdown(f"[{name}]({url})  \n<span class='ri-muted'>{desc}</span>", unsafe_allow_html=True)

st.markdown("#### Veille récurrente")
wl = ui.data("watchlist")
st.caption("Ces cibles sont relancées automatiquement par la mise à jour planifiée.")
st.dataframe(wl, hide_index=True, width="stretch")
