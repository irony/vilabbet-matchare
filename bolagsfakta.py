"""Bolagsfaktasteget: identifiera juridisk enhet och hämta hårda fakta.

Flöde:
1. Leta org.nr (55xxxx-xxxx) i råmaterialet — föredrar träffar nära bolagsnamnet
2. Scrape allabolag.se/<orgnr> -> anställda, omsättning, balans, grundat
   (LLM-extrahering om regex inte räcker)
3. Uppdatera ramaterial med bolagsdatasidan (så faktasöket kan citera den)
4. Skriv/uppdatera profiler/<tag>_party.json med verifierade siffror

Användning:
  python3 bolagsfakta.py --tag bolag [--orgnr 556000-0000] [--solo]
"""
import argparse
import json
import os
import re
import time
import urllib.request

from vilabbet_client import chat

HERE = os.path.dirname(os.path.abspath(__file__))
KEY = os.environ.get("BERGET_API_KEY", "").strip()
ORGNR_PAT = re.compile(r"\b(55\d{4}-\d{4})\b")


def scrape(url, only_main=False):
    req = urllib.request.Request(
        "https://api.berget.ai/v1/firecrawl/scrape",
        data=json.dumps({"url": url, "formats": ["markdown"],
                         "onlyMainContent": only_main}).encode(),
        headers={"Authorization": f"Bearer {KEY}",
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return (json.loads(r.read().decode()).get("data") or {}).get("markdown") or ""


def hitta_orgnr(pages, bolagsnamn):
    """Score:a org.nr-träffar: +2 om bolagsnamnet nämns inom 300 tecken."""
    kandidater = {}
    for p in pages:
        md = p["markdown"]
        for m in ORGNR_PAT.finditer(md):
            orgnr = m.group(1)
            kontext = md[max(0, m.start() - 300):m.end() + 300].lower()
            poang = 1 + (2 if bolagsnamn.lower().split()[0] in kontext else 0)
            kandidater[orgnr] = max(kandidater.get(orgnr, 0), poang)
    if not kandidater:
        return None, {}
    bast = max(kandidater.items(), key=lambda kv: kv[1])
    return bast[0], kandidater


def llm_extrahera(md, orgnr):
    user = f"""Extrahera bolagsfakta ur denna allabolag.se-text för org.nr {orgnr}.
Svara ENBART med JSON: {{"namn": str|null, "anstallda": int|null,
"grundat": int|null (år), "omsattning_tkr": int|null (senaste år),
"balans_tkr": int|null, "snittsiffror": bool (true om siffrorna är bransch-SNI-snitt, inte bolagets)}}

TEXT:
{md[:12000]}"""
    content, _ = chat([{"role": "user",
                        "content": user}], model="default", max_tokens=400,
                      temperature=0.0)
    try:
        return json.loads(content[content.index("{"):content.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError):
        return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--orgnr", help="Hoppa över identifieringen, använd detta org.nr")
    ap.add_argument("--solo", action="store_true",
                    help="droppa den generiska konsortiepartnern ur party.json")
    args = ap.parse_args()
    tag = args.tag

    if not KEY:
        raise SystemExit("BERGET_API_KEY saknas i env")

    raw_path = os.path.join(HERE, "profiler", f"{tag}_ramaterial.json")
    raw = json.load(open(raw_path))
    bolagsnamn = raw.get("company", tag)

    orgnr = args.orgnr
    if not orgnr:
        orgnr, alla = hitta_orgnr(raw["pages"], bolagsnamn)
        print(f"Org.nr-kandidater i textmassan: {alla or 'inga'}")

    if not orgnr:
        # Fallback: vanliga legal-sluggar på samma domän (org.nr bor i
        # footer/policyer som profilskrapet hoppar över)
        base = raw.get("base_url", "").rstrip("/")
        for slug in ("/en/dpa", "/en/terms", "/dpa", "/terms", "/privacy",
                     "/integritetspolicy", "/var-integritetspolicy",
                     "/om-oss", "/about", "/kontakt", "/contact"):
            url = base + slug
            try:
                md = scrape(url)
            except Exception:  # noqa: BLE001
                continue
            hits = ORGNR_PAT.findall(md)
            if hits:
                kandidater = {}
                for m in ORGNR_PAT.finditer(md):
                    kontext = md[max(0, m.start() - 300):m.end() + 300].lower()
                    poang = 1 + (2 if bolagsnamn.lower().split()[0] in kontext else 0)
                    kandidater[m.group(1)] = max(
                        kandidater.get(m.group(1), 0), poang)
                orgnr = max(kandidater.items(), key=lambda kv: kv[1])[0]
                print(f"Org.nr hittat via {url}: {orgnr} "
                      f"(kandidater: {kandidater})")
                raw["pages"].append({"url": url, "markdown": md})
                break

    if not orgnr:
        raise SystemExit(
            f"Kunde inte identifiera juridisk enhet för {bolagsnamn}. "
            f"Kör om med --orgnr 55xxxx-xxxx")
    print(f"Identifierad: org.nr {orgnr} ({bolagsnamn})")

    print("Skrapar allabolag.se ...")
    facts = {}
    md = ""
    orgnr_nodash = orgnr.replace("-", "")
    url = f"https://www.allabolag.se/{orgnr_nodash}"
    try:
        md = scrape(url, only_main=False)
        # Försök även bokslut/nyckeltal-undersidor för siffrorna
        for under in ("/bokslut", "/nyckeltal"):
            try:
                md2 = scrape(url + under, only_main=False)
                if md2 and "Å nej" not in md2:
                    md += "\n\n--- UNDERSIDA " + under + " ---\n\n" + md2
            except Exception:  # noqa: BLE001
                pass
    except Exception as e:  # noqa: BLE001
        print(f"  allabolag misslyckades: {str(e)[:150]}")
    if md and len(md) > 800 and "Å nej" not in md:
        facts = llm_extrahera(md, orgnr)
        print(f"  allabolag-fakta: {facts}")
    else:
        md = ""
        print(f"  otillräckligt svar — allabolag hittade inte sidan")

    # Uppdatera råmaterialet med bolagsdatasidan (för faktasökets citat)
    if md:
        if not any(p["url"] == url for p in raw["pages"]):
            raw["pages"].append({"url": url, "markdown": md})
        raw["orgnr"] = orgnr
        json.dump(raw, open(raw_path, "w"), ensure_ascii=False, indent=1)
        print(f"  råmaterialet berikat: {raw_path}")

    # Skriv party.json
    anstallda = facts.get("anstallda")
    oms = facts.get("omsattning_tkr")
    balans = facts.get("balans_tkr")
    grundat = facts.get("grundat")
    juridiskt_namn = facts.get("namn") or bolagsnamn

    party = {
        "name": juridiskt_namn,
        "legal_form": "limited_company",
        "registration_country": "SE",
        "operations_in_sweden": True,
        "is_research_organisation": False,
    }
    if anstallda is not None:
        party["employees"] = anstallda
    if grundat is not None:
        party["founded"] = grundat
    if oms is not None and not facts.get("snittsiffror"):
        party["turnover_ksek"] = oms
    if balans is not None and not facts.get("snittsiffror"):
        party["balance_sheet_total_ksek"] = balans

    parties = [party]
    if not args.solo:
        parties.append({
            "name": "Eventuell partner (behovsägare)",
            "legal_form": "limited_company",
            "registration_country": "SE",
            "operations_in_sweden": True,
            "employees": 400,
            "is_needs_owner": True,
        })
    saknas = [f for f in ("employees", "turnover_ksek") if f not in party]
    out = {
        "_comment": (f"Verifierade fakta från allabolag.se/{orgnr} "
                     f"(hamtade {time.strftime('%Y-%m-%d')}). "
                     + (f"SAKNAS fortfarande: {', '.join(saknas)}. " if saknas else "")
                     + "Belopp/datum utelamnas avsiktligt."),
        "orgnr": orgnr,
        "kalla": f"https://www.allabolag.se/{orgnr}",
        "payload": {"parties": parties},
    }
    ppath = os.path.join(HERE, "profiler", f"{tag}_party.json")
    json.dump(out, open(ppath, "w"), ensure_ascii=False, indent=1)
    print(f"party.json skriven: {ppath}")
    print(json.dumps(parties, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
