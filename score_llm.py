"""Steg 3: LLM-poängsättning av toppkandidater — öppna omgångar + topp-15 stängda.

Användning: python3 score_llm.py [--profil profil.txt] [--tag bolag]
"""
import argparse
import json
import os

from vilabbet_client import chat

HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument("--profil", default="profil.txt")
ap.add_argument("--tag", default="bolag")
args = ap.parse_args()
TAG = args.tag
PROFIL = open(os.path.join(HERE, args.profil)).read().strip()
OUT = os.path.join(HERE, "output", f"ranking_llm_{TAG}.json")

SYSTEM = """Du är expert på svenska innovationsfinansiärer (Vinnova, Formas, VR) och
bedömer hur väl en ansökningsomgång passar ett företag. Svara ALLTID med
en JSON-objektlista med exakt dessa fält:
- tematisk_passform: heltal 0-10 (hur väl omgångens tema matchar företagets erbjudande)
- eligibility_passform: heltal 0-10 (hur väl företaget matchar "vem kan söka" — storlek, bransch, konsortiekrav)
- behovs_driven: heltal 0-10 (krävs extern behovsägare/kund snarare än egen innovation?)
- motivering: max 3 meningar på svenska, med citat ur omgångstexten inom "..."
- risker: max 2 korta punkter (t.ex. storlekskrav, branschkrav, konsortiekrav)
Bedöm STR ÄNGT: en generisk AI-referens i texten räcker inte för hög tematisk poäng.
Basera allt på den givna omgångstexten, gissa inte."""


def round_block(dnr, d):
    texts = []
    for t in d.get("texts") or []:
        if t.get("text"):
            texts.append(f"[{t.get('heading') or t.get('field')}]: {t['text']}")
    blob = "\n".join(texts) or (d.get("description") or "")
    return f"""### {dnr}: {d.get('title')}
Status: {d.get('state')} | Sista dag: {d.get('closing_date')} | Finansiär: {d.get('funder')}
VAD: {(d.get('what') or {}).get('sv') or '-'}
VEM: {(d.get('who') or {}).get('sv') or '-'}
HUR: {(d.get('how') or {}).get('sv') or '-'}
{texts and 'TEXTER:' + chr(10) + blob[:4000] or ''}"""


def main():
    details = json.load(open(os.path.join(HERE, "cache", "rounds_detail.json")))
    emb = json.load(open(os.path.join(HERE, "output", f"ranking_embeddings_{TAG}.json")))

    open_dnrs = [x["dnr"] for x in emb if x["can_apply_now"]]
    closed_top = [x["dnr"] for x in emb if not x["can_apply_now"]][:15]
    targets = open_dnrs + closed_top
    print(f"Bedömer {len(open_dnrs)} öppna + {len(closed_top)} stängda toppkandidater")

    emb_score = {x["dnr"]: x["similarity"] for x in emb}
    results = {}
    BATCH = 5
    for i in range(0, len(targets), BATCH):
        chunk = targets[i:i + BATCH]
        blocks = "\n\n".join(round_block(dnr, details[dnr]) for dnr in chunk)
        user = f"""FÖRETAGSPROFIL:
{PROFIL}

Bedöm dessa {len(chunk)} omgångar mot profilen ovan. Returnera EN JSON-lista
med ett objekt per omgång, i samma ordning, med fälten dnr, tematisk_passform,
eligibility_passform, behovs_driven, motivering, risker.

{blocks}"""
        content, usage = chat(
            [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
            model="default", max_tokens=4000, temperature=0.1,
        )
        try:
            start = content.index("[")
            end = content.rindex("]") + 1
            scored = json.loads(content[start:end])
        except (ValueError, json.JSONDecodeError) as e:
            print(f"  !! JSON-parsefel för batch {i}: {e}\n{content[:300]}")
            continue
        for item in scored:
            item["embedding_similarity"] = emb_score.get(item["dnr"])
            item["title"] = details[item["dnr"]]["title"]
            item["can_apply_now"] = item["dnr"] in open_dnrs
            item["state"] = details[item["dnr"]].get("state")
            item["closing_date"] = details[item["dnr"]].get("closing_date")
            item["funder"] = details[item["dnr"]].get("funder")
            item["totalt"] = (item["tematisk_passform"] * 0.45
                              + item["eligibility_passform"] * 0.4
                              + item["behovs_driven"] * -0.15
                              + item["embedding_similarity"] * 10 * 0.3)
            results[item["dnr"]] = item
        print(f"  batch {i + 1}-{min(i + BATCH, len(targets))} klar "
              f"({usage.get('total_tokens', '?')} tokens)")

    ranked = sorted(results.values(), key=lambda x: -x["totalt"])
    json.dump(ranked, open(OUT, "w"), ensure_ascii=False, indent=1)
    print(f"\n== Rankad (totalt = viktad poäng) ==")
    for r in ranked:
        flag = "ÖPPEN" if r["can_apply_now"] else r["state"]
        print(f"  {r['totalt']:5.2f}  T{r['tematisk_passform']} E{r['eligibility_passform']} "
              f"[{flag:8}] {r['dnr']}  {r['title'][:60]}")


if __name__ == "__main__":
    main()
