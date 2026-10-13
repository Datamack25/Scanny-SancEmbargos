import pandas as pd
import streamlit as st

from core import adverse, ingest, storage, ui

ui.setup("Espace administrateur")

# ----------------------------------------------------------------- connexion
if not ui.is_admin():
    if not ui.secret("ADMIN_PASSWORD"):
        st.error("Aucun mot de passe administrateur n'est configuré. Ajoutez `ADMIN_PASSWORD` dans "
                 "`.streamlit/secrets.toml` (ou dans les secrets Streamlit Cloud), puis relancez.")
        st.stop()
    with st.form("login"):
        pwd = st.text_input("Mot de passe administrateur", type="password")
        if st.form_submit_button("Se connecter", type="primary"):
            if ui.check_password(pwd):
                st.session_state["is_admin"] = True
                storage.audit("admin", "connexion")
                st.rerun()
            else:
                storage.audit("inconnu", "échec de connexion admin")
                st.error("Mot de passe incorrect.")
    st.stop()

top = st.columns([5, 1])
top[1].button("Se déconnecter", on_click=lambda: st.session_state.update(is_admin=False))

media = ui.data("adverse_media")
pending_n = int((media["statut"] == "en_attente").sum())
tabs = st.tabs([f"Validation presse ({pending_n})", "Mises à jour", "Modifier les données",
                "Ajouter une entité", "Demandes utilisateurs", "Journal d'audit"])

# ---------------------------------------------------- 1. file de validation
with tabs[0]:
    st.caption("Rien n'apparaît comme « validé » sur une fiche sans votre décision. Vérifiez l'identité "
               "(homonymes) et la fiabilité de la source avant de valider.")
    pend = media[media["statut"] == "en_attente"].copy()
    if pend.empty:
        st.success("File vide.")
    else:
        cibles = sorted(pend["cible"].unique())
        cible = st.selectbox("Cible", ["Toutes"] + cibles)
        if cible != "Toutes":
            pend = pend[pend["cible"] == cible]
        pend.insert(0, "décision", "—")
        edited = st.data_editor(
            pend[["décision", "cible", "titre", "url", "source", "date_pub", "categories", "score", "pertinence_ia", "resume_ia", "id"]],
            hide_index=True, width="stretch", disabled=["cible", "titre", "url", "source", "date_pub", "categories", "score", "pertinence_ia", "resume_ia", "id"],
            column_config={"décision": st.column_config.SelectboxColumn("Décision", options=["—", "valider", "rejeter"], width="small"),
                           "url": st.column_config.LinkColumn("Lien", display_text="Ouvrir")},
            key="valid_editor")
        b = st.columns(3)
        if b[0].button("Appliquer les décisions", type="primary"):
            dec = edited[edited["décision"] != "—"].set_index("id")["décision"]
            df = storage.load("adverse_media")
            mask = df["id"].isin(dec.index)
            df.loc[mask, "statut"] = df.loc[mask, "id"].map(dec).map({"valider": "validé", "rejeter": "rejeté"})
            df.loc[mask, "valide_par"] = "admin"
            df.loc[mask, "valide_le"] = storage.now()
            storage.save("adverse_media", df)
            storage.audit("admin", "validation presse", "adverse_media", f"{(dec == 'valider').sum()} validés, {(dec == 'rejeter').sum()} rejetés")
            st.rerun()
        if b[1].button("Tout valider (sélection affichée)"):
            df = storage.load("adverse_media")
            mask = df["id"].isin(pend["id"])
            df.loc[mask, ["statut", "valide_par", "valide_le"]] = ["validé", "admin", storage.now()]
            storage.save("adverse_media", df)
            storage.audit("admin", "validation presse en masse", "adverse_media", f"{mask.sum()} validés")
            st.rerun()

