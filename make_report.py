"""Steg 5: slutrapport som markdown."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))

llm = json.load(open(os.path.join(HERE, "output", "ranking_llm.json")))
emb = json.load(open(os.path.join(HERE, "output", "ranking_embeddings.json")))
details = json.load(open(os.path.join(HERE, "cache", "rounds_detail.json")))

def url(dnr):
    return f"https://www.vinnova.se/ao/{dnr}" if not dnr.startswith(("vr", "formas")) else \
        (details.get(dnr) or {}).get("source_url", "")

def row(r):
    dnr = r["dnr"]
    d = details.get(dnr) or {}
    st = d.get("status") or {}
    warnings = "; ".join(st.get("warnings") or r.get("warnings") or [])
    return f"""### {r['totalt']:.1f}/10 — [{r['title']}]({url(dnr)}) ({dnr})

- **Status:** {r['state']}{" ✅ ÖPPEN" if r.get('can_apply_now') else ""} | stänger {str(r.get('closing_date'))[:16]} | {r.get('funder')}
- **Poäng:** tema {r['tematisk_passform']}/10, eligibility {r['eligibility_passform']}/10, embedding {r['embedding_similarity']}
- **Vem kan söka:** {(d.get('who') or {}).get('sv','-')}
- **Bedömning:** {r['motivering']}
- **Risker:** {"; ".join(r['risker']) if isinstance(r['risker'], list) else r['risker']}
{f"- **Statusvarningar:** {warnings}" if warnings else ""}
"""

open_ranked = [r for r in llm if r["can_apply_now"]]
closed_ranked = [r for r in llm if not r["can_apply_now"]]

md = f"""Matchningsrapport: Vinnova/Formas/VR-omgångar × bolaget
Korpus 0.7.0 (byggd 2026-10-16) · 303 omgångar rankade · genererad via vilabbet.se sandbox

## Metod

1. **Profil** skrapad webbplats (profil.txt)
2. **Embeddings-rankning** (gateway-modellen `embedding`, cosine) av alla 303 omgångars titel + beskrivning + vad/vem/hur-texter
3. **LLM-poäng** (`default`-modellen) på tema/eligibility/behovsdrivenhet för toppkandidater
4. **Eligibility-check** (`/v1/eligibility/check`) med bolaget som part

⚠️ Eligibility-testerna bygger på ANTAGANDEN om bolagets siffror (anställda, omsättning).
Korpusets regelverk: många krav är `needs_human` (mänsklig granskning) — en grön
automatisk check är inte ett godkännande.

## 🟢 Öppna omgångar (kan sökas nu), rankade

{"".join(row(r) for r in open_ranked)}

## ⏸️ Stängda men starka matchningar (bevaka nästa omgång)

{"".join(row(r) for r in closed_ranked[:8])}

## Nyckelfynd från eligibility-checks

| Omgång | Konstellation | Resultat | Kommentar |
|---|---|---|---|
| 2025-04831 Innovativa Startups 2026 | Solo | ✅ eligible | **Krav: max 10 anställda** (S4) och max 10 mkr omsättning/balans (S5). Bidrag ≤ 500 000 kr. 13/13 auto-krav OK. |
| 2026-01892 Cyberfysiska system | Konsortium (min 2 parter) | ✅ eligible | Faller solo på `min_antal_parter`. Max 8 Mkr, ≤50 % stödnivå. 14/14 auto-krav OK. |
| 2026-01891 Cybersäkerhet, AI och resiliens | Konsortium (min 2 parter) | ✅ eligible | Faller solo på `min_antal_parter`. Max 10 Mkr, ≤50 % stödnivå. 15/15 auto-krav OK. |
"""
open(os.path.join(HERE, "output", "matchningsrapport.md"), "w").write(md)
print("Skrev output/matchningsrapport.md")
print(f"Öppna rankade: {len(open_ranked)}, stängda topp: {min(8, len(closed_ranked))}")
