"""Steg E: bygg reveal.js-presentation från krav_fakta_<tag>.json.

Skapar output/presentation_<tag>/index.html — varje kapitel är en horisontell
slide med vertikala djupdyk (nästlade <section data-markdown>, inga
separator-gissningar). slides.md skrivs också som portabel källa
(--- horisontell, -- vertikal).
"""
import argparse
import html
import json
import os
import re
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))

STATUS = {
    "styrkt_uppfyllt": "✅",
    "styrkt_ej_uppfyllt": "❌",
    "okant": "❓",
    "strukturellt": "🔧",
}


def korta(text, n=90):
    text = re.sub(r"\s+", " ", str(text or "").strip())
    return text if len(text) <= n else text[:n - 1] + "…"


def esc(text):
    return html.escape(str(text or ""))


def md_table(rows, header):
    lines = ["| " + " | ".join(header) + " |",
             "|" + "---|" * len(header)]
    for r in rows:
        lines.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(lines)


def motor_label(motor):
    if not motor:
        return "ej körd (party-fil saknas)"
    if motor.get("error"):
        return f"fel: {korta(motor['error'], 60)}"
    if motor.get("eligible") is True:
        return "✅ eligible — automatiska krav OK"
    if motor.get("eligible") is False:
        return f"❌ {korta(motor.get('explanation'), 120)}"
    return (f"⚠️ ej avgörbart — {motor.get('automatic_count', '?')} auto-krav OK, "
            f"{motor.get('not_met_count', 0)} underkända, "
            f"{motor.get('needs_review_count', '?')} kräver granskning")


def bygg_stacks(data, profil_text):
    company = data["company"]
    rounds = data["rounds"]
    stacks = []  # lista av {h: markdown, v: [markdown, ...]}

    stacks.append({"h": f"""# Finansieringsmatchning

## {company}

Korpus 0.7.0 (Vilabbet, byggd 2026-10-16) · {date.today().isoformat()}

Profil → embeddings (303 omgångar) → LLM-poäng → kravanalys → faktasök → regelmotor

<small>Tryck **↓** på varje omgång för att fördjupa dig. Alla bedömningar ska
verifieras — korpusets regel: en källa för allt, gissa aldrig.</small>""", "v": []})

    stacks.append({"h": f"""## Metod

1. **Profil**: webbplats skrapad (Firecrawl via api.berget.ai) → LLM destillerade bolagsprofil
2. **Matchning**: cosine-likhet mellan profil-embedding och 303 omgångar
3. **Finsil**: LLM poängsatte tema/eligibility på topp 29
4. **Kravanalys**: topp 10 — krav av typ eligibility/formal/tid/medfinansiering/kostnadstak
5. **Faktasök**: LLM svarade på kraven ENBART utifrån skrapad textmassa
6. **Regelmotor**: `/v1/eligibility/check` med bolagsfakta \\*

\\* **ANTAGANDEN** — ersätt med riktiga siffror

<small>↓ djup: bolagets profil + statusvärden</small>""",
                   "v": [f"""### Bolagets profil (destillerad)

{profil_text}""",
                         """### Faktasögets statusvärden

- ✅ **styrkt_uppfyllt** — textmassan visar uppfyllt (citat)
- ❌ **styrkt_ej_uppfyllt** — textmassan visar att det INTE uppfylls
- ❓ **okant** — textmassan saknar fakta (lucka)
- 🔧 **strukturellt** — ansökans/projektets upplägg, inte bolagsfakta"""]})

    rows = []
    for r in rounds:
        st = r["stats"]
        rows.append([
            korta(r["title"], 45),
            "🟢" if r["can_apply_now"] else "⏸️",
            f"{r['totalt']:.1f}",
            f"✅{st.get('styrkt_uppfyllt', 0)} ❓{st.get('okant', 0)} "
            f"❌{st.get('styrkt_ej_uppfyllt', 0)} 🔧{st.get('strukturellt', 0)}",
        ])
    stacks.append({"h": f"""## Översikt — topp {len(rounds)} för {company}

{md_table(rows, ["Omgång", "Sökbar", "Poäng", "Faktaläge"])}

<small>🟢 = kan sökas nu · ⏸️ = stängd (bevaka nästa omgång) ·
poäng = viktad matchningspoäng 0-10</small>""", "v": []})

    for i, r in enumerate(rounds, 1):
        st = r["stats"]
        n_krav = len(r["krav"])
        status_txt = "🟢 Öppen för ansökan" if r["can_apply_now"] else "⏸️ Stängd — kan inte sökas nu"
        motor = r.get("motor") or {}
        if motor.get("eligible") is False:
            recom = "❌ Motorn ser ett automatiskt hinder"
        elif r["totalt"] >= 6 and st.get("styrkt_ej_uppfyllt", 0) == 0:
            recom = "✅ Värd att gå vidare med"
        else:
            recom = "⚠️ Granska luckorna innan beslut"

        h = f"""## {i}. {korta(r['title'], 70)}

**{r['dnr']}** · {r.get('funder', '')} · stänger {str(r.get('closing_date'))[:10]}

{status_txt} · Matchpoäng **{r['totalt']:.1f}**/10

| ✅ styrkta | ❓ okända | ❌ felmatch | 🔧 strukturella | av {n_krav} krav |
|---|---|---|---|---|
| {st.get('styrkt_uppfyllt', 0)} | {st.get('okant', 0)} | {st.get('styrkt_ej_uppfyllt', 0)} | {st.get('strukturellt', 0)} | analyserade |

**Regelmotor:** {motor_label(motor)}

### {recom}

<small>↓ vem kan söka · besvarade krav · luckor · strukturkrav & källa</small>"""

        v1 = f"""### Vem kan söka & varför träff

**LLM-bedömning:** {esc(korta(r.get("motivering"), 480))}

**Kända risker:** {esc(korta("; ".join(r["risker"]) if isinstance(r.get("risker"), list) else r.get("risker"), 280))}

<small>○ = LLM-omdöme i matchningssteget, inte regelmotor</small>"""

        styrkta = [k for k in r["krav"] if k["status"].startswith("styrkt")]
        if styrkta:
            body = md_table(
                [[STATUS[k["status"]], korta(k["text"], 80),
                  "„" + korta(k.get("fakta"), 75) + "“"] for k in styrkta[:9]],
                ["", "Krav", "Fakta ur textmassan"])
        else:
            body = "_Inga krav kunde besvaras ur textmassan._"
        v2 = f"### Krav besvarade ur textmassan ({len(styrkta)})\n\n{body}"

        okanda = [k for k in r["krav"] if k["status"] == "okant"]
        if okanda:
            body = md_table([[korta(k["text"], 92), k.get("type", "")]
                             for k in okanda[:10]],
                            ["Lucka — fakta saknas i textmassan", "Typ"])
        else:
            body = "_Inga luckor._ 🎉"
        v3 = f"### Luckor att fylla ({len(okanda)})\n\n{body}"

        strukt = [k for k in r["krav"] if k["status"] == "strukturellt"]
        exempel = next((k for k in r["krav"] if k.get("prov_terms_id")), None)
        prov = ""
        if exempel:
            prov = (f"**Proveniens (exempel):** `{exempel['requirement_id']}` ← "
                    f"`{exempel.get('prov_terms_id')}`"
                    + (f"#{exempel['prov_anchor']}" if exempel.get("prov_anchor") else "")
                    + (f"\n\n> {korta(exempel.get('prov_quote'), 220)}"
                       if exempel.get("prov_quote") else ""))
        v4 = f"""### Strukturkrav & ansökningsupplägg ({len(strukt)})

Konsortium, underskrifter, budget, projektplan — designval snarare än bolagsfakta.

{md_table([[korta(k["text"], 100)] for k in strukt[:6]], ["Exempel"])}

{prov}"""

        stacks.append({"h": h, "v": [v1, v2, v3, v4]})

    stacks.append({"h": f"""## Sammanfattningsvis — {company}

- De flesta krav är 🔧 **strukturella** — avgörs av ansökans upplägg, inte bolaget
- ❓ **Luckor** gäller juridisk entitet/registreringar → lös med bolagsdata
- ❌ **Felmatch** betyder: textmassan motsäger krav — omgången passar sannolikt inte
- Regelmotorn är striktast: kör `/v1/eligibility/check` med riktiga siffror före beslut

**Nästa steg:** verifiera antaganden → välj 1–2 omgångar → fyll luckor → ansök med källhänvisningar""", "v": []})

    return stacks


