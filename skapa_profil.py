"""Skapa företagsprofil för valfritt bolag via Bergets Firecrawl-endpoint.

Användning:
    python3 skapa_profil.py https://example.se [--namn "Exempelbolaget"] [--extra "fritext om bolaget"]

Steg: map -> välj relevanta sidor -> scrape (markdown) -> LLM sammanfattar
-> profiler/<slug>_profil.txt
"""
import argparse
import json
import os
import re
import time
import urllib.error
import urllib.request

from vilabbet_client import chat

HERE = os.path.dirname(os.path.abspath(__file__))

BERGET_KEY = os.environ.get("BERGET_API_KEY", "").strip()

FIRECRAWL = "https://api.berget.ai/v1/firecrawl"

# Sidor som brukar beskriva ett bolag bäst
PRIO_PAT = re.compile(
    r"($|/(om|about|om-oss|who-we-are|company|bolaget|produkter?|products?|"
    r"tjanster|tjänster|services|erbjudande|offer|losningar|lösningar|solutions|"
    r"case|kunder|customers|branscher|industries|teknik|tech|plattform|platform|"
    r"ai|varfor|varför|why|karriar|career|jobb))",
    re.IGNORECASE)
SKIP_PAT = re.compile(
    r"(blogg|blog|nyhet|news|press|artikel|article|pod|event|webinar|"
    r"integritet|privacy|cookie|gdpr|terms|villkor|legal|login|signup|"
    r"kontakt|contact|tag/|category/|author/|\.(pdf|jpg|png|zip)$)",
    re.IGNORECASE)

MAX_PAGES = 8
MAX_MD_PER_PAGE = 9000


def firecrawl(endpoint, payload, timeout=120):
    req = urllib.request.Request(
        f"{FIRECRAWL}/{endpoint}", data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {BERGET_KEY}",
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def scrape(url):
    try:
        r = firecrawl("scrape", {"url": url, "formats": ["markdown"],
                                 "onlyMainContent": True})
        if r.get("success"):
            return (r.get("data") or {}).get("markdown") or ""
        print(f"  !! scrape {url}: {r}")
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
        print(f"  !! scrape {url}: {e}")
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url", help="Bolagets webbadress, t.ex. https://example.se")
    ap.add_argument("--namn", help="Bolagsnamn (annars härleds från domänen)")
    ap.add_argument("--extra", help="Extra fritext om bolaget att väva in")
    ap.add_argument("--slug", help="Åsidosätt filnsuffixet profiler/<slug>_*")
    ap.add_argument("--endast-material", action="store_true",
                    help="Skrapa bara råmaterial, återskapa inte profilen")
    args = ap.parse_args()

    if not BERGET_KEY:
        raise SystemExit(
            "Sätt BERGET_API_KEY som env-variabel först, t.ex:\n"
            "  export BERGET_API_KEY=...  # nyckel med aktiv subscription\n"
            "  python3 skapa_profil.py https://example.se")

    base = args.url.rstrip("/")
    dom = re.sub(r"^https?://(www\.)?", "", base).split("/")[0]
    namn = args.namn or dom.split(".")[0].capitalize()
    slug = args.slug or re.sub(r"[^a-z0-9]+", "-", dom.lower()).strip("-")

    print(f"== {namn} ({base})")
    print("1/3 map: letar sidor...")
    urls = [base]
    try:
        m = firecrawl("map", {"url": base, "limit": 500})
        found = m.get("links") or (m.get("data") or {}).get("links") or []
        if isinstance(found, list):
            urls += [u.get("url") if isinstance(u, dict) else u for u in found]
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
        print(f"  map misslyckades ({e}), fortsätter med bara startsidan")

    picked, seen = [], set()
    for u in urls:
        if not u or u in seen or SKIP_PAT.search(u):
            continue
        seen.add(u)
        if u.rstrip("/") == base or PRIO_PAT.search(u.replace(base, "")):
            picked.append(u)
    picked = picked[:MAX_PAGES]
    print(f"  {len(urls)} sidor hittade, skrapar {len(picked)}: "
          f"{[u.replace(base,'') or '/' for u in picked]}")

    print("2/3 scrape...")
    pages = []
    raw = []
    for u in picked:
        md = scrape(u)
        if md:
            pages.append(f"### {u}\n{md[:MAX_MD_PER_PAGE]}")
            raw.append({"url": u, "markdown": md})
            print(f"  ✓ {u} ({len(md)} tecken)")
        time.sleep(0.3)
    if not pages:
        raise SystemExit("Inget innehåll skrapat — avbryter")

    os.makedirs(os.path.join(HERE, "profiler"), exist_ok=True)
    raw_path = os.path.join(HERE, "profiler", f"{slug}_ramaterial.json")
    json.dump({"company": namn, "base_url": base, "pages": raw},
              open(raw_path, "w"), ensure_ascii=False, indent=1)
    print(f"  råmaterial sparat: {raw_path}")

    if args.endast_material:
        print("Klar (--endast-material, profil orörd).")
        return

    print("3/3 LLM sammanfattar profil...")
    material = "\n\n".join(pages)
    system = """Du skapar en företagsprofil som ska användas för att matcha bolaget
mot svenska innovationsutlysningar (Vinnova m.fl.). Skriv på svenska i exakt
denna struktur:

<BOLAGSNAMN>

<1-2 meningar: vad bolaget gör, grundat år om det framgår, storlek om det framgår>

Produkter och teknik:
- <punktlista: konkreta produkter, tjänster, teknikstack, expertis>

Differentiering och värdeerbjudande:
- <punktlista: vad som skiljer bolaget, certifieringar, unika styrkor>

Kunder: <branscher och kundtyper bolaget säljer till>

Kompetens: <nyckelkompetenser, kommaseparerat>

Vi söker samarbeten kring: <3-6 teman där bolaget rimligen skulle söka
finansierad samverkan — härled ur erbjudandet, teman inte produktnamn>

Skriv endast sådant som stöds av källmaterialet. Utelämna det som inte framgår
istället för att gissa. Total längd: 200-350 ord."""
    user = f"Bolag: {namn} ({base})\n\nSKRAPAT MATERIAL:\n{material}"
    if args.extra:
        user += f"\n\nEXTRA INFORMATION FRÅN BESTÄLLAREN (lita på denna):\n{args.extra}"
    profil, usage = chat([{"role": "system", "content": system},
                          {"role": "user", "content": user}],
                         model="default", max_tokens=1200, temperature=0.2)

    path = os.path.join(HERE, "profiler", f"{slug}_profil.txt")
    with open(path, "w") as f:
        f.write(profil.strip() + "\n")
    print(f"\n✓ Profil sparad: {path} ({usage.get('total_tokens','?')} tokens)\n")
    print(profil)


if __name__ == "__main__":
    main()
