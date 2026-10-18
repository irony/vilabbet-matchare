"""Kärnlogik för demon — pipelinen som återanvändbara funktioner.

Flöde: scrape_company -> match_rounds (bara framtida/öppna) -> fetch_requirements
-> fact_find -> build_krav_doc + build_application_doc.
"""
import json
import os
import re
import time
import urllib.request

from concurrent.futures import ThreadPoolExecutor

from vilabbet_client import api_get, api_post, chat, cosine, embed

HERE = os.path.dirname(os.path.abspath(__file__))
FIRECRAWL = "https://api.berget.ai/v1/firecrawl"
BERGET_KEY = os.environ.get("BERGET_API_KEY", "").strip()

PRIO_PAT = re.compile(
    r"($|/(om|about|om-oss|who-we-are|company|bolaget|produkter?|products?|"
    r"tjanster|tjänster|services|erbjudande|offer|losningar|lösningar|solutions|"
    r"case|kunder|customers|branscher|industries|teknik|tech|plattform|platform|"
    r"ai|varfor|varför|why|karriar|career|jobb))", re.IGNORECASE)
SKIP_PAT = re.compile(
    r"(blogg|blog|nyhet|news|press|artikel|article|pod|event|webinar|"
    r"integritet|privacy|cookie|gdpr|terms|villkor|legal|login|signup|"
    r"kontakt|contact|tag/|category/|author/|\.(pdf|jpg|png|zip)$)",
    re.IGNORECASE)

MAX_PAGES = 8
MAX_MD_PER_PAGE = 9000

ORGNR_PAT = re.compile(r"\b(55\d{4}-\d{4})\b")

KOSTTAK_PAT = re.compile(r"(maximalt bidrag|maximal ansökan|högst \d|stödnivå|"
                         r"stodniva|får motsvara|procent av)", re.IGNORECASE)
KRAVTYPER = {"eligibility", "formal", "time", "co_financing"}


def _tell(cb, msg, item=None):
    if cb:
        cb(msg)
        if item is not None:
            cb(item)          # strukturerat "bevis" för skärmsläckaren
    print(f"  [demo] {msg}")


def _first_line(md):
    for line in (md or "").splitlines():
        line = line.strip().strip("#>*- ")
        if len(line) > 25:
            return line[:110]
    return ""


def _fc(endpoint, payload, timeout=120):
    req = urllib.request.Request(
        f"{FIRECRAWL}/{endpoint}", data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {BERGET_KEY}",
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


# ---------------------------------------------------------------- scrape

def scrape_company(url, name=None, progress=None):
    base = url.rstrip("/")
    m = re.match(r"^https?://(www\.)?([^/]+)", base)
    dom = m.group(2)
    name = name or dom.split(".")[0].capitalize()

    _tell(progress, "Kartlägger webbplatsen …")
    urls = [base]
    try:
        r = _fc("map", {"url": base, "limit": 400})
        found = r.get("links") or (r.get("data") or {}).get("links") or []
        urls += [u.get("url") if isinstance(u, dict) else u for u in found]
    except Exception as e:  # noqa: BLE001
        _tell(progress, f"Kartläggning misslyckades ({e}) — fortsätter med startsidan")

    picked, seen = [], set()
    for u in urls:
        if not u or u in seen or SKIP_PAT.search(u):
            continue
        seen.add(u)
        if u.rstrip("/") == base or PRIO_PAT.search(u.replace(base, "")):
            picked.append(u)
    picked = picked[:MAX_PAGES]

    # fallback för SPA-sajter utan sitemap (t.ex. Next.js-appar där map
    # bara hittar förstasidan): bredd-först länkkrawl via firecrawls
    # scrape med links-format — renderas i proxyns headless-browser.
    if len(picked) < 6:
        _tell(progress, f"Karta gav bara {len(urls)} sidor — länkkrawl "
                        f"från förstasidan …")
        seen.add(base)
        frontier = [base]
        puls = 0

        def _länkar(u):
            try:
                r = _fc("scrape", {"url": u, "formats": ["markdown", "links"],
                                   "onlyMainContent": True})
                return r.get("data") or {}
            except Exception:  # noqa: BLE001
                return {}

        while len(picked) < MAX_PAGES and frontier and puls < 6:
            puls += 1
            batch, frontier = frontier, []
            with ThreadPoolExecutor(max_workers=3) as pool:
                for d in pool.map(_länkar, batch):
                    for l in (d.get("links") or []):
                        l = l.split("#")[0].rstrip("/")
                        if (l.startswith(base) and l not in seen
                                and not SKIP_PAT.search(l)):
                            seen.add(l)
                            picked.append(l)
                            frontier.append(l)
        picked = picked[:MAX_PAGES]
        _tell(progress, f"Länkkrawl samlar {len(picked)} sidor")

    _tell(progress, f"Hittade {len(urls)} sidor — skrapar {len(picked)} av dem")

    pages: list[dict] = [None] * len(picked)  # type: ignore[list-item]

    def _skrapa_en(iu):
        i, u = iu
        try:
            r = _fc("scrape", {"url": u, "formats": ["markdown"],
                               "onlyMainContent": True})
            md = (r.get("data") or {}).get("markdown") or ""
        except Exception as e:  # noqa: BLE001
            md = ""
            _tell(progress, f"  kunde inte skrapa {u}: {str(e)[:80]}")
        if md:
            pages[i] = {"url": u, "markdown": md[:MAX_MD_PER_PAGE]}
            _tell(progress, f"  ✓ {u.split(dom)[-1] or u} ({len(md)} tecken)",
                  {"kind": "page", "title": u.replace(base, "") or "/",
                   "sub": _first_line(md), "n": len(md)})

    _tell(progress, f"Skrapar {len(picked)} sidor parallellt (4 trådar) …")
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(_skrapa_en, enumerate(picked)))
    pages = [p for p in pages if p]
    if not pages:
        raise RuntimeError("Kunde inte skrapa någon sida från webbplatsen")

    _tell(progress, "Sammanfattar bolagsprofil …")
    material = "\n\n".join(f"### {p['url']}\n{p['markdown']}" for p in pages)
    system = """Du skapar en företagsprofil som ska användas för att matcha bolaget
mot svenska innovationsutlysningar (Vinnova m.fl.). Skriv på svenska i exakt
denna struktur:

<BOLAGSNAMN>

<1-2 meningar: vad bolaget gör, grundat år om det framgår, storlek om det framgår>

Produkter och teknik:
- <punktlista>

Differentiering och värdeerbjudande:
- <punktlista>

Kunder: <branscher och kundtyper>

Kompetens: <nyckelkompetenser, kommaseparerat>

Vi söker samarbeten kring: <3-6 teman härledda ur erbjudandet>

Skriv endast sådant som stöds av källmaterialet. 200-350 ord."""
    profil, _ = chat([{"role": "system", "content": system},
                      {"role": "user", "content":
                       f"Bolag: {name} ({base})\n\nSKRAPAT MATERIAL:\n{material}"}],
                     model="default", max_tokens=1200, temperature=0.2)
    return {"company": name, "base_url": base, "pages": pages,
            "profil": profil.strip()}


