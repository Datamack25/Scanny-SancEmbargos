"""Filtrage de tiers (correspondance approchée) et aide à la levée d'homonymie."""
from __future__ import annotations

import re

import pandas as pd
from rapidfuzz import fuzz, process

from .adverse import norm

STOP = {"ltd", "llc", "sa", "sas", "sarl", "gmbh", "co", "company", "inc", "plc", "jsc", "ooo", "ao", "pjsc", "the", "de", "la", "le", "al", "el"}


def clean(name: str) -> str:
    return " ".join(w for w in norm(name).replace("-", " ").replace(".", " ").split() if w not in STOP)


def build_index(df: pd.DataFrame) -> pd.DataFrame:
    """Une ligne par nom ou alias, pointant vers l'id de l'inscription."""
    rows = []
    for _, r in df.iterrows():
        rows.append((r["id"], r["nom"], clean(r["nom"])))
        for a in str(r.get("alias", "")).split("|"):
            if a.strip():
                rows.append((r["id"], a.strip(), clean(a)))
    return pd.DataFrame(rows, columns=["id", "libelle", "cle"]).query("cle != ''")


def screen(query: str, entities: pd.DataFrame, index: pd.DataFrame, threshold: int = 85, limit: int = 50) -> pd.DataFrame:
    q = clean(query)
    if not q or index.empty:
        return entities.iloc[0:0].assign(score=[], nom_correspondant=[])
    hits = process.extract(q, index["cle"].tolist(), scorer=fuzz.token_set_ratio, limit=limit * 4, score_cutoff=threshold)
    best: dict[str, tuple[float, str]] = {}
    for _, score, pos in hits:
        # pénalise les correspondances d'un seul mot court (bruit fréquent)
        if len(q.split()) == 1 and len(q) < 5:
            score = min(score, fuzz.ratio(q, index["cle"].iat[pos]))
        eid = index["id"].iat[pos]
        if score >= threshold and score > best.get(eid, (0, ""))[0]:
            best[eid] = (round(score, 1), index["libelle"].iat[pos])
    if not best:
        return entities.iloc[0:0].assign(score=[], nom_correspondant=[])
    out = entities[entities["id"].isin(best)].copy()
    out["score"] = out["id"].map(lambda i: best[i][0])
    out["nom_correspondant"] = out["id"].map(lambda i: best[i][1])
    return out.sort_values("score", ascending=False).head(limit)


def _years(s: str) -> set[str]:
    return set(re.findall(r"(?:19|20)\d{2}", s or ""))


def _parse(d: str):
    d = d.strip()
    return pd.to_datetime(d, dayfirst=not re.match(r"^\d{4}-", d), errors="raise").date()


def _same_date(client: str, listed: str) -> bool:
    """Vrai seulement si une date COMPLÈTE du client correspond à une date de la fiche."""
    if len(re.sub(r"\D", "", client)) < 6:
        return False  # une année seule ne suffit pas
    try:
        c = _parse(client)
    except (ValueError, TypeError):
        return False
    for part in listed.split("|"):
        try:
            if _parse(part) == c:
                return True
        except (ValueError, TypeError):
            continue
    return False


def homonym_check(row: dict, dob: str = "", nationality: str = "", ident: str = "") -> list[tuple[str, str, str]]:
    """Compare les éléments du client à la fiche. Renvoie (critère, verdict, explication)."""
    out = []
    if dob:
        listed = row.get("date_naissance", "")
        if not listed:
            out.append(("Date de naissance", "non comparable", "La fiche officielle ne mentionne aucune date de naissance."))
        elif _same_date(dob, listed):
            out.append(("Date de naissance", "concordance", f"Identique à la fiche ({listed})."))
        elif _years(dob) & _years(listed):
            out.append(("Date de naissance", "partielle", f"Même année ; fiche : {listed}."))
        else:
            out.append(("Date de naissance", "divergence", f"Fiche : {listed}."))
    if nationality:
        listed = " ".join([row.get("nationalite", ""), row.get("pays_iso3", "")])
        if not listed.strip():
            out.append(("Nationalité", "non comparable", "Aucune nationalité sur la fiche."))
        elif norm(nationality) in norm(listed):
            out.append(("Nationalité", "concordance", f"Fiche : {listed.strip()}."))
        else:
            out.append(("Nationalité", "divergence", f"Fiche : {listed.strip()}. Une double nationalité reste possible."))
    if ident:
        listed = row.get("identifiants", "")
        digits = re.sub(r"\D", "", ident)
        if not listed:
            out.append(("Identifiant", "non comparable", "Aucun identifiant publié (INN, passeport…)."))
        elif digits and digits in re.sub(r"[^\d|]", "", listed):
            out.append(("Identifiant", "concordance", "Identifiant présent sur la fiche — correspondance forte."))
        else:
            out.append(("Identifiant", "divergence", f"Identifiants de la fiche : {listed}. Un identifiant unique (ex. INN) divergent écarte en principe l'homonyme."))
    return out