HTML_TEMPLATE = """<!doctype html>
<html lang="sv">
<head>
<meta charset="utf-8">
<title>Finansieringsmatchning — {company}</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/reveal.js@5/dist/reveal.css">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/reveal.js@5/dist/theme/white.css">
<style>
  .reveal {{ font-size: 30px; }}
  .reveal table {{ font-size: 0.6em; }}
  .reveal h1 {{ font-size: 1.6em; }} .reveal h2 {{ font-size: 1.15em; }}
  .reveal h3 {{ font-size: 0.9em; }}
  .reveal small {{ font-size: 0.55em; color: #666; }}
  .reveal blockquote {{ font-size: 0.6em; }}
  .reveal td, .reveal th {{ padding: 0.25em 0.5em; }}
</style>
</head>
<body>
<div class="reveal"><div class="slides">
{sections}
</div></div>
<script src="https://cdn.jsdelivr.net/npm/reveal.js@5/dist/reveal.js"></script>
<script src="https://cdn.jsdelivr.net/npm/reveal.js@5/plugin/markdown/markdown.js"></script>
<script>Reveal.initialize({{plugins: [RevealMarkdown], slideNumber: true, hash: true}});</script>
</body>
</html>
"""


def section(md):
    return ("<section data-markdown><textarea data-template>\n"
            + md + "\n</textarea></section>")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    args = ap.parse_args()
    tag = args.tag

    data = json.load(open(os.path.join(HERE, "output", f"krav_fakta_{tag}.json")))
    profil_path = os.path.join(HERE, "profiler", f"{tag}_profil.txt")
    profil = open(profil_path).read() if os.path.exists(profil_path) else ""

    stacks = bygg_stacks(data, profil)

    html_parts = []
    for st in stacks:
        leaves = [section(st["h"])] + [section(v) for v in st["v"]]
        html_parts.append("<section>\n" + "\n".join(leaves) + "\n</section>")

    md_parts = []
    for st in stacks:
        md_parts.append("\n\n--\n\n".join([st["h"]] + st["v"]))
    markdown = "\n\n---\n\n".join(md_parts)

    outdir = os.path.join(HERE, "output", f"presentation_{tag}")
    os.makedirs(outdir, exist_ok=True)
    open(os.path.join(outdir, "slides.md"), "w").write(markdown)
    open(os.path.join(outdir, "index.html"), "w").write(
        HTML_TEMPLATE.format(company=data["company"],
                             sections="\n".join(html_parts)))
    print(f"Skrev {outdir}/index.html + slides.md ({len(stacks)} kapitel, "
          f"{sum(1 + len(s['v']) for s in stacks)} slides)")


if __name__ == "__main__":
    main()