def bolagsfakta_from_sites(company_data, orgnr=None, progress=None):
    """Försök hitta org.nr i materialet; skrapa allabolag för hårda fakta."""
    pages = company_data["pages"]
    kandidater = {}
    if not orgnr:
        namn_del = company_data["company"].lower().split()[0]
        for p in pages:
            for m in ORGNR_PAT.finditer(p["markdown"]):
                kontext = p["markdown"][max(0, m.start() - 300):m.end() + 300].lower()
                rad = p["markdown"][p["markdown"].rfind("\n", 0, m.start()):
                                    p["markdown"].find("\n", m.end())].lower()
                poang = 1 + (2 if namn_del in kontext else 0) + (3 if namn_del in rad else 0)
                kandidater[m.group(1)] = max(kandidater.get(m.group(1), 0), poang)
        if kandidater:
            orgnr = max(kandidater.items(), key=lambda kv: kv[1])[0]
            _tell(progress, f"Hittade org.nr i materialet: {orgnr}")
    if not orgnr:
        return None

    # 1) verifiera/enrich:a mot Bolagsverkets officiella register (lokal kopia)
    reg = None
    try:
        import foretagsregister
        reg = foretagsregister.lookup(orgnr)
        if reg:
            _tell(progress,
                  f"✓ {reg['namn']} — grundat {reg['grundat_ar']}, {reg['form']}, "
                  f"{'i likvidation/rekonstruktion!' if reg['likvidation_eller_rekonstruktion'] else 'aktiv'} {reg['ort']}",
                  {"kind": "bolagsreg",
                   "title": f"⚖️ {reg['namn']}",
                   "sub": f"grundat {reg['grundat_ar']} · {reg['form']} · {reg['ort']}"})
        else:
            # orgnr missar registret? kan vara felaktig orgnr på sajten
            for kand in sorted(kandidater, key=lambda k: -kandidater[k]):
                alt = foretagsregister.lookup(kand)
                if alt:
                    _tell(progress,
                          f"Org.nr {orgnr} saknas i registret — byter till {kand} "
                          f"({alt['namn']})")
                    orgnr = kand
                    reg = alt
                    break
            if not reg:
                _tell(progress, "Org.nr saknas i Bolagsverkets register — litar på allabolag")
    except Exception:  # noqa: BLE001
        reg = None

    _tell(progress, f"Hämtar bolagsfakta för {orgnr} …")
    url = f"https://www.allabolag.se/{orgnr.replace('-', '')}"
    try:
        r = _fc("scrape", {"url": url, "formats": ["markdown"],
                           "onlyMainContent": False})
        md = (r.get("data") or {}).get("markdown") or ""
        if "Å nej" in md:
            md = ""
    except Exception:  # noqa: BLE001
        md = ""
    if not md:
        return None
    pages.append({"url": url, "markdown": md})
    user = f"""Extrahera bolagsfakta ur denna allabolag.se-text för org.nr {orgnr}.
Svara ENBART med JSON: {{"namn": str|null, "anstallda": int|null,
"grundat": int|null, "omsattning_tkr": int|null, "balans_tkr": int|null,
"snittsiffror": bool}}

TEXT:
{md[:12000]}"""
    content, _ = chat([{"role": "user", "content": user}],
                      model="default", max_tokens=400, temperature=0.0)
    try:
        facts = json.loads(content[content.index("{"):content.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError):
        facts = {}
    party = {"name": facts.get("namn") or company_data["company"],
             "legal_form": "limited_company", "registration_country": "SE",
             "operations_in_sweden": True, "is_research_organisation": False}
    if facts.get("anstallda") is not None:
        party["employees"] = facts["anstallda"]
    if facts.get("grundat") is not None:
        party["founded"] = facts["grundat"]
    if facts.get("omsattning_tkr") is not None and not facts.get("snittsiffror"):
        party["turnover_ksek"] = facts["omsattning_tkr"]
    if facts.get("balans_tkr") is not None and not facts.get("snittsiffror"):
        party["balance_sheet_total_ksek"] = facts["balans_tkr"]
    # officiellt register tar precedens på juridiska fält
    if reg:
        party["name"] = reg["namn"]
        if reg.get("grundat_ar"):
            party["founded"] = reg["grundat_ar"]
    _tell(progress, f"Bolagsfakta: {party}")
    return {"orgnr": orgnr,
            "kalla": "Bolagsverket + allabolag" if reg else url,
            "party": party, "registret": reg}


# ---------------------------------------------------------------- matchning

def _caches():
    rounds = json.load(open(os.path.join(HERE, "cache", "rounds_list.json")))
    details = json.load(open(os.path.join(HERE, "cache", "rounds_detail.json")))
    emb = json.load(open(os.path.join(HERE, "cache", "embeddings.json")))
    return rounds, details, emb


def match_rounds(profil, max_results=15, progress=None, model="default"):
    rounds, details, emb_cache = _caches()
    _tell(progress, "Embeddar bolagsprofilen …")
    pvec = embed([profil])[0]

    _tell(progress, f"Matchar mot {len(rounds)} omgångar …")
    sims = []
    for r in rounds:
        c = emb_cache.get(r["dnr"])
        if not c:
            continue
        st = (details.get(r["dnr"]) or {}).get("status") or r.get("status") or {}
        framtida = st.get("can_apply_now") or r.get("state") in ("open", "upcoming")
        if not framtida:
            continue
        sims.append({
            "dnr": r["dnr"], "title": r["title"],
            "funder": r.get("funder"), "state": r.get("state"),
            "closing_date": r.get("closing_date"),
            "can_apply_now": bool(st.get("can_apply_now")),
            "similarity": cosine(pvec, c["vec"]),
            "warnings": st.get("warnings", []),
        })
    sims.sort(key=lambda x: -x["similarity"])
    # embeddings är bara en grovsil — LLM:en ger den egaentliga bedömningen
    kandidater = sims[:max(40, max_results * 3)]
    _tell(progress, f"{len(sims)} framtida/öppna omgångar hittade — "
                    f"bedömer {len(kandidater)} med AI …")

    if kandidater:
        block = "\n".join(
            f"{v['dnr']}: {v['title']}\nVEM: {((details.get(v['dnr']) or {}).get('who') or {}).get('sv', '-')}"
            f"\nVAD: {((details.get(v['dnr']) or {}).get('what') or {}).get('sv', '-')[:300]}"
            for v in kandidater)
        user = f"""BOLAGSPROFIL:
{profil[:1800]}

Bedöm VARJE ansökningsomgångs passform för bolaget med utgångspunkt i VEM och
VAD — ärligt, gissa inte:
- "passform": "bra" (tydligt överlapp i tema/teknik OCH målgrupp),
  "mojlig" (möjlig med anpassad ansats), "dalig" (bolaget passar inte
  syftet/målgruppen), "ej_bedombar" (för lite info).
- "poang": heltal 0–100 (samlad bedömning av passform).
- "varfor": max 15 ord, rakt besked.
Svara ENBART med JSON-lista:
[{{"dnr": "...", "passform": "...", "poang": 0, "varfor": "..."}}, ...]

{block}"""
        content, _ = chat([{"role": "user", "content": user}],
                          model=model, max_tokens=3000, temperature=0.2)
        try:
            b = json.loads(content[content.index("["):content.rindex("]") + 1])
            bed = {x.get("dnr"): x for x in b if isinstance(x, dict)}
        except (ValueError, json.JSONDecodeError):
            bed = {}
        for v in kandidater:
            x = bed.get(v["dnr"], {})
            v["passform"] = x.get("passform", "")
            v["matchpoang"] = x.get("poang")
            v["varfor"] = x.get("varfor", "")

    kandidater.sort(key=lambda x: -(x.get("matchpoang") or -1))
    valda = [v for v in kandidater if v.get("matchpoang") is not None][:max_results]
    for v in valda[:8]:
        _tell(progress, f"  {v['matchpoang']} %: {v['title'][:60]}",
              {"kind": "match", "title": v["title"][:70],
               "sub": f"{v['matchpoang']} % · {v.get('passform') or ''} · "
                      f"stänger {str(v.get('closing_date'))[:10]}"})
    _tell(progress, f"visar topp {len(valda)} efter AI-bedömning")
    return valda


# ---------------------------------------------------------------- krav

def fetch_requirements(dnr):
    reqs = api_get(f"/v1/rounds/{dnr}/requirements").get("data", {})
    if isinstance(reqs, dict):
        reqs = reqs.get("requirements", reqs)
    valda = [r for r in reqs
             if r.get("type") in KRAVTYPER
             or (r.get("type") == "cost" and KOSTTAK_PAT.search(r.get("text") or ""))]
    return reqs, valda


FAKTASYSTEM = """Du är en noggrann faktakontrollant. Du får krav från en svensk
innovationsutlysning och skrapad text från ett företags webbplats.

För VARJE krav: avgör om textmaterialet innehåller fakta som besvarar det.
Svara ENBART utifrån materialet — gissa aldrig.

Statusvärden:
- "styrkt_uppfyllt": materialet visar att kravet är uppfyllt. Ange kort citat.
- "styrkt_ej_uppfyllt": materialet visar att kravet INTE uppfylls. Ange citat.
- "okant": materialet saknar relevant fakta.
- "strukturellt": kravet gäller ansökans/projektets upplägg (konsortium,
  projektplan, underskrifter, budget) — inget bolagsfaktum.

Svara med ENBART en JSON-lista, ett objekt per krav, samma ordning:
{"requirement_id": "...", "status": "...", "fakta": "citat eller fynd, annars null",
 "kommentar": "max 1 mening eller null"}"""


def _korta(text, n=200):
    text = re.sub(r"\s+", " ", (text or "").strip())
    return text if len(text) <= n else text[:n - 1] + "…"


def fact_find(profil, material, dnr, valda_krav, progress=None, model="default"):
    svar = []
    BATCH = 40
    ordinal = {r["requirement_id"]: n + 1
               for n, r in enumerate(valda_krav)}

    def _kör_batch(i0: int):
        batch = valda_krav[i0:i0 + BATCH]
        _tell(progress,
              f"  krav {i0 + 1}–{min(i0 + BATCH, len(valda_krav))} "
              f"av {len(valda_krav)}")
        kravlista = "\n".join(
            f'{r["requirement_id"]} [{r.get("type")}]: {_korta(r.get("text"))}'
            for r in batch)
        user = f"""BOLAGSPROFIL:
{profil[:2000]}

SKRAPAT MATERIAL FRÅN BOLAGETS WEBBPLATS OCH BOLAGSREGISTER:
{material[:24000]}

KRAV ATT BESVARA ({len(batch)} st, omgång {dnr}):
{kravlista}"""
        content, usage = chat([{"role": "system", "content": FAKTASYSTEM},
                               {"role": "user", "content": user}],
                              model=model, max_tokens=6000, temperature=0.0)
        try:
            parsed = json.loads(content[content.index("["):
                                        content.rindex("]") + 1])
            by_req = {r["requirement_id"]: r for r in batch}
            for s in parsed:
                req = by_req.get(s.get("requirement_id"), {})
                _tell(progress, f"  [{s.get('status')}] {_korta(req.get('text'), 60)}",
                      {"kind": "req", "status": s.get("status", "okant"),
                       "id": s.get("requirement_id"), "dnr": dnr,
                       "n": ordinal.get(s.get("requirement_id")),
                       "title": _korta(req.get("text"), 95),
                       "sub": _korta(s.get("fakta") or s.get("kommentar")
                                     or f"typ: {req.get('type')}", 90)})
            return parsed
        except (ValueError, json.JSONDecodeError):
            return []

    batch_starts = list(range(0, len(valda_krav), BATCH))
    if len(batch_starts) > 1:
        _tell(progress, f"  kör {len(batch_starts)} kravbatchar parallellt "
                        f"(3 trådar) för {dnr}")
    with ThreadPoolExecutor(max_workers=3) as pool:
        for parsed in pool.map(_kör_batch, batch_starts):
            svar.extend(parsed)
    by_id = {s.get("requirement_id"): s for s in svar}
    ut = []
    for r in valda_krav:
        s = by_id.get(r["requirement_id"], {})
        prov = r.get("provenance") or {}
        ut.append({
            "requirement_id": r["requirement_id"],
            "type": r.get("type"), "mandatory": r.get("mandatory"),
            "checkable": r.get("checkable"), "text": r.get("text"),
            "status": s.get("status", "okant"),
            "fakta": s.get("fakta"), "kommentar": s.get("kommentar"),
            "prov_terms_id": prov.get("terms_id"),
            "prov_anchor": prov.get("anchor") or (prov.get("trace") or {}).get("anchor"),
            "prov_quote": _korta(prov.get("quote"), 260),
        })
    return ut


def motor_check(dnr, party, progress=None):
    """Kör officiella eligibility-checken om vi har bolagsfakta."""
    if not party:
        return None
    parties = [party, {
        "name": "Eventuell partner (behovsägare)",
        "legal_form": "limited_company", "registration_country": "SE",
        "operations_in_sweden": True, "employees": 400, "is_needs_owner": True}]
    try:
        d = api_post("/v1/eligibility/check",
                     {"round_dnr": dnr, "parties": parties}).get("data", {})
        return {k: d.get(k) for k in ("eligible", "automatic_count",
                                      "not_met_count", "needs_review_count",
                                      "explanation")}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:200]}


