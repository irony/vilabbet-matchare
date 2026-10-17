"""Bygg sammanställnings-xlsx av alla matchningsdata.

Kör:  uv run --with openpyxl python3 bygg_excel.py
"""
import json
import os
import re
from datetime import date

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "output", f"vinnova_matchningar_{date.today().isoformat()}.xlsx")

HDR_FILL = PatternFill("solid", fgColor="1F2937")
HDR_FONT = Font(color="FFFFFF", bold=True)
WRAP = Alignment(vertical="top", wrap_text=True)
OK_FILL = PatternFill("solid", fgColor="DCFCE7")
WARN_FILL = PatternFill("solid", fgColor="FEF3C7")
BAD_FILL = PatternFill("solid", fgColor="FEE2E2")


def sheet(wb, title, header, rows, widths, first=False):
    ws = wb.active if first else wb.create_sheet()
    ws.title = title
    ws.append(header)
    for c in ws[1]:
        c.fill = HDR_FILL
        c.font = HDR_FONT
        c.alignment = Alignment(vertical="center")
    for row in rows:
        ws.append(row)
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    for r in ws.iter_rows(min_row=2):
        for c in r:
            c.alignment = WRAP
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    return ws


def load(name):
    p = os.path.join(HERE, "output", name)
    return json.load(open(p)) if os.path.exists(p) else None


def korta(text, n=300):
    text = re.sub(r"\s+", " ", str(text or "").strip())
    return text if len(text) <= n else text[:n - 1] + "…"


# ---------- data ----------
# Byt till dina egna tags (namn på körda bolagskörningar i output/).
tags = ["bolag-A"]
ranking = {t: load(f"ranking_llm_{t}.json") or [] for t in tags}
kf = load(f"krav_fakta_{tags[0]}.json") if tags else None
elig = load("eligibility.json")  # deep-dive för topp-omgångar
party_bolag = load(f"../profiler/{tags[0]}_party.json") if tags else None

wb = Workbook()

# ---------- 1. Översikt ----------
rows = []
for t in tags:
    top = ranking[t][0] if ranking[t] else {}
    kravrunda = None
    if kf and t == tags[0]:
        kravrunda = f"{len(kf['rounds'])} omgångar kravanalyserade"
    bolagsdata = ""
    if t == tags[0] and party_bolag:
        for p in party_bolag.get("payload", {}).get("parties", [])[:1]:
            bolagsdata = (f"{p.get('name')}: {p.get('employees')} anst, "
                          f"grundat {p.get('founded')}, "
                          f"oms {p.get('turnover_ksek')} tkr, "
                          f"balans {p.get('balance_sheet_total_ksek')} tkr "
                          f"(allabolag.se {party_bolag.get('orgnr')})")
    rows.append([
        t, "✅ klar", len(ranking[t]),
        korta(top.get("title"), 60), top.get("dnr", ""),
        f"{top.get('totalt', 0):.1f}" if top else "",
        kravrunda or "–", bolagsdata or "–",
    ])
ov = sheet(wb, "Översikt",
           ["Bolag (tag)", "Status", "Rankade omgångar", "Toppmatchning", "Dnr",
            "Poäng", "Kravanalys", "Verifierade bolagsfakta"],
           rows, [16, 10, 10, 60, 14, 8, 26, 60], first=True)
ov.append([])
ov.append(["Metod", "webbplats → Firecrawl-scrape → LLM-profil → "
                   "embeddings-match mot 303 omgångar (Vilabbet korpus 0.7.0) → LLM-poäng topp N "
                   "→ kravanalys + regelmotor (/v1/eligibility/check)"])
ov["A3"].font = Font(italic=True, size=9)

# ---------- 2. Ranking ----------
rows = []
for t in tags:
    for r in ranking[t]:
        risker = r.get("risker")
        rows.append([
            t, r.get("dnr"), korta(r.get("title"), 70), r.get("funder"),
            "🟢 öppen" if r.get("can_apply_now") else f"⏸️ {r.get('state')}",
            str(r.get("closing_date"))[:10],
            r.get("tematisk_passform"), r.get("eligibility_passform"),
            r.get("embedding_similarity"),
            round(r.get("totalt", 0), 2),
            korta(r.get("motivering"), 400),
            korta("; ".join(risker) if isinstance(risker, list) else risker, 250),
        ])
