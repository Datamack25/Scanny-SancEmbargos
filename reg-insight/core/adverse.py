"""Moteur de recherche de presse négative à la demande.

Sources gratuites, sans clé :
  * Google News RSS (FR + EN)
  * GDELT DOC 2.0 (presse mondiale, 65 langues)
Analyse :
  * scoring par mots-clés LCB-FT (catégories FR/EN) — toujours actif
  * qualification IA facultative (clé ANTHROPIC_API_KEY) : l'IA ne voit QUE le titre
    et l'extrait récupérés, et doit répondre « inconnu » plutôt que d'inventer.
Tout résultat entre dans la file de validation (statut « en_attente ») : rien
n'est publié sur une fiche sans validation humaine par l'administrateur.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import unicodedata
from datetime import datetime
from urllib.parse import quote, quote_plus, urlparse

import feedparser
import requests

from . import storage

UA = {"User-Agent": "Mozilla/5.0 (REG-INSIGHT veille conformite)"}

CATEGORIES = {
    "Blanchiment": ["blanchiment", "money laundering", "laundering", "lavado", "blanqueo"],
    "Fraude / escroquerie": ["fraude", "fraud", "escroquerie", "scam", "ponzi", "abus de bien", "detournement", "embezzlement", "faux et usage"],
    "Corruption": ["corruption", "bribery", "pot-de-vin", "kickback", "fcpa", "sapin", "trafic d'influence", "soudoy"],
    "Sanctions / embargo": ["sanction", "embargo", "ofac", "gel des avoirs", "asset freeze", "contournement", "evasion of sanctions", "sanctions evasion"],
    "Terrorisme": ["terroris", "financement du terrorisme", "terrorist financing", "djihad", "jihad"],
    "Fiscal": ["fraude fiscale", "tax evasion", "evasion fiscale", "tax fraud", "carrousel tva"],
    "Crime organisé": ["cartel", "mafia", "trafic de drogue", "drug trafficking", "narcotrafic", "crime organise", "organized crime", "traite"],
    "Judiciaire": ["condamn", "convicted", "mis en examen", "indicted", "inculp", "perquisition", "garde a vue", "arrested", "arrete", "proces", "trial", "plaide coupable", "pleaded guilty", "amende", "fined", "penalty", "enquete", "investigation", "poursuite"],
}
SEVERITY = {"Terrorisme": 5, "Sanctions / embargo": 5, "Blanchiment": 4, "Corruption": 4,
            "Crime organisé": 4, "Fraude / escroquerie": 3, "Fiscal": 3, "Judiciaire": 2}

NEG_FR = '(fraude OR blanchiment OR corruption OR sanction OR condamnation OR amende OR enquête OR "mis en examen" OR escroquerie OR terrorisme)'
NEG_EN = '(fraud OR "money laundering" OR corruption OR sanctions OR convicted OR fined OR investigation OR indicted OR bribery OR terrorism)'


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s.lower()).strip()


def _strip_html(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", s or "")).strip()


# ------------------------------------------------------------------ collecte
def google_news(target: str, lang: str = "fr") -> list[dict]:
    q = f'"{target}" {NEG_FR if lang == "fr" else NEG_EN}'
    hl, gl, ceid = ("fr", "FR", "FR:fr") if lang == "fr" else ("en-US", "US", "US:en")
    url = f"https://news.google.com/rss/search?q={quote_plus(q)}&hl={hl}&gl={gl}&ceid={ceid}"
    feed = feedparser.parse(requests.get(url, headers=UA, timeout=30).content)
    out = []
    for e in feed.entries[:40]:
        src = e.get("source", {}).get("title", "") if isinstance(e.get("source"), dict) else ""
        pub = ""
        if e.get("published_parsed"):
            pub = datetime(*e.published_parsed[:6]).strftime("%Y-%m-%d")
        out.append({"titre": _strip_html(e.get("title", "")), "url": e.get("link", ""),
                    "source": src or "Google News", "date_pub": pub,
                    "extrait": _strip_html(e.get("summary", ""))[:600]})
    return out


def gdelt(target: str, timespan: str = "24months") -> list[dict]:
    q = f'"{target}" {NEG_EN}'
    url = ("https://api.gdeltproject.org/api/v2/doc/doc?query=" + quote(q)
           + f"&mode=artlist&format=json&maxrecords=75&sort=datedesc&timespan={timespan}")
    r = requests.get(url, headers=UA, timeout=40)
    try:
        data = r.json()
    except ValueError:  # GDELT renvoie du texte en cas de requête refusée
        return []
    out = []
    for a in data.get("articles", []):
        d = a.get("seendate", "")
        out.append({"titre": a.get("title", ""), "url": a.get("url", ""),
                    "source": a.get("domain", "GDELT"),
                    "date_pub": f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) >= 8 else "",
                    "extrait": f"Langue : {a.get('language', '')} · Pays source : {a.get('sourcecountry', '')}"})
    return out


# ------------------------------------------------------------------- scoring
def classify(text: str) -> tuple[list[str], int]:
    t = norm(text)
    cats = [c for c, kws in CATEGORIES.items() if any(norm(k) in t for k in kws)]
    score = max([SEVERITY[c] for c in cats], default=0)
    if len(cats) >= 3:
        score = min(5, score + 1)
    return cats, score


def name_in_text(target: str, text: str) -> bool:
    """Le nom (tous ses mots significatifs) apparaît-il réellement dans le texte ?"""
    t = norm(text)
    tokens = [w for w in norm(target).split() if len(w) > 2]
    return bool(tokens) and all(w in t for w in tokens)


# ------------------------------------------------------------- qualification IA
SYSTEM_PROMPT = """Tu es analyste conformité LCB-FT. Tu qualifies des articles de presse pour
une recherche de presse négative sur une cible donnée.
RÈGLES STRICTES :
- Tu t'appuies UNIQUEMENT sur le titre et l'extrait fournis. Aucune connaissance externe.
- Si l'extrait ne permet pas de conclure, réponds "inconnu". N'invente jamais de faits,
  de montants, de dates ou de liens.