def hämta_kravobj(dnr, progress=None):
    """Hämta rundinfo + relevanta krav — ingen LLM, bara korpus-API:t."""
    rounds = json.load(open(os.path.join(HERE, "cache", "rounds_list.json")))
    meta = next((r for r in rounds if r["dnr"] == dnr), {})
    d = api_get(f"/v1/rounds/{dnr}").get("data", {})
    alla, valda = fetch_requirements(dnr)
    title = d.get("title") or meta.get("title", dnr)
    _tell(progress, f"  {dnr}: {len(valda)} av {len(alla)} krav relevanta",
          {"kind": "kravlista",
           "title": f"{len(valda)} relevanta krav identifierade",
           "sub": _korta(title, 70)})
    return {
        "dnr": dnr, "title": title,
        "closing_date": d.get("closing_date") or meta.get("closing_date"),
        "state": d.get("state") or meta.get("state"),
        "funder": d.get("funder") or meta.get("funder"),
        "source_url": meta.get("source_url"),
        "n_krav_totalt": len(alla),
        "krav_objekt": [{"requirement_id": r.get("requirement_id"),
                         "type": r.get("type"),
                         "text": r.get("text")} for r in valda],
    }


def analysera(company_data, bolagsfakta, dnr, progress=None, model="default",
              prefetched=None):
    rounds = json.load(open(os.path.join(HERE, "cache", "rounds_list.json")))
    meta = next((r for r in rounds if r["dnr"] == dnr), {})
    d = api_get(f"/v1/rounds/{dnr}").get("data", {})
    if prefetched:
        valda, antal_totalt = prefetched["krav_objekt"], prefetched["n_krav_totalt"]
    else:
        alla, valda = fetch_requirements(dnr)
        antal_totalt = len(alla)
    _tell(progress, f"letar bevis för {len(valda)} krav (av {antal_totalt} i korpuset)")
    material = "\n\n".join(f"[{p['url']}]\n{p['markdown']}" for p in company_data["pages"])
    krav = fact_find(company_data["profil"], material, dnr, valda,
                     progress=progress, model=model)
    stats = {}
    for k in krav:
        stats[k["status"]] = stats.get(k["status"], 0) + 1
    motor = None
    if bolagsfakta:
        _tell(progress, "Kör officiella regelmotorn …")
        motor = motor_check(dnr, bolagsfakta.get("party"))
        if motor:
            _tell(progress,
                  f"  motor: eligible={motor.get('eligible')}",
                  {"kind": "motor",
                   "title": f"Regelmotor: eligible={motor.get('eligible')}",
                   "sub": _korta(motor.get("explanation"), 110)})
    return {
        "dnr": dnr,
        "title": d.get("title") or meta.get("title", dnr),
        "funder": d.get("funder"), "who": (d.get("who") or {}).get("sv"),
        "closing_date": d.get("closing_date"),
        "state": d.get("state"), "status": d.get("status"),
        "source_url": meta.get("source_url")
        or (f"https://www.vinnova.se/ao/{dnr}" if not dnr.startswith(("vr", "formas")) else ""),
        "n_krav_totalt": antal_totalt, "krav": krav, "stats": stats,
                                            "motor": motor,
    }


