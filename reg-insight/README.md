# REG-INSIGHT

Plateforme de veille LCB-FT : sanctions (ONU, OFAC, UE), risque pays GAFI, presse négative à la demande, leçons tirées des décisions des autorités. Base au format CSV, enrichie automatiquement et administrable.

## Démarrage

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # puis définir ADMIN_PASSWORD
streamlit run main.py
```

Premier lancement : **Espace administrateur → Mises à jour → Tout mettre à jour** pour télécharger les listes officielles. Comptez quelques minutes. Pour tester sans réseau, chargez les 60 entités fictives (régime « DÉMO »), puis supprimez-les en un clic.

## Pages

| Page | Contenu |
|---|---|
| Tableau de bord | Carte mondiale du risque pays et bulles d'entités sanctionnées. Un clic sur un pays ou une bulle affiche la liste des entités, chacune avec un lien vers sa fiche. |
| Recherche tiers | Filtrage par correspondance approchée (noms et alias). Fonctionne en unitaire ou par lot via CSV. |
| Fiche entité | Identité, griefs, cohérence entre régimes (ONU / OFAC / UE). Aide à la levée d'homonymie par date de naissance, nationalité ou identifiant (INN…). Presse négative, rapport HTML téléchargeable. |
| Listes de sanctions | Filtres, export CSV / JSON, journal des ajouts et radiations. |
| Risque pays (GAFI) | Listes noire et grise (plénière du 19 juin 2026), carences relevées, historique des entrées et sorties. |
| Presse négative | Recherche à la demande sur n'importe quelle entité : Google News FR/EN et GDELT, classement par catégorie LCB-FT et gravité. Liens pré-remplis vers des bases d'investigation gratuites (ICIJ, OCCRP Aleph, OpenSanctions…). Veille récurrente. |
| Rapports conformité | Piste d'audit des recherches et synthèse de la presse négative par cible. |
| Leçons à retenir | Décisions d'autorités : faits, leçon et procédure préventive. |
| Espace administrateur | File de validation de la presse, mises à jour des listes, édition de toutes les tables, ajout manuel d'entités (listes nationales ou internes), import CSV, demandes des utilisateurs, journal d'audit. |

## Principes de fiabilité

- **Sources directes** : les listes sont téléchargées depuis les publications officielles, sans intermédiaire.
- **Garde-fou d'ingestion** : une extraction de moins de 50 lignes est rejetée. Une inscription disparue de la source passe en « radié » ; elle n'est jamais supprimée.
- **Enrichissements préservés** : les champs complétés par l'administrateur survivent aux mises à jour.
- **Validation humaine** : un article de presse n'apparaît comme « validé » qu'après décision de l'administrateur.
- **IA encadrée (facultative)** : avec `ANTHROPIC_API_KEY`, l'IA qualifie chaque article (concerne la cible, homonyme possible, hors sujet). Elle ne lit que le titre et l'extrait récupérés, et répond « inconnu » plutôt que d'inventer.
- **Traçabilité** : chaque action est inscrite au journal `data/audit.csv`.

## Mise à jour automatique

`.github/workflows/update.yml` lance `scripts/update.py` chaque jour à 05:17 UTC (listes et veille presse), puis committe les CSV. Pour activer la qualification IA dans ce traitement, ajoutez le secret `ANTHROPIC_API_KEY` au dépôt GitHub.

## À savoir avant une mise en production

- **Stockage sur Streamlit Cloud** : le disque y est éphémère. Les modifications faites dans l'espace admin sont perdues au redémarrage, sauf si les CSV sont recommittés. Pour un usage commercial, hébergez sur un serveur avec disque persistant, ou migrez le stockage (`core/storage.py`) vers une base (PostgreSQL, Supabase…). Ce module est le seul à modifier.
- **Listes GAFI** : à mettre à jour après chaque plénière (février, juin, octobre) dans l'admin. Chaque changement de statut est historisé automatiquement.
- **Leçons à retenir** : les montants et faits pré-saisis sont à vérifier avec la décision officielle avant diffusion (colonne `verifie`).
- **Licences** : ONU, OFAC et UE publient leurs listes librement. Les données d'OpenSanctions (liens d'investigation uniquement ici) exigent une licence pour un usage commercial. Google News RSS et GDELT conviennent pour un MVP ; une offre payante gagnera à passer par une API presse sous contrat.
- **Responsabilité** : l'outil est une aide à la décision. Prévoyez dans les CGV que l'établissement reste responsable de l'analyse de ses clients.

## Structure

```
main.py                 navigation et thème
core/storage.py         CSV, schémas, journal d'audit
core/ingest.py          ingestion ONU / OFAC / UE et fusion historisée
core/adverse.py         moteur de presse négative et liens OSINT
core/screening.py       correspondance approchée, levée d'homonymie
core/report.py          rapport de filtrage HTML
views/*.py              pages
data/*.csv              base (GAFI, risque pays et leçons pré-remplis)
scripts/update.py       mise à jour planifiée
```
