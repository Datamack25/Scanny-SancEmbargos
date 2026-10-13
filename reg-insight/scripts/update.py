"""Mise à jour planifiée (cron, GitHub Actions, n8n…).

    python scripts/update.py              # listes + veille presse
    python scripts/update.py --listes     # listes seulement
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import adverse, ingest, storage  # noqa: E402

storage.ensure_all()
only_lists = "--listes" in sys.argv
ingest.run(user="planificateur")
if not only_lists:
    wl = storage.load("watchlist")
    for t in wl["cible"]:
        print(f"Veille : {t}")
        adverse.search(t, user="planificateur", api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
                       model=os.environ.get("LLM_MODEL", "claude-sonnet-5-5"), log=print)
    if not wl.empty:
        wl["derniere_recherche"] = storage.now()
        storage.save("watchlist", wl)