ÄMNESREGLER = [
    ("Regler, etik & strategi",
      ["etisk", "forskningsed", "gdpr", "lagar och regler", "statligt stöd",
       "eu:s", "europeiska unionen"]),
    ("Ordnad administration & register",
      ["luf", "ordnad löpande redovisning", "löpande bokföring", "skatteverket",
       "arbetsgivare", "likvidation", "rekonstruktion", "kronofogde",
       "obestånd", "bokföring"]),
    ("Bidrag & budget",
      ["bidrag", "stöd", "budget", "kostnad", "avskrivning", "finansiär",
       "medfinansiering", "belopp", " kronor"]),
    ("Storlek & ekonomi",
      ["anställd", "årsarbetskraft", "omsättning", "balans", "vinstutdelning",
       "aktiekapital", "mkr", "nettoomsättning"]),
    ("Bolag & ägarskap",
      ["aktiebolag", "koncern", "börsnoterad", "fusion", "övertagande",
       "juridisk", "aktieägare", "svensk", "sverige", "bolag"]),
    ("Projekt & organisation",
      ["projektavtal", "koordinator", "projektledare", "projekttid",
       "godkännande", "projektparts", "arbetspaket", "projekt"]),
]
ÄMNESORDNING = [a for a, _ in ÄMNESREGLER] + ["Övrigt"]


def ämnesgrupp(text):
    t = " " + (text or "").lower()
    for namn, nycklar in ÄMNESREGLER:
        if any(k in t for k in nycklar):
            return namn
    return "Övrigt"


def gruppera_krav(kravobj_list, tröskel=0.94, model="embedding"):
    """Slå ihop snarlika krav över (och inom) omgångar med embeddings +
    union–find-klustring. Returnerar ämnessorterade grupper."""
    alla = []
    for ko in kravobj_list:
        for r in ko["krav_objekt"]:
            alla.append({"dnr": ko["dnr"], **r})
    if not alla:
        return []
    vecs = embed([(r.get("text") or "")[:300] for r in alla], model=model)
    n = len(alla)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(n):
        for j in range(i + 1, n):
            if cosine(vecs[i], vecs[j]) >= tröskel:
                parent[find(i)] = find(j)
    by = {}
    for i in range(n):
        by.setdefault(find(i), []).append(i)
    grupper = []
    for idxs in by.values():
        inst = [alla[i] for i in idxs]
        rep = max(inst, key=lambda r: len(r.get("text") or ""))
        grupper.append({
            "text": rep.get("text"),
            "amne": ämnesgrupp(rep.get("text")),
            "dnrs": sorted({i["dnr"] for i in inst}),
            "forekomster": [{"dnr": i["dnr"], "id": i["requirement_id"],
                             "type": i.get("type"),
                             "text": _korta(i.get("text"), 160)}
                            for i in inst],
        })
    return sorted(grupper,
                  key=lambda g: (ÄMNESORDNING.index(g["amne"]),
                                 -len(g["forekomster"])))


STATUS_TEXT = {"styrkt_uppfyllt": "Styrkt uppfyllt",
               "styrkt_ej_uppfyllt": "Styrkt ej uppfyllt",
               "okant": "Okänt — att komplettera",
               "strukturellt": "Strukturkrav"}

# --------------------------------------------------- färska-ögon-granskning
# Granskaren läser UTKASTET mot UTLYSNINGEN — inget från bolagswebben används,
# bara utlysningens villkor och kravmatrisens status. Det är avsikten:
# granskningen ska vara bolagsblind, som en extern utvärderare.

GRANSKA_VIKT = {"blockerare": 0, "viktigt": 1, "förslag": 2}


# ---------------------------------------------------------------------------
# Gap-stöd: andra varvet mot hemsidan för varje gappunkt
# ---------------------------------------------------------------------------

_GAPTEMAS = [
    # (nyckelord i punkt-text, url-hintar, etikett)
    (("konsorti", "partner", "juridisk person", "annat företag",
      "annan organisation", "samarbet", "tväräg", "innovationspartner"),
     ("case", "kunder", "referens", "samarbet", "projekt", "uppdrag"),
     "kund- och samarbetscase"),
    (("cv", "medarbetare", "team", "komp", "person", "organisation",
      "sammansätt", "erfarenhet som ska med"),
     ("om-oss", "team", "medarbetare", "about", "karriar", "folk",
      "ledning", "vi-ar", "vara-radgivare", "konsult"),
     "personer och kompetens"),
    (("budget", "belopp", "kostnad", "finansi", "prissnivå", "omsätt",
      "stödnivå"),
     ("pris", "erbjud", "produkt", "arbeten", "sektor", "om-oss"),
     "siffror och bakgrund"),
    (("problem", "sektor", "användningsfall", "målgrupp", "bränsle",
      "sjukvård", "energi", "transport", "försvar", "finans", "välfärd"),
     ("case", "kunder", "branscher", "sektorer", "losning", "tjanst",
      "omrade"),
     "användningsfall/bransch"),
]