- Signale le risque d'homonymie quand rien ne rattache l'article à la cible précise.
Réponds en JSON : une liste d'objets {"i": index, "pertinence": "concerne_cible"|"homonyme_possible"|"hors_sujet"|"inconnu",
"resume": "≤ 30 mots, en français, factuel, au conditionnel si allégation"}."""


def llm_qualify(target: str, items: list[dict], api_key: str, model: str) -> None:
    if not api_key or not items:
        return
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    for start in range(0, len(items), 20):
        batch = items[start:start + 20]
        payload = [{"i": start + k, "titre": it["titre"], "extrait": it["extrait"][:400]} for k, it in enumerate(batch)]
        msg = client.messages.create(
            model=model, max_tokens=4000, system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": f"Cible : {target}\nArticles :\n{json.dumps(payload, ensure_ascii=False)}"}],
        )
        raw = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        m = re.search(r"\[.*\]", raw, re.S)
        if not m:
            continue
        for res in json.loads(m.group(0)):
            i = res.get("i")
            if isinstance(i, int) and 0 <= i < len(items):
                items[i]["pertinence_ia"] = res.get("pertinence", "inconnu")
                items[i]["resume_ia"] = res.get("resume", "")[:300]


# ---------------------------------------------------------------- orchestration
def search(target: str, entity_id: str = "", user: str = "utilisateur", country: str = "",
           api_key: str = "", model: str = "claude-sonnet-5-5", use_gdelt: bool = True,
           log=lambda *_: None) -> list[dict]:
    target = target.strip()
    raw, errors = [], []
    for name, fn in (("Google News FR", lambda: google_news(target, "fr")),
                     ("Google News EN", lambda: google_news(target, "en")),
                     ("GDELT", lambda: gdelt(target) if use_gdelt else [])):
        try:
            got = fn()
            log(f"{name} : {len(got)} résultats")
            raw += got
        except Exception as e:
            errors.append(f"{name} : {e}")
            log(f"{name} : indisponible ({e})")
    # dédoublonnage par URL et par titre normalisé
    seen, items = set(), []
    for it in raw:
        k = (urlparse(it["url"]).netloc + urlparse(it["url"]).path) or norm(it["titre"])
        k2 = norm(it["titre"])[:80]
        if k in seen or k2 in seen:
            continue
        seen.update({k, k2})
        text = f"{it['titre']} {it['extrait']}"
        if not name_in_text(target, text):
            continue  # filtre anti-bruit : le nom doit apparaître
        cats, score = classify(text)
        if score == 0:
            continue
        it.update({"categories": " | ".join(cats), "score": str(score),
                   "resume_ia": "", "pertinence_ia": ""})
        items.append(it)
    try:
        llm_qualify(target, items, api_key, model)
    except Exception as e:
        log(f"Qualification IA indisponible ({e}) — résultats conservés sans IA")
    items.sort(key=lambda x: (int(x["score"]), x["date_pub"]), reverse=True)

    ts = storage.now()
    existing = storage.load("adverse_media")
    known = set(zip(existing["cible"].map(norm), existing["url"]))
    rows = []
    for it in items:
        if (norm(target), it["url"]) in known:
            continue
        rows.append({
            "id": hashlib.sha1(f"{target}|{it['url']}".encode()).hexdigest()[:12],
            "cible": target, "entity_id": entity_id, **{k: it[k] for k in
            ("titre", "url", "source", "date_pub", "extrait", "categories", "score", "resume_ia", "pertinence_ia")},
            "statut": "en_attente", "trouve_le": ts, "valide_par": "", "valide_le": "",
        })
    storage.append("adverse_media", rows)
    storage.append("requests", [{"id": hashlib.sha1(f"{target}{ts}".encode()).hexdigest()[:10],
                                 "date": ts, "utilisateur": user, "cible": target, "pays": country,
                                 "statut": "erreurs : " + " ; ".join(errors) if errors and not raw else "terminée",
                                 "nb_resultats": str(len(items))}])
    storage.audit(user, "recherche presse négative", "adverse_media", f"{target} → {len(items)} résultats ({len(rows)} nouveaux)")
    return items


# --------------------------------------------------------- liens d'investigation
def investigation_links(target: str) -> list[tuple[str, str, str]]:
    """Bases gratuites à consulter manuellement (OSINT) — liens pré-remplis."""
    q = quote_plus(target)
    qq = quote_plus(f'"{target}"')
    return [
        ("OpenSanctions", f"https://www.opensanctions.org/search/?q={q}", "Sanctions, PPE, entités d'intérêt consolidées"),
        ("ICIJ Offshore Leaks", f"https://offshoreleaks.icij.org/search?q={q}", "Panama / Pandora / Paradise Papers"),
        ("OCCRP Aleph", f"https://aleph.occrp.org/search?q={q}", "Documents fuités, registres, corruption"),
        ("OpenCorporates", f"https://opencorporates.com/companies?q={q}", "Existence légale, dirigeants"),
        ("OFAC Sanctions Search", "https://sanctionssearch.ofac.treas.gov/", "Recherche officielle SDN (saisie manuelle)"),
        ("EU Sanctions Map", "https://www.sanctionsmap.eu/", "Régimes UE en vigueur"),
        ("CourtListener (US)", f"https://www.courtlistener.com/?q={qq}", "Décisions de justice fédérales US"),
        ("SEC EDGAR", f"https://efts.sec.gov/LATEST/search-index?q={qq}", "Dépôts et enquêtes SEC"),
        ("UK Companies House", f"https://find-and-update.company-information.service.gov.uk/search?q={q}", "Registre britannique"),
        ("Portal da Transparência (BR)", "https://portaldatransparencia.gov.br/sancoes/ceis", "Entreprises sanctionnées au Brésil"),
        ("Google — presse négative", f"https://www.google.com/search?q={quote_plus(target and f'{qq} AND (fraude OR blanchiment OR sanction OR condamnation OR amende OR poursuite OR investigation)')}", "Dork presse négative FR"),
        ("Google — décisions officielles", f"https://www.google.com/search?q={quote_plus(f'{qq} filetype:pdf (site:gouv.fr OR site:gov OR site:europa.eu) décision')}", "PDF de régulateurs / jugements"),
    ]
