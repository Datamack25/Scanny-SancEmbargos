"""Ingestion des listes de sanctions officielles (sources directes, gratuites).

- ONU  : liste consolidée du Conseil de sécurité (XML)
- OFAC : SDN (CSV principal + adresses + alias)
- UE   : liste consolidée des sanctions financières (CSV FSF 1.1)

Chaque source est normalisée vers le schéma `entities`. Une réingestion :
  * ajoute les nouvelles inscriptions (journal `changes` : « ajout »)
  * passe en « radié » celles qui ont disparu (journal : « retrait »)
  * conserve les champs enrichis par l'administrateur (enrichissement, validation,
    motif saisi à la main).
"""
from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
from collections import defaultdict

import pandas as pd
import requests

from . import storage
from .geo import to_iso3

UA = {"User-Agent": "REG-INSIGHT/1.0 (veille conformite LCB-FT)"}
TIMEOUT = 120

SOURCES = {
    "ONU": "https://scsanctions.un.org/resources/xml/en/consolidated.xml",
    "OFAC": "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.CSV",
    "OFAC_ADD": "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/ADD.CSV",
    "OFAC_ALT": "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/ALT.CSV",
    "UE": "https://webgate.ec.europa.eu/fsd/fsf/public/files/csvFullSanctionsList_1_1/content?token=dG9rZW4tMjAxNw",
}
LINKS = {
    "ONU": "https://main.un.org/securitycouncil/fr/content/un-sc-consolidated-list",
    "OFAC": "https://sanctionssearch.ofac.treas.gov/Details.aspx?id={ref}",
    "UE": "https://www.sanctionsmap.eu/",
}

PRESERVE = ["enrichissement", "valide_admin"]