def _gap_välj_sidor(punkt: dict, pages: list, max_sidor: int = 3) -> list:
    """Välj de mest sannolika sidorna för just den här gap-punkten:
    tema-hintar på URL + ordöverlappnedgång i sidtexten."""
    text = f"{punkt.get('beskrivning') or ''} {punkt.get('atgard') or ''}".lower()
    trähintar, tema = [], ""
    for ordar, hintar, etikett in _GAPTEMAS:
        if any(o in text for o in ordar):
            trähintar.extend(hintar)
            tema = etikett
            break
    stop = {"som", "och", "för", "med", "inte", "detta", "avsnitt", "ska",
            "the", "den", "att", "är", "har", "från", "omfatt", "projekt",
            "utkast", "ansökan", "bolaget", "saknas", "ange", "exakt",
            "konkret", "behöver", "måste", "text", "formulär", "uppfyll"}
    ord = {w for w in re.findall(r"[a-zåäö]{5,}", text) if w not in stop}
    sorterade = []
    for p in pages:
        url = (p.get("url") or "").lower()
        md = (p.get("markdown") or "")
        md_low = md.lower()
        poäng = sum(3 for h in trähintar if h in url)
        poäng += min(9, sum(1 for w in ord if w in md_low))
        if poäng > 0:
            sorterade.append((poäng, p))
    sorterade.sort(key=lambda par: par[0], reverse=True)
    valda = [p for _poäng, p in sorterade[:max_sidor]]
    if not valda:
        valda = pages[:max_sidor]  # fallback: första sidorna
    return valda, tema or "allmänt"


def gap_stöd(punkter: list, company_data: dict, progress=None,
             model: str = "default", max_punkter: int = 9):
    """Andra varv mot hemsidan: leta svar på varje gappunkt i de skrapade
    sidorna (crawl+motore-signatur) — personer/CV, kunder som kan bli
    konsortiepartner, tidiga case, konkreta siffror. Muterar 'punkter'
    in-place med fältet 'stöd'."""
    pages = company_data.get("pages") or []
    if not pages or not punkter:
        return
    company = company_data.get("company", "bolaget")
    # prioritet: blockerare > viktigt > förslag — ta de max_punkter första
    valbara = sorted(punkter,
                     key=lambda p: (GRANSKA_VIKT.get(p.get("allvar"), 9),
                                    p.get("nr", 99)))[:max_punkter]
    _tell(progress,
          f"Letar svar på {len(valbara)} gappunkter i hemsidans "
          f"{len(pages)} sidor …",
          {"kind": "note", "title": "🔎 Gap-stöd mot hemsidan",
           "sub": f"{len(valbara)} punkter × {len(pages)} sidor"})

    def _en(p):
        valda, tema = _gap_välj_sidor(p, pages)
        material = "\n\n".join(
            f"### {s['url']}\n{s.get('markdown', '')[:4800]}" for s in valda)
        prompt = f"""Du hjälper {company} att stryka luckorna i deras
ansökningsutkast. Här är en granskningspunkt, och här är sidorna från
bolagets egen webbplats (färskt skrapad).

GRANSKNINGSPUNKT ({p.get('kategori')} / {p.get('allvar')}):
Beskrivning: {p.get('beskrivning')}
Åtgärd som efterfrågas: {p.get('atgard')}

SIDOR (fokus-läge: {tema}):
{material[:15000]}

Leta i sidmaterialet efter det som kan fylla luckan:
- t.ex. namngivna personer eller team som hade kunnat vara i ansökan (CV-start)
- tidigare kunder/samarbetspartners som kan bilda konsortium eller ge lärdom
- konkreta siffror, ska-l, erfarenhetsord, branschlabels
- ALLT i materialet som gör punkten enklare för bolaget att åtgärda

Svara ENBART med JSON:
{{"hittade": true/false,
  "fynd": [{{"sida": "url", "citat": "≤220 tecken från sidan",
             "kommentar": "1 mening om varför det hjälper"}}],
  "personer": ["namn eller roll"],
  "organisationer": ["org-namn som nämns som kund/partner på sidorna"],
  "förslag": "1–3 meningar: konkret hur bolaget utnyttjar fyndet mot gapet"}}"""
        try:
            content, _ = chat([{"role": "user", "content": prompt}],
                              model=model, max_tokens=1500, temperature=0.0)
            j = json.loads(content[content.index("{"):content.rindex("}") + 1])
        except Exception:  # noqa: BLE001
            return
        stöd = {
            "fynd": [f for f in (j.get("fynd") or [])[:4] if f.get("citat")],
            "personer": [s for s in (j.get("personer") or [])[:6] if s][:6],
            "organisationer": [s for s in (j.get("organisationer") or [])[:8]
                               if s][:8],
            "förslag": str(j.get("förslag") or "").strip(),
        }
        if stöd["fynd"] or stöd["förslag"]:
            p["stöd"] = stöd
            _tell(progress,
                  f"  ✓ #{p.get('nr')} {p.get('avsnitt') or ''}: "
                  f"{len(stöd['fynd'])} fynd",
                  {"kind": "note",
                   "title": f"🔎 Gap #{p.get('nr')} stöttad",
                   "sub": f"{len(stöd['fynd'])} fynd, "
                          f"{len(stöd['organisationer'])} org-kandidater"})

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(_en, valbara))
    funna = sum(1 for p in valbara if p.get("stöd"))
    _tell(progress, f"  ✓ gap-stöd klart: {funna}/{len(valbara)} punkter "
                    f"fick stöd", {"kind": "motor",
                                  "title": "Gap-stöd klart",
                                  "sub": f"{funna} av {len(valbara)}"})


