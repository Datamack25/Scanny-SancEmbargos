"""Rapport de filtrage téléchargeable (HTML autonome, imprimable en PDF)."""
from __future__ import annotations

import html

import pandas as pd

from . import storage


def _e(x) -> str:
    return html.escape(str(x or "—"))


def entity_report(row: dict, coherence: pd.DataFrame, media: pd.DataFrame, analyst: str) -> str:
    med_rows = "".join(
        f"<tr><td>{_e(m['date_pub'])}</td><td><a href='{_e(m['url'])}'>{_e(m['titre'])}</a></td>"
        f"<td>{_e(m['categories'])}</td><td>{_e(m['statut'])}</td></tr>" for _, m in media.iterrows()
    ) or "<tr><td colspan=4>Aucun article enregistré.</td></tr>"
    coh_rows = "".join(
        f"<tr><td>{_e(r['regime'])}</td><td>{_e(r['nom'])}</td><td>{_e(r['score'])}</td><td>{_e(r['statut'])}</td></tr>"
        for _, r in coherence.iterrows()
    ) or "<tr><td colspan=4>Aucune autre inscription approchante.</td></tr>"
    fields = [("Régime", "regime"), ("Programme", "programme"), ("Type", "type"), ("Statut", "statut"),
              ("Date de désignation", "date_designation"), ("Alias", "alias"), ("Nationalité", "nationalite"),
              ("Pays", "pays_iso3"), ("Date de naissance", "date_naissance"), ("Lieu de naissance", "lieu_naissance"),
              ("Identifiants", "identifiants"), ("Fonction", "fonction"), ("Motif / griefs", "motif"),
              ("Enrichissement validé", "enrichissement"), ("Source officielle", "source_url")]
    ident = "".join(f"<tr><th>{k}</th><td>{_e(row.get(v))}</td></tr>" for k, v in fields)
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<title>Rapport REG-INSIGHT — {_e(row.get('nom'))}</title>
<style>body{{font-family:Arial,sans-serif;margin:32px;color:#1b2333}}h1{{font-size:20px}}h2{{font-size:15px;margin-top:24px;border-bottom:2px solid #1F4E9E}}
table{{border-collapse:collapse;width:100%;font-size:12px}}td,th{{border:1px solid #ccd;padding:5px;vertical-align:top;text-align:left}}th{{background:#eef2f8;width:200px}}
.meta{{color:#666;font-size:11px}}</style></head><body>
<h1>Rapport de filtrage — {_e(row.get('nom'))}</h1>
<p class="meta">Généré le {storage.now()} UTC par {_e(analyst)} · REG-INSIGHT · Réf. {_e(row.get('id'))}</p>
<h2>1. Inscription</h2><table>{ident}</table>
<h2>2. Cohérence entre régimes</h2><table><tr><th>Régime</th><th>Nom</th><th>Score</th><th>Statut</th></tr>{coh_rows}</table>
<h2>3. Presse négative</h2><table><tr><th>Date</th><th>Article</th><th>Catégories</th><th>Statut</th></tr>{med_rows}</table>
<h2>4. Conclusion de l'analyste</h2><p style="min-height:80px;border:1px dashed #aab;padding:8px">&nbsp;</p>
<p class="meta">Document d'aide à la décision établi à partir de sources publiques. Il ne se substitue pas à l'analyse
de l'établissement assujetti, seul responsable de la décision et des déclarations éventuelles.</p>
</body></html>"""