def _get(url: str) -> bytes:
    r = requests.get(url, headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    return r.content


def _join(*parts) -> str:
    return " ".join(p.strip() for p in parts if p and p.strip())


# --------------------------------------------------------------------------- ONU
def parse_un(xml_bytes: bytes) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    out = []

    def txt(node, tag):
        n = node.find(tag)
        return (n.text or "").strip() if n is not None and n.text else ""

    for kind, tag, alias_tag, addr_tag in (
        ("personne", "INDIVIDUALS/INDIVIDUAL", "INDIVIDUAL_ALIAS", "INDIVIDUAL_ADDRESS"),
        ("entité", "ENTITIES/ENTITY", "ENTITY_ALIAS", "ENTITY_ADDRESS"),
    ):
        for n in root.findall(tag):
            name = _join(txt(n, "FIRST_NAME"), txt(n, "SECOND_NAME"), txt(n, "THIRD_NAME"), txt(n, "FOURTH_NAME"))
            aliases = [txt(a, "ALIAS_NAME") for a in n.findall(alias_tag) if txt(a, "ALIAS_NAME")]
            nats = [v.text.strip() for v in n.findall("NATIONALITY/VALUE") if v.text]
            countries = [txt(a, "COUNTRY") for a in n.findall(addr_tag) if txt(a, "COUNTRY")]
            dob = []
            for d in n.findall("INDIVIDUAL_DATE_OF_BIRTH"):
                dob.append(txt(d, "DATE") or txt(d, "YEAR") or _join(txt(d, "FROM_YEAR"), txt(d, "TO_YEAR")))
            pob = [_join(txt(p, "CITY"), txt(p, "COUNTRY")) for p in n.findall("INDIVIDUAL_PLACE_OF_BIRTH")]
            docs = [f"{txt(d, 'TYPE_OF_DOCUMENT')}:{txt(d, 'NUMBER')}" for d in n.findall("INDIVIDUAL_DOCUMENT") if txt(d, "NUMBER")]
            designation = [v.text.strip() for v in n.findall("DESIGNATION/VALUE") if v.text]
            iso = to_iso3(countries[0]) if countries else (to_iso3(nats[0]) if nats else "")
            ref = txt(n, "REFERENCE_NUMBER") or txt(n, "DATAID")
            out.append({
                "id": f"ONU-{txt(n, 'DATAID')}", "regime": "ONU", "source_ref": ref,
                "nom": name, "alias": " | ".join(dict.fromkeys(aliases)), "type": kind,
                "programme": txt(n, "UN_LIST_TYPE"), "motif": txt(n, "COMMENTS1")[:1500],
                "date_designation": txt(n, "LISTED_ON"),
                "date_maj": (n.findall("LAST_DAY_UPDATED/VALUE")[-1].text or "") if n.findall("LAST_DAY_UPDATED/VALUE") else "",
                "statut": "actif", "nationalite": " | ".join(nats), "pays_iso3": iso,
                "date_naissance": " | ".join(filter(None, dob)), "lieu_naissance": " | ".join(filter(None, pob)),
                "identifiants": " | ".join(docs), "fonction": " | ".join(designation),
                "source_url": LINKS["ONU"],
            })
    return out


# -------------------------------------------------------------------------- OFAC
SDN_COLS = ["ent_num", "nom", "sdn_type", "programme", "titre", "call_sign", "vess_type",
            "tonnage", "grt", "vess_flag", "vess_owner", "remarks"]


def _clean(v):
    v = "" if v is None else str(v).strip()
    return "" if v == "-0-" else v


def parse_ofac(sdn: bytes, add: bytes | None, alt: bytes | None) -> list[dict]:
    df = pd.read_csv(io.BytesIO(sdn), header=None, names=SDN_COLS, dtype=str,
                     keep_default_na=False, encoding="latin-1", on_bad_lines="skip")
    countries = defaultdict(list)
    if add:
        a = pd.read_csv(io.BytesIO(add), header=None, dtype=str, keep_default_na=False,
                        encoding="latin-1", on_bad_lines="skip")
        for _, r in a.iterrows():
            if len(r) >= 5 and _clean(r[4]):
                countries[r[0]].append(_clean(r[4]))
    aliases = defaultdict(list)
    if alt:
        b = pd.read_csv(io.BytesIO(alt), header=None, dtype=str, keep_default_na=False,
                        encoding="latin-1", on_bad_lines="skip")
        for _, r in b.iterrows():
            if len(r) >= 4 and _clean(r[3]):
                aliases[r[0]].append(_clean(r[3]))
    type_map = {"individual": "personne", "vessel": "navire", "aircraft": "aéronef"}
    out = []
    for _, r in df.iterrows():
        rem = _clean(r["remarks"])
        dob = re.findall(r"DOB ([^;]+)", rem)
        pob = re.findall(r"POB ([^;]+)", rem)
        nat = re.findall(r"(?:nationality|Nationality) ([^;]+)", rem)
        ids = re.findall(r"((?:Passport|National ID No\.|Tax ID No\.|Registration Number|Identification Number|IMO|MMSI)[^;]*)", rem)
        designated = re.findall(r"(?:Designation Date|Listing Date)[: ]+([^;]+)", rem)
        iso = ""
        if countries.get(r["ent_num"]):
            iso = to_iso3(countries[r["ent_num"]][0])
        if not iso and nat:
            iso = to_iso3(nat[0].strip())
        if not iso and _clean(r["vess_flag"]):
            iso = to_iso3(_clean(r["vess_flag"]))
        out.append({
            "id": f"OFAC-{r['ent_num']}", "regime": "OFAC", "source_ref": r["ent_num"],
            "nom": _clean(r["nom"]), "alias": " | ".join(dict.fromkeys(aliases.get(r["ent_num"], []))),
            "type": type_map.get(_clean(r["sdn_type"]).lower(), "entité"),
            "programme": _clean(r["programme"]).strip("[]"), "motif": rem[:1500],
            "date_designation": designated[0].strip() if designated else "", "date_maj": "",
            "statut": "actif", "nationalite": " | ".join(n.strip() for n in nat), "pays_iso3": iso,
            "date_naissance": " | ".join(d.strip() for d in dob), "lieu_naissance": " | ".join(p.strip() for p in pob),
            "identifiants": " | ".join(i.strip() for i in ids), "fonction": _clean(r["titre"]),
            "source_url": LINKS["OFAC"].format(ref=r["ent_num"]),
        })
    return out


# ---------------------------------------------------------------------------- UE
def _col(row, *names):
    for n in names:
        if n in row and str(row[n]).strip():
            return str(row[n]).strip()
    return ""


def parse_eu(raw: bytes) -> list[dict]:
    df = pd.read_csv(io.BytesIO(raw), sep=";", dtype=str, keep_default_na=False,
                     encoding="utf-8-sig", on_bad_lines="skip")
    key = "Entity_LogicalId" if "Entity_LogicalId" in df.columns else df.columns[1]
    out = []
    for lid, g in df.groupby(key):
        first = g.iloc[0].to_dict()
        names = [n for n in g.get("NameAlias_WholeName", pd.Series(dtype=str)).tolist() if n]
        names = list(dict.fromkeys(names))
        cits = [c for c in g.get("Citizenship_CountryIso2Code", pd.Series(dtype=str)).tolist() if c and c != "00"]
        addr = [c for c in g.get("Address_CountryIso2Code", pd.Series(dtype=str)).tolist() if c and c != "00"]
        dobs = [d for d in g.get("BirthDate_BirthDate", pd.Series(dtype=str)).tolist() if d]
        docs = []
        if "Identification_Number" in g:
            for _, r in g.iterrows():
                if r.get("Identification_Number"):
                    docs.append(f"{r.get('Identification_TypeCode', '')}:{r['Identification_Number']}")
        functions = [f for f in g.get("NameAlias_Function", pd.Series(dtype=str)).tolist() if f]
        st = _col(first, "Entity_SubjectType", "Entity_SubjectType_ClassificationCode").lower()
        kind = "personne" if st.startswith("person") or st == "p" else "entité"
        iso = to_iso3(addr[0]) if addr else (to_iso3(cits[0]) if cits else "")
        out.append({
            "id": f"UE-{lid}", "regime": "UE", "source_ref": _col(first, "Entity_EU_ReferenceNumber") or str(lid),
            "nom": names[0] if names else "", "alias": " | ".join(names[1:]), "type": kind,
            "programme": _col(first, "Entity_Regulation_Programme"),
            "motif": _col(first, "Entity_Remark", "Entity_DesignationDetails")[:1500],
            "date_designation": _col(first, "Entity_DesignationDate", "Entity_Regulation_PublicationDate"),
            "date_maj": _col(first, "Entity_Regulation_PublicationDate"),
            "statut": "actif", "nationalite": " | ".join(dict.fromkeys(cits)), "pays_iso3": iso,
            "date_naissance": " | ".join(dict.fromkeys(dobs)), "lieu_naissance": "",
            "identifiants": " | ".join(dict.fromkeys(docs)), "fonction": " | ".join(dict.fromkeys(functions)),
            "source_url": _col(first, "Entity_Regulation_PublicationUrl") or LINKS["UE"],
        })
    return out


# ------------------------------------------------------------------------ fusion
def merge(regime: str, fresh: list[dict], user: str = "système") -> dict:
    """Fusionne une extraction fraîche dans entities.csv et journalise les écarts."""
    cur = storage.load("entities")
    old = cur[cur["regime"] == regime]
    others = cur[cur["regime"] != regime]
    new = pd.DataFrame(fresh).reindex(columns=storage.SCHEMAS["entities"]).fillna("")
    old_idx = old.set_index("id")
    added, removed = [], []
    if not new.empty:
        for c in PRESERVE:
            new[c] = new["id"].map(old_idx[c]).fillna("") if not old.empty else ""
        # motif saisi par l'admin conservé si la source n'en fournit pas
        if not old.empty:
            m = new["id"].map(old_idx["motif"]).fillna("")
            new["motif"] = new["motif"].where(new["motif"] != "", m)
    new_ids, old_ids = set(new["id"]), set(old["id"])
    ts = storage.now()
    for i in new_ids - old_ids:
        added.append(i)
    gone = old[(~old["id"].isin(new_ids)) & (old["statut"] != "radié")].copy()
    if not gone.empty:
        gone["statut"] = "radié"
        gone["date_maj"] = ts[:10]
        removed = gone["id"].tolist()
    keep_radies = old[(~old["id"].isin(new_ids)) & (old["statut"] == "radié")]
    first_load = old.empty
    final = pd.concat([others, new, gone, keep_radies], ignore_index=True)
    storage.save("entities", final)
    names = dict(zip(final["id"], final["nom"]))
    if not first_load:  # le premier chargement n'est pas un « ajout » métier
        storage.append("changes",
                       [{"date": ts, "regime": regime, "id": i, "nom": names.get(i, ""), "action": "ajout", "detail": ""} for i in added]
                       + [{"date": ts, "regime": regime, "id": i, "nom": names.get(i, ""), "action": "retrait", "detail": "absent de la source"} for i in removed])
    storage.audit(user, f"ingestion {regime}", "entities",
                  f"{len(new)} inscriptions, +{len(added) if not first_load else 0} / -{len(removed)}")
    return {"regime": regime, "total": len(new), "ajouts": 0 if first_load else len(added), "retraits": len(removed)}


def run(regimes=("ONU", "OFAC", "UE"), user: str = "système", log=print) -> list[dict]:
    results = []
    for reg in regimes:
        try:
            log(f"Téléchargement {reg}…")
            if reg == "ONU":
                rows = parse_un(_get(SOURCES["ONU"]))
            elif reg == "OFAC":
                add = alt = None
                try:
                    add = _get(SOURCES["OFAC_ADD"]); alt = _get(SOURCES["OFAC_ALT"])
                except Exception as e:  # les fichiers annexes sont facultatifs
                    log(f"OFAC annexes indisponibles : {e}")
                rows = parse_ofac(_get(SOURCES["OFAC"]), add, alt)
            elif reg == "UE":
                rows = parse_eu(_get(SOURCES["UE"]))
            else:
                continue
            if len(rows) < 50:
                raise ValueError(f"extraction anormalement courte ({len(rows)} lignes) — fusion annulée")
            res = merge(reg, rows, user)
            log(f"{reg} : {res['total']} inscriptions (+{res['ajouts']} / -{res['retraits']})")
            results.append(res)
        except Exception as e:
            storage.audit(user, f"échec ingestion {reg}", "entities", str(e))
            log(f"{reg} : échec — {e}")
            results.append({"regime": reg, "erreur": str(e)})
    return results


# --------------------------------------------------------------------- démo
def seed_demo() -> int:
    """Jeu FICTIF pour tester l'interface hors connexion (régime « DÉMO »)."""
    import random
    random.seed(7)
    pays = ["RUS", "IRN", "PRK", "SYR", "MMR", "VEN", "IRQ", "LBN", "YEM", "BLR", "CUB", "ARE", "TUR", "CHN", "HTI", "COD", "SDN", "AFG", "LBY", "NIC"]
    motifs = ["Financement du terrorisme", "Prolifération", "Contournement d'embargo",
              "Violation des droits humains", "Corruption", "Soutien à un régime sanctionné"]
    rows = []
    for i in range(60):
        iso = pays[i % len(pays)]
        kind = random.choice(["personne", "entité", "entité", "navire"])
        rows.append({
            "id": f"DEMO-{i + 1:03d}", "regime": "DÉMO", "source_ref": f"D{i + 1:03d}",
            "nom": f"[DÉMO] {'Personne' if kind == 'personne' else 'Société' if kind == 'entité' else 'Navire'} fictive {i + 1:03d}",
            "alias": "", "type": kind, "programme": "Jeu de test", "motif": random.choice(motifs),
            "date_designation": f"2026-{random.randint(1, 9):02d}-{random.randint(1, 28):02d}",
            "date_maj": "", "statut": "actif", "nationalite": iso if kind == "personne" else "",
            "pays_iso3": iso, "date_naissance": f"19{random.randint(50, 95)}-0{random.randint(1, 9)}-1{random.randint(0, 9)}" if kind == "personne" else "",
            "lieu_naissance": "", "identifiants": f"INN:{random.randint(10**11, 10**12 - 1)}" if iso == "RUS" and kind == "personne" else "",
            "fonction": "", "source_url": "", "enrichissement": "Donnée fictive", "valide_admin": "",
        })
    cur = storage.load("entities")
    cur = cur[cur["regime"] != "DÉMO"]
    storage.save("entities", pd.concat([cur, pd.DataFrame(rows)], ignore_index=True))
    return len(rows)