def granska_ansokan(res, ansokan_md, progress=None, model="default"):
    """Läs ansökningsutkastet mot utlysningen — vad saknas främst?

    Returnerar {"sammanfattning": str, "punkter": [...]} där varje punkt är
    {"kategori", "allvar", "krav_id"|None, "avsnitt", "beskrivning", "atgard"}.
    """
    dnr = res["dnr"]
    form_fragor = []
    try:
        d = api_get(f"/v1/rounds/{dnr}/form").get("data", {})
        form_fragor = d.get("questions") or []
    except Exception:  # noqa: BLE001
        form_fragor = []

    krav_med_status = []
    for k in res.get("krav") or []:
        st = STATUS_TEXT.get(k.get("status"), k.get("status"))
        krav_med_status.append(
            f"- [{k.get('id') or k.get('requirement_id')}] {st}: "
            f"{_korta(k.get('text'), 200)}"
            + (f" (kommentar: {_korta(k.get('fakta') or k.get('kommentar'), 120)})"
               if (k.get("fakta") or k.get("kommentar")) else ""))
    fragelista = "\n".join(
        f"- {_korta(q.get('question') or q.get('text') or q.get('label'), 150)}"
        for q in form_fragor[:20]) or "- (korpuset saknar formulärfrågor)"
    motor = res.get("motor") or {}
    motortxt = (f"Officiella regelmotorn: eligible={motor.get('eligible')} — "
                + _korta(motor.get("explanation"), 300)) if motor else \
        "Officiella regelmotorn har inte kunnat avgöra (saknar party-fakta)."

    prompt = f"""Du är en väldigt erfaren granskare av ansökningar till {res.get('funder') or 'finansiären'}.
Du har ALDRIG sett bolaget förut — du bedömer BARA utkastet mot utlysningen.
Ingen webbinformation om bolaget finns tillgänglig: allt du behöver veta måste
stå i ansökningsutkastet självt. Det är exakt så en granskande läsare möter
ansökan i verkligheten.

UTLYSNING: {res['title']} ({dnr}), finansiär: {res.get('funder') or ''}
Stänger: {str(res.get('closing_date'))[:10]}
Vem kan söka: {res.get('who') or '–'}

{motortxt}

FORMULÄRFRÅGOR I UTLYSNINGEN:
{fragelista}

KRAVENS STATUS UR KRAVMATRISEN (inte fyllbara i utkastet, men vägleder prio):
{chr(10).join(krav_med_status[:60])}

ANSÖKNINGSUTKAST (markdown):
---
{ansokan_md[:16000]}
---

Läs igenom utkastet KRITISKT mot utlysningen och lista vad som FRÄMST saknas
eller är för svagt innan ansökan kan lämnas in. Tänk på: formalia (belopp,
datum, diarienummer, underskrift, obligatoriska bilagor), obesvarade
formulärfrågor eller "ATT KOMPLETTERA"-lådor, krav som riskerar att underkännas,
svag eller icke-undantagslös argumentstyrka, motsägelser mot utlysningstexten.

Svara ENBART med JSON i exakt detta format:
{{"sammanfattning": "3–6 meningar om läget — vad som främst saknas totalt.",
  "punkter": [{{"kategori": "formalia|formulärfråga|krav|bristande_bevis|svagt_argument|motsägelse",
               "allvar": "blockerare|viktigt|förslag",
               "krav_id": "kravets id om kopplat, annars null",
               "avsnitt": "vilket ställe i ansökan det hör till",
               "beskrivning": "vad som saknas eller är svagt, konkret",
               "atgard": "vad som faktiskt behöver göras, konkret"}}]}}

Högst 30 punkter, ordnat med blockerare först. Var konkret och hänvisa till
utlysningens villkor, inte till allmänna ansökningstips."""
    _tell(progress, f"Granskar {dnr} med färska ögon …",
          {"kind": "form", "title": "🔍 Färska-ögon-granskning",
           "sub": _korta(res["title"], 70)})
    content, usage = chat([{"role": "user", "content": prompt}],
                          model=model, max_tokens=6000, temperature=0.0)
    try:
        g = json.loads(content[content.index("{"):content.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError):
        g = {"sammanfattning": "", "punkter": []}
    punkter = g.get("punkter") or []
    tillåtna_kat = {"formalia", "formulärfråga", "krav", "bristande_bevis",
                    "svagt_argument", "motsägelse"}
    rensade = []
    for i, p in enumerate(punkter[:30], 1):
        if not isinstance(p, dict):
            continue
        rensade.append({
            "nr": i,
            "kategori": str(p.get("kategori") or "krav").strip().lower()
            if str(p.get("kategori") or "").strip().lower() in tillåtna_kat
            else "krav",
            "allvar": str(p.get("allvar") or "viktigt").strip().lower()
            if str(p.get("allvar") or "").strip().lower() in GRANSKA_VIKT
            else "viktigt",
            "krav_id": p.get("krav_id") or None,
            "avsnitt": _korta(p.get("avsnitt"), 100),
            "beskrivning": str(p.get("beskrivning") or "").strip(),
            "atgard": str(p.get("atgard") or "").strip(),
        })
    rensade.sort(key=lambda p: (GRANSKA_VIKT.get(p["allvar"], 9), p["nr"]))
    for i, p in enumerate(rensade, 1):
        p["nr"] = i
    antal = {"blockerare": 0, "viktigt": 0, "förslag": 0}
    for p in rensade:
        antal[p["allvar"]] = antal.get(p["allvar"], 0) + 1
    _tell(progress,
          f"  ✓ granskning klar: {antal['blockerare']} blockerare, "
          f"{antal['viktigt']} viktiga",
          {"kind": "motor",
           "title": f"Granskning: {antal['blockerare']} blockerare · "
                    f"{antal['viktigt']} viktiga",
           "sub": _korta(res["title"], 60)})
    return {"sammanfattning": str(g.get("sammanfattning") or "").strip(),
            "punkter": rensade, "antal": antal}


def bygg_gransknings_xlsx(res, granskning, company, fyllning=None):
    """Granskningsformuläret som Excel — med statusdropdown från rad 2.

    fyllning: valfri dict {"punkter": {nr: {"status","ansvarig","kommentar"}},
                           "kommentar": str} — redan insamlade svar som ska
    vara ifyllda i arket."""
    import io
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    fyllning = fyllning or {}
    ifyllda = (fyllning.get("punkter") or {}) if isinstance(fyllning, dict) else {}

    wb = Workbook()
    ws = wb.active
    ws.title = "Granskning"
    HDR_FILL = PatternFill("solid", fgColor="111816")
    ws.append(["Nr", "Kategori", "Allvar", "Krav", "Avsnitt i ansökan",
               "Brist / vad som saknas", "Åtgärd som behövs",
               "Status", "Ansvarig", "Kommentar",
               "💡 Gap-stöd från hemsidan"])
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = HDR_FILL
        c.alignment = Alignment(vertical="center")
    ALLVAR_FARG = {"blockerare": "FEE2E2", "viktigt": "FEF3C7", "förslag": "DBEAFE"}
    KAT_TEXT = {"formalia": "Formalia", "formulärfråga": "Formulärfråga",
                "krav": "Krav", "bristande_bevis": "Bristande bevis",
                "svagt_argument": "Svagt argument", "motsägelse": "Motsägelse"}
    punkter = granskning.get("punkter") or []
    for p in punkter:
        fylld = ifyllda.get(str(p["nr"])) or ifyllda.get(p["nr"]) or {}
        stöd = p.get("stöd") or {}
        stödtexter = []
        if stöd.get("förslag"):
            stödtexter.append(stöd["förslag"])
        for f in (stöd.get("fynd") or [])[:3]:
            stödtexter.append(f"“{str(f.get('citat'))[:160]}”"
                              f" ({_korta(f.get('sida'), 60)})")
        if stöd.get("personer"):
            stödtexter.append("Personer: " + ", ".join(stöd["personer"]))
        if stöd.get("organisationer"):
            stödtexter.append("Org-kandidater: "
                              + ", ".join(stöd["organisationer"]))
        ws.append([p["nr"], KAT_TEXT.get(p["kategori"], p["kategori"]),
                   p["allvar"].capitalize(), p.get("krav_id") or "",
                   p.get("avsnitt") or "", p.get("beskrivning") or "",
                   p.get("atgard") or "", fylld.get("status") or "Ej påbörjad",
                   fylld.get("ansvarig") or "", fylld.get("kommentar") or "",
                   "\n".join(stödtexter)[:900]])
        ws.cell(row=ws.max_row, column=3).fill = PatternFill(
            "solid", fgColor=ALLVAR_FARG.get(p["allvar"], "FFFFFF"))
    bredd = [5, 15, 12, 14, 22, 48, 42, 14, 16, 30, 52]
    for i, b in enumerate(bredd, 1):
        ws.column_dimensions[get_column_letter(i)].width = b
    for r in ws.iter_rows(min_row=2):
        for c in r:
            c.alignment = Alignment(vertical="top", wrap_text=True)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    dv = DataValidation(type="list",
                        formula1='"Ej påbörjad,Pågår,Löst,Behöver ej"',
                        allow_blank=True, showDropDown=False)
    dv.error = "Välj: Ej påbörjad, Pågår, Löst eller Behöver ej"
    dv.errorTitle = "Ogiltigt värde"
    ws.add_data_validation(dv)
    dv.add(f"H2:H{len(punkter) + 1}")

    ws2 = wb.create_sheet("Om granskningen")
    ws2.column_dimensions["A"].width = 22
    ws2.column_dimensions["B"].width = 90
    ws2.append(["Post", "Innehåll"])
    for c in ws2[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = HDR_FILL
    import time as _time
    rader = [
        ("Bolag", company),
        ("Omgång", f"{res['title']} ({res['dnr']})"),
        ("Genererad", _time.strftime("%Y-%m-%d")),
        ("Sammanfattning", granskning.get("sammanfattning") or ""),
        ("Antal blockerare", (granskning.get("antal") or {}).get("blockerare", 0)),
        ("Antal viktiga", (granskning.get("antal") or {}).get("viktigt", 0)),
        ("Antal förslag", (granskning.get("antal") or {}).get("förslag", 0)),
        ("Formulärkommentar", fyllning.get("kommentar") or ""),
        ("Metod", "LLM-granskning av utkastet mot utlysningens villkor — "
                  "bolagsblind läsning (som en extern utvärderare). "
                  "Kravmatrisens status vägledde prioriteringen."),
        ("Obs", "Granskningen är ett AI-utkast — alla punkter måste "
                "granskas av människa innan inlämning."),
    ]
    for r in rader:
        ws2.append(list(r))
    for r in ws2.iter_rows(min_row=2):
        for c in r:
            c.alignment = Alignment(vertical="top", wrap_text=True)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_kravmatris_xlsx(res, bolagsnamn=""):
    """Kravmatris som .xlsx-bytes: alla krav + bevisstatus + källa."""
    import io
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "Kravmatris"
    rubrik = ["Krav", "Typ", "Obligatoriskt", "Status",
              "Bevis / citat", "Kommentar", "Källa"]
    ws.append(rubrik)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="111816")
    FARGER = {"styrkt_uppfyllt": "dcfce7", "okant": "fef9c3",
              "styrkt_ej_uppfyllt": "fee2e2", "strukturellt": "f3f4f6"}
    for k in res["krav"]:
        källa = (f"{k['prov_terms_id']}#{k['prov_anchor']}"
                 if k.get("prov_terms_id") else "")
        ws.append([k.get("text"), k.get("type"),
                   "ja" if k.get("mandatory") else "",
                   STATUS_TEXT.get(k.get("status"), k.get("status")),
                   k.get("fakta") or "", k.get("kommentar") or "", källa])
        sc = ws.cell(row=ws.max_row, column=4)
        f = FARGER.get(k.get("status"))
        if f:
            sc.fill = PatternFill("solid", fgColor=f.upper())
    bredd = [60, 14, 12, 18, 45, 35, 22]
    for i, b in enumerate(bredd, 1):
        ws.column_dimensions[get_column_letter(i)].width = b
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:G{ws.max_row}"

    o = wb.create_sheet("Översikt")
    o.append([f"Kravmatris — {res['title']} ({res['dnr']})"])
    o["A1"].font = Font(bold=True, size=14)
    räk = res.get("stats", {})
    rader = [
        ("Bolag", bolagsnamn), ("Omgång", res["dnr"]),
        ("Stänger", str(res.get("closing_date"))[:10]),
        ("Finansiär", res.get("funder")),
        ("Analyserade krav", sum(räk.values())),
        ("Styrkt uppfyllda", räk.get("styrkt_uppfyllt", 0)),
        ("Luckor (okänt)", räk.get("okant", 0)),
        ("Felmatchningar", räk.get("styrkt_ej_uppfyllt", 0)),
        ("Strukturkrav", räk.get("strukturellt", 0)),
    ]
    mot = res.get("motor") or {}
    if mot:
        rader += [("Regelmotor eligible", str(mot.get("eligible"))),
                  ("Motorbesked", mot.get("explanation"))]
    for a, b in rader:
        o.append([a, b])
    o.column_dimensions["A"].width = 24
    o.column_dimensions["B"].width = 90
    o.append([])
    o.append(["⚠️ Underlaget för kravbeskorten är bolagets egen webbplats plus "
              "offentliga register. Alla svar ska mänskliggranskas."])
    o["A" + str(o.max_row)].alignment = Alignment(wrap_text=True)
    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()


# ---------------------------------------------------------------- dokument

STATUS_LABEL = {"styrkt_uppfyllt": "✅ Styrkt uppfyllt",
                "styrkt_ej_uppfyllt": "❌ Styrkt ej uppfyllt",
                "okant": "❓ Okänt — att komplettera",
                "strukturellt": "🔧 Strukturkrav"}


def build_krav_doc(company_data, results, progress=None, model="default"):
    """Dokument 1: sammanställd kravbild + förslag på vårt svar per omgång."""
    bolag = company_data["company"]
    delar = [f"""# Kravsammanställning och förslag till svar — {bolag}

*Genererad {time.strftime('%Y-%m-%d')} · Vilabbet korpus 0.7.0 · Underlag: {len(company_data['pages'])} skrapade sidor + bolagsregister*

> Alla svar ska granskas av en människa. Korpusets regel gäller: en källa för
> allt, "kan inte avgöras" istället för gissning.
"""]
    for res in results:
        st = res["stats"]
        delar.append(f"""---

## {res['title']} ({res['dnr']})

**Finansiär:** {res.get('funder') or '–'} · **Stänger:** {str(res.get('closing_date'))[:10]} ·
**Källa:** {res.get('source_url') or f'https://www.vinnova.se/ao/{res["dnr"]}'}

**Vem kan söka:** {res.get('who') or '–'}

**Faktaläge:** ✅ {st.get('styrkt_uppfyllt', 0)} styrkta ·
❓ {st.get('okant', 0)} okända · ❌ {st.get('styrkt_ej_uppfyllt', 0)} felmatch ·
🔧 {st.get('strukturellt', 0)} strukturkrav (av {len(res['krav'])} analyserade)
""")
        _tell(progress, f"Formulerar svarsförslag för {res['dnr']} …")
        kravblock = "\n".join(
            f"- [{STATUS_LABEL.get(k['status'], k['status'])}] ({k['type']}) "
            f"{_korta(k['text'], 180)}"
            + (f" — FAKTA: {_korta(k['fakta'], 120)}" if k.get("fakta") else "")
            for k in res["krav"][:45])
        prompt = f"""Du skriver avdelningen "Vårt svar" i en kravsammanställning för
{bolag}. Nedan kommer omgångens krav med fakta-status. Skriv i svenska:

### Vårt svar — {res['title']}

1. **Kort bedömning** (2-3 meningar): passar omgången bolaget utifrån kraven?
2. **Det vi redan uppfyller** — punktlista med hänvisning till styrkt fakta
3. **Det vi måste komplettera** — punktlista över okända krav, och exakt vilken
   handling som krävs (t.ex. "ta fram registreringsbevis", "identifiera konsortiepartner")
4. **Strukturella åtaganden** — vad ansökans upplägg måste uppfylla (konsortium,
   underskrifter, budget), formulerat som åtgärder

Skriv aldrig påhittade fakta. Tona in att detta är ett utkast för mänsklig granskning.

BOLAGSPROFIL:
{company_data['profil'][:1500]}

KRAV MED STATUS:
{kravblock}"""
        svar, _ = chat([{"role": "user", "content": prompt}],
                       model=model, max_tokens=2200, temperature=0.3)
        delar.append(svar)
        _tell(progress, f"  ✓ svarsförslag klara för {res['dnr']}",
              {"kind": "doc", "title": f"Vårt svar — {_korta(res['title'], 55)}",
               "sub": _first_line(svar)})

        tabellrader = []
        for k in res["krav"]:
            icon = {"styrkt_uppfyllt": "✅", "styrkt_ej_uppfyllt": "❌",
                    "okant": "❓", "strukturellt": "🔧"}.get(k["status"], "")
            fakta = f"„{k['fakta']}“" if k.get("fakta") else "–"
            tabellrader.append(
                f"| {icon} | {k['type']} | {_korta(k['text'], 160)} | "
                f"{_korta(fakta, 130)} |")
        prov_krav = next((k for k in res["krav"] if k.get("prov_terms_id")), None)
        prov_txt = ""
        if prov_krav:
            prov_txt = (f"\n\n*Proveniens-exempel:* `{prov_krav['requirement_id']}` ← "
                        f"`{prov_krav['prov_terms_id']}`"
                        + (f"#{prov_krav['prov_anchor']}" if prov_krav.get("prov_anchor") else ""))
        if res.get("motor"):
            m = res["motor"]
            prov_txt += (f"\n\n*Regelmotor:* eligible={m.get('eligible')} "
                         f"({m.get('automatic_count')} auto, {m.get('not_met_count')} ej uppfyllda, "
                         f"{m.get('needs_review_count')} granskning) — "
                         f"{_korta(m.get('explanation'), 200)}")
        delar.append(f"""
### Bilaga: full kravbild ({len(res['krav'])} krav)

| | Typ | Krav | Fakta/citat |
|---|---|---|---|
{chr(10).join(tabellrader)}
{prov_txt}
""")
    return "\n".join(delar)


def build_application_doc(company_data, res, progress=None, model="default"):
    """Dokument 2: fullständig ansökningshandling (utkast)."""
    bolag = company_data["company"]
    dnr = res["dnr"]
    material = "\n\n".join(f"[{p['url']}]\n{p['markdown'][:6000]}" for p in company_data["pages"])

    formfragor = []
    try:
        d = api_get(f"/v1/rounds/{dnr}/form").get("data", {})
        formfragor = d.get("questions") or []
    except Exception:  # noqa: BLE001
        formfragor = []
    _tell(progress, f"{len(formfragor)} formulärfrågor hittade" if formfragor
          else "Inget formulär i korpuset — använder standardstruktur",
          {"kind": "form", "title": "Formulärfrågor" if formfragor else "Standardstruktur",
           "sub": f"{len(formfragor)} frågor att besvara" if formfragor
           else "klassisk ansökningsstruktur"})
    for q in formfragor[:6]:
        _tell(progress, f"  fråga: {_korta(q.get('question') or q.get('text'), 60)}",
              {"kind": "form",
               "title": _korta(q.get("question") or q.get("text") or q.get("label"), 95),
               "sub": "formulärfråga"})

    if formfragor:
        fragelista = "\n".join(
            f'{i}. {q.get("question") or q.get("text") or q.get("label")}'
            + (f" (typ: {q.get('answer_type')}, max {q.get('max_length')} tecken)"
               if q.get("answer_type") else "")
            for i, q in enumerate(formfragor, 1))
        struktur = f"""Skriv dokumentet som utkast till ansökan med EXAKT dessa
formulärfrågor som avsnitt (samma ordning, numrerade). Under varje fråga:
**Förslag till svar:** <konkret utkasttext för {bolag} inom ev. teckengräns>
**Stöd/källa:** <vilken del av underlaget svaret vilar på, eller "ATT KOMPLETTERA: …">

FORMULÄRFRÅGOR:
{fragelista}"""
    else:
        struktur = f"""Korpuset saknar formulärfrågor för denna omgång. Använd denna
klassiska ansökningsstruktur, ett avsnitt per punkt, med samma märkning
"Förslag till svar" + "Stöd/källa":
1. Sammanfattning av projektet (300 ord)
2. Bakgrund och behov (problemet som löses)
3. Projektbeskrivning och innovativ höjd
4. Mål och förväntade effekter
5. Genomförande (aktiviteter, tidplan)
6. Projektorganisation och kompetens
7. Budget och finansieringsplan (totalt, sökt belopp, egen insats)
8. Risker och riskhantering
9. Hållbarhet och jämställdhet
10. Uppfyllelse av särskilda krav för omgången"""

    prompt = f"""Du skriver utkast till en komplett svensk ansökningshandling åt
bolaget {bolag} för utlysningen nedan. Skriv på svenska, professionellt och
konkret. Påståenden om bolaget ska vila på det bifogade underlaget; där
underlaget saknas skriver du "ATT KOMPLETTERA: …" istället för att gissa.

UTLYSNING: {res['title']} ({dnr}), {res.get('funder') or ''}
Stänger: {str(res.get('closing_date'))[:10]}
Vem kan söka: {res.get('who') or '–'}

VIKTIGA KRAV (urval):
{chr(10).join('- ' + _korta(k['text'], 150) for k in res['krav'][:20])}

BOLAGETS PROFIL:
{company_data['profil']}

UNDERLAG FRÅN WEBBPLATS:
{material[:14000]}

{struktur}

Avsluta med en checklista "Innan inlämning" (underskrifter, bilagor, datum)."""
    _tell(progress, "Skriver ansökningshandling …")
    doc, _ = chat([{"role": "user", "content": prompt}],
                  model=model, max_tokens=6000, temperature=0.3)
    _tell(progress, "  ✓ ansökningshandling klar",
          {"kind": "doc", "title": "📝 Ansökningshandling", "sub": _first_line(doc)})
    return f"""# Utkast till ansökningshandling — {res['title']}

*Bolag: {bolag} · Omgång: {dnr} · Genererad {time.strftime('%Y-%m-%d')} ·
Källa: {res.get('source_url') or f'https://www.vinnova.se/ao/{dnr}'}*

> ⚠️ Utkast för mänsklig granskning. "ATT KOMPLETTERA" markerar luckor i underlaget.

---

{doc}
"""
