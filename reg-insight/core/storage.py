"""Stockage CSV centralisé + journal d'audit.

Toutes les lectures/écritures passent par ce module : l'interface, l'admin et
le script planifié partagent ainsi le même format.
"""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

DATA_DIR = Path(os.environ.get("REGINSIGHT_DATA", Path(__file__).resolve().parent.parent / "data"))

SCHEMAS: dict[str, list[str]] = {
    # Une ligne = une inscription (une entité listée par un régime donné)
    "entities": [
        "id", "regime", "source_ref", "nom", "alias", "type", "programme", "motif",
        "date_designation", "date_maj", "statut", "nationalite", "pays_iso3",
        "date_naissance", "lieu_naissance", "identifiants", "fonction",
        "source_url", "enrichissement", "valide_admin",
    ],
    "fatf": ["iso3", "pays", "statut", "depuis", "carences", "source", "mis_a_jour"],
    "country_risk": ["iso3", "niveau", "commentaire", "mis_a_jour"],
    "fatf_history": ["date", "iso3", "pays", "action", "liste", "source"],
    "rex": ["id", "etablissement", "secteur", "pays_iso3", "autorite", "date", "montant",
            "devise", "theme", "faits", "lecon", "procedure_preventive", "source", "verifie"],
    # Presse négative : chaque article trouvé par le moteur passe par la file de validation
    "adverse_media": [
        "id", "cible", "entity_id", "titre", "url", "source", "date_pub", "extrait",
        "categories", "score", "resume_ia", "pertinence_ia", "statut", "trouve_le",
        "valide_par", "valide_le",
    ],
    "requests": ["id", "date", "utilisateur", "cible", "pays", "statut", "nb_resultats"],
    "changes": ["date", "regime", "id", "nom", "action", "detail"],
    "watchlist": ["cible", "ajoute_le", "derniere_recherche"],
    "audit": ["date", "utilisateur", "action", "table", "detail"],
}


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def path(name: str) -> Path:
    return DATA_DIR / f"{name}.csv"


def load(name: str) -> pd.DataFrame:
    p = path(name)
    cols = SCHEMAS[name]
    if not p.exists():
        return pd.DataFrame(columns=cols)
    df = pd.read_csv(p, dtype=str, keep_default_na=False)
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    return df[cols + [c for c in df.columns if c not in cols]]


def save(name: str, df: pd.DataFrame) -> None:
    """Écriture atomique (fichier temporaire puis remplacement)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=DATA_DIR, suffix=".tmp")
    os.close(fd)
    df.to_csv(tmp, index=False, encoding="utf-8")
    os.replace(tmp, path(name))


def append(name: str, rows: list[dict]) -> None:
    if not rows:
        return
    df = load(name)
    df = pd.concat([df, pd.DataFrame(rows)], ignore_index=True)
    save(name, df.fillna(""))


def audit(user: str, action: str, table: str = "", detail: str = "") -> None:
    append("audit", [{"date": now(), "utilisateur": user, "action": action,
                      "table": table, "detail": detail[:500]}])


def ensure_all() -> None:
    for name in SCHEMAS:
        if not path(name).exists():
            save(name, pd.DataFrame(columns=SCHEMAS[name]))