# ------------------------------------------------------------ 2. mises à jour
with tabs[1]:
    ent = ui.data("entities")
    st.markdown("##### Listes de sanctions officielles")
    summary = ent.groupby(["regime", "statut"]).size().unstack(fill_value=0) if not ent.empty else pd.DataFrame()
    st.dataframe(summary, width="stretch")
    cols = st.columns(4)
    choice = None
    if cols[0].button("Tout mettre à jour", type="primary", icon=":material/sync:"):
        choice = ("ONU", "OFAC", "UE")
    for k, reg in enumerate(["ONU", "OFAC", "UE"]):
        if cols[k + 1].button(f"Mettre à jour {reg}"):
            choice = (reg,)
    if choice:
        with st.status("Ingestion en cours…", expanded=True) as s:
            res = ingest.run(choice, user="admin", log=st.write)
            ok = all("erreur" not in r for r in res)
            s.update(label="Terminé" if ok else "Terminé avec des erreurs", state="complete" if ok else "error")
    st.caption("Une extraction de moins de 50 lignes est rejetée (protection contre un fichier source vide ou tronqué). "
               "Les champs que vous avez enrichis sont conservés à chaque mise à jour.")

    st.markdown("##### Données de démonstration")
    d = st.columns(2)
    if d[0].button("Charger 60 entités fictives"):
        n = ingest.seed_demo(); storage.audit("admin", "chargement démo", "entities", str(n)); st.rerun()
    if d[1].button("Supprimer les données de démonstration"):
        df = storage.load("entities"); storage.save("entities", df[df["regime"] != "DÉMO"])
        storage.audit("admin", "purge démo", "entities"); st.rerun()

    st.markdown("##### Veille presse récurrente")
    wl = ui.data("watchlist")
    st.caption(f"{len(wl)} cible(s) suivie(s).")
    if st.button("Relancer la veille maintenant", disabled=wl.empty):
        with st.status("Recherche…", expanded=True):
            for t in wl["cible"]:
                st.write(f"**{t}**")
                adverse.search(t, user="admin (veille)", api_key=ui.secret("ANTHROPIC_API_KEY"),
                               model=ui.secret("LLM_MODEL", "claude-sonnet-5-5"), log=st.write)
            w = storage.load("watchlist"); w["derniere_recherche"] = storage.now(); storage.save("watchlist", w)

# -------------------------------------------------------- 3. éditer les tables
with tabs[2]:
    labels = {"fatf": "Listes GAFI (pays)", "fatf_history": "Historique GAFI", "country_risk": "Niveau de risque pays (surcharge)",
              "rex": "Leçons à retenir", "entities": "Inscriptions de sanctions", "adverse_media": "Presse négative",
              "watchlist": "Veille récurrente"}
    name = st.selectbox("Table", list(labels), format_func=labels.get)
    df = storage.load(name)
    if name == "entities":
        f = st.columns(2)
        reg = f[0].multiselect("Régime", sorted(df["regime"].unique()))
        q = f[1].text_input("Filtrer par nom ou id")
        view = df
        if reg:
            view = view[view["regime"].isin(reg)]
        if q:
            view = view[view["nom"].str.contains(q, case=False, regex=False) | (view["id"] == q)]
        st.caption(f"{len(view)} ligne(s) — édition limitée à 300 lignes filtrées à la fois.")
        view = view.head(300)
        edited = st.data_editor(view, hide_index=True, width="stretch", disabled=["id"], key="ed_entities")
        if st.button("Enregistrer", type="primary", key="save_entities"):
            base = df.set_index("id")
            base.update(edited.set_index("id"))
            storage.save("entities", base.reset_index())
            storage.audit("admin", "édition", "entities", f"{len(edited)} lignes revues")
            st.success("Enregistré."); st.rerun()
    else:
        edited = st.data_editor(df, hide_index=True, width="stretch", num_rows="dynamic", key=f"ed_{name}")
        c = st.columns(3)
        if c[0].button("Enregistrer", type="primary", key=f"save_{name}"):
            if name == "fatf":
                edited["mis_a_jour"] = edited["mis_a_jour"].where(edited["mis_a_jour"].astype(str) != "", storage.now()[:10])
                # toute entrée/sortie de liste est tracée dans l'historique
                old, new = dict(zip(df["iso3"], df["statut"])), dict(zip(edited["iso3"], edited["statut"]))
                ev = []
                for iso in set(old) | set(new):
                    if old.get(iso) != new.get(iso):
                        pays = (edited.set_index("iso3")["pays"].get(iso) if iso in new else df.set_index("iso3")["pays"].get(iso)) or iso
                        if old.get(iso):
                            ev.append({"date": storage.now()[:10], "iso3": iso, "pays": pays, "action": "retrait", "liste": old[iso], "source": "saisie admin"})
                        if new.get(iso):
                            ev.append({"date": storage.now()[:10], "iso3": iso, "pays": pays, "action": "ajout", "liste": new[iso], "source": "saisie admin"})
                storage.append("fatf_history", ev)
            storage.save(name, edited.fillna(""))
            storage.audit("admin", "édition", name, f"{len(df)} → {len(edited)} lignes")
            st.success("Enregistré."); st.rerun()
        c[1].download_button("Télécharger le CSV", df.to_csv(index=False).encode("utf-8-sig"), f"{name}.csv")
        up = c[2].file_uploader("Remplacer par un CSV", type=["csv"], key=f"up_{name}", label_visibility="collapsed")
        if up is not None:
            new = pd.read_csv(up, dtype=str, keep_default_na=False)
            missing = set(storage.SCHEMAS[name]) - set(new.columns)
            if missing:
                st.error(f"Colonnes manquantes : {', '.join(sorted(missing))}")
            elif st.button(f"Confirmer le remplacement ({len(new)} lignes)"):
                storage.save(name, new); storage.audit("admin", "import CSV", name, f"{len(new)} lignes"); st.rerun()