ws = sheet(wb, "Ranking topp-29 per bolag",
           ["Bolag", "Dnr", "Titel", "Finansiär", "Status", "Stänger",
            "Tema 0-10", "Eligib. 0-10", "Cosine", "Totalt", "Motivering (LLM, källförankrad)",
            "Risker"],
           rows, [10, 13, 55, 10, 11, 11, 8, 8, 8, 8, 60, 40])
for r in ws.iter_rows(min_row=2):
    r[4].fill = OK_FILL if "öppen" in str(r[4].value) else PatternFill()

# ---------- 3. Krav & fakta ----------
if kf:
    rows = []
    for r in kf["rounds"]:
        for k in r["krav"]:
            icon = {"styrkt_uppfyllt": "✅", "styrkt_ej_uppfyllt": "❌",
                    "okant": "❓", "strukturellt": "🔧"}.get(k["status"], "")
            rows.append([
                r["dnr"], korta(r["title"], 45), k["requirement_id"],
                k.get("type"), "oblig." if k.get("mandatory") else "",
                k.get("checkable"), f"{icon} {k['status']}",
                korta(k.get("text"), 300),
                korta(k.get("fakta"), 220),
                (korta(k.get("prov_terms_id"), 40) or "") +
                ("#" + k["prov_anchor"] if k.get("prov_anchor") else ""),
                korta(k.get("prov_quote"), 220),
            ])
    ws = sheet(wb, f"Krav & fakta {tags[0]}",
               ["Omgång", "Titel", "Krav-id", "Typ", "Mand.", "Checkbar",
                "Fakta-status", "Kravtext", "Fakta/citat ur textmassa",
                "Proveniens", "Källcitat (korpus)"],
               rows, [12, 40, 22, 12, 7, 12, 16, 60, 45, 42, 45])
    for r in ws.iter_rows(min_row=2):
        s = str(r[6].value)
        if "styrkt_ej" in s:
            r[6].fill = BAD_FILL
        elif "styrkt_upp" in s:
            r[6].fill = OK_FILL
        elif "okant" in s:
            r[6].fill = WARN_FILL

# ---------- 4. Regelmotor ----------
rows = []
if kf:
    for r in kf["rounds"]:
        m = r.get("motor") or {}
        rows.append([tags[0], r["dnr"], korta(r["title"], 45),
                     str(m.get("eligible")), m.get("automatic_count"),
                     m.get("not_met_count"), m.get("needs_review_count"),
                     korta(m.get("explanation"), 220)])
if elig:
    for dnr, v in elig.items():
        c = v.get("check", {})
        titel = next((x.get("title") for t in tags for x in ranking[t] if x.get("dnr") == dnr), "")
        rows.append([tags[0], dnr, korta(titel, 45),
                     str(c.get("eligible")), c.get("automatic_count"),
                     c.get("not_met_count"), c.get("needs_review_count"),
                     korta(c.get("explanation"), 220)])
ws = sheet(wb, "Regelmotor eligibility",
           ["Bolag", "Dnr", "Titel", "eligible", "Auto-krav", "Ej uppfyllda",
            "Kräver granskning", "Motorns förklaring"],
           rows, [12, 12, 45, 10, 9, 10, 12, 70])
for r in ws.iter_rows(min_row=2):
    v = str(r[3].value)
    r[3].fill = OK_FILL if v == "True" else (BAD_FILL if v == "False" else WARN_FILL)

# ---------- 5. Antaganden & källor ----------
rows = [
    ["Bolagsfakta", "Verifierade via Bolagsverkets register + allabolag.se",
     "Fylls i dynamiskt per körning — ersätt med riktiga siffror"],
    ["Belopp/datum i motorkörningar", "Avsiktligt utelämnade",
     "De krav som beror på sökt belopp/projektperiod blir 'kan inte avgöras' = ärliga luckor"],
    ["Korskäl korpus", "Vilabbet korpus 0.7.0 (byggd 2026-10-16)",
     "129 utlysningar, 303 omgångar, 8 471 krav; regel: citera källa, gissa aldrig"],
    ["LLM-omdömen", "Bedömningar, inte fakta",
     "Tema/eligibility-poäng och fakta-status kommer från LLM-läsning; verifiera alltid mot källan"],
]
sheet(wb, "Antaganden & källor", ["Post", "Status", "Detalj"], rows, [30, 45, 70])

os.makedirs(os.path.dirname(OUT), exist_ok=True)
wb.save(OUT)
print(f"Skrev {OUT} ({os.path.getsize(OUT)//1024} KB, {len(wb.sheetnames)} blad: {wb.sheetnames})")