# ------------------------------------------------------- 4. ajout manuel
with tabs[3]:
    st.caption("Pour une liste nationale (ex. gel des avoirs DG Trésor), une liste interne ou un enrichissement ponctuel.")
    with st.form("add_entity", clear_on_submit=True):
        a = st.columns(3)
        nom = a[0].text_input("Nom *")
        regime = a[1].text_input("Régime / liste *", "Liste interne")
        typ = a[2].selectbox("Type", ["personne", "entité", "navire", "aéronef"])
        b = st.columns(3)
        pays = b[0].text_input("Pays ISO3")
        dob = b[1].text_input("Date de naissance")
        ident = b[2].text_input("Identifiants (ex. INN:770123456789)")
        alias = st.text_input("Alias (séparés par |)")
        motif = st.text_area("Motif / griefs")
        url = st.text_input("Source (URL)")
        if st.form_submit_button("Ajouter", type="primary"):
            if not nom or not regime:
                st.error("Nom et régime obligatoires.")
            else:
                eid = f"MAN-{pd.Timestamp.now().strftime('%Y%m%d%H%M%S')}"
                storage.append("entities", [{"id": eid, "regime": regime, "source_ref": eid, "nom": nom, "alias": alias,
                                             "type": typ, "programme": "", "motif": motif, "date_designation": storage.now()[:10],
                                             "date_maj": "", "statut": "actif", "nationalite": "", "pays_iso3": pays.upper(),
                                             "date_naissance": dob, "lieu_naissance": "", "identifiants": ident, "fonction": "",
                                             "source_url": url, "enrichissement": "", "valide_admin": "oui"}])
                storage.append("changes", [{"date": storage.now(), "regime": regime, "id": eid, "nom": nom, "action": "ajout", "detail": "saisie manuelle"}])
                storage.audit("admin", "ajout manuel", "entities", f"{eid} {nom}")
                st.success(f"Ajouté : {nom}")

# --------------------------------------------------- 5. demandes utilisateurs
with tabs[4]:
    req = ui.data("requests").sort_values("date", ascending=False)
    st.dataframe(req, hide_index=True, width="stretch")

# --------------------------------------------------------------- 6. audit
with tabs[5]:
    aud = ui.data("audit").sort_values("date", ascending=False)
    st.dataframe(aud, hide_index=True, width="stretch", height=500)
    st.download_button("Exporter le journal", aud.to_csv(index=False).encode("utf-8-sig"), "journal_audit.csv")
