"""Steg C+D: Krav- och faktaanalys.

För topp N ur ranking_llm_<tag>.json:
1. Hämtar omgångens krav (eligibility/formal/time/co_financing + kostnadstak)
2. LLM söker svar på varje krav i bolagets skrapade textmassa
3. Kör korpusets eligibility/check (om party_<tag>.json finns) som officiell motor
4. Sparar output/krav_fakta_<tag>.json

Statusvärden per krav:
  styrkt_uppfyllt   – textmassan visar att kravet är uppfyllt (citat)
  styrkt_ej_uppfyllt– textmassan visar att kravet INTE är uppfyllt (citat)
  okant             – textmassan saknar fakta (lucka att fylla)
  strukturellt      – gäller ansökans upplägg/projektidé, inte bolagsfakta
"""
import argparse
import json
import os
import re

from vilabbet_client import api_get, api_post, chat

HERE = os.path.dirname(os.path.abspath(__file__))

TYPER = {"eligibility", "formal", "time", "co_financing"}
KOSTTAK = re.compile(r"(maximalt bidrag|maximal ansökan|högst \d|stödnivå|"
                     r"stodniva|får motsvara|procent av)", re.IGNORECASE)

SYSTEM = """Du är en noggrann faktakontrollant. Du får krav från en svensk
innovationsutlysning och skrapad text från ett företags webbplats.

För VARJE krav ska du avgöra om textmaterialet innehåller fakta som besvarar
det. Svara ENBART utifrån materialet — gissa aldrig.

Statusvärden:
- "styrkt_uppfyllt": materialet visar att kravet är uppfyllt. Ange kort citat.
- "styrkt_ej_uppfyllt": materialet visar att kravet INTE uppfylls. Ange citat.
- "okant": materialet saknar relevant fakta.
- "strukturellt": kravet gäller ansökans/projektets upplägg (konsortium,
  projektplan, underskrifter, budget) och kan inte besvaras av bolagsfakta.

Svara med ENBART en JSON-lista, ett objekt per krav, samma ordning:
{"requirement_id": "...", "status": "...", "fakta": "citat ur materialet eller kort fynd, annars null",
 "kommentar": "max 1 mening eller null"}"""


def korta(text, n=200):
    text = re.sub(r"\s+", " ", (text or "").strip())
    return text if len(text) <= n else text[:n - 1] + "…"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--model", default="default")
    args = ap.parse_args()
    tag = args.tag

    ranking = json.load(open(os.path.join(HERE, "output", f"ranking_llm_{tag}.json")))
    profil = open(os.path.join(HERE, "profiler", f"{tag}_profil.txt")).read()
    raw = json.load(open(os.path.join(HERE, "profiler", f"{tag}_ramaterial.json")))
    party_path = os.path.join(HERE, "profiler", f"{tag}_party.json")
    party = None
    if os.path.exists(party_path):
        party_data = json.load(open(party_path))
        party = party_data.get("payload", party_data)

    material = "\n\n".join(f"[{p['url']}]\n{p['markdown']}" for p in raw["pages"])
    material = material[:24000]

    top = ranking[:args.top]
    result = {"tag": tag, "company": raw["company"], "rounds": []}

    for item in top:
        dnr = item["dnr"]
        print(f"=== {dnr} {item['title'][:55]}")
        reqs_data = api_get(f"/v1/rounds/{dnr}/requirements").get("data", {})
        reqs = reqs_data.get("requirements", reqs_data) if isinstance(reqs_data, dict) else reqs_data
        valda = [r for r in reqs
                 if r.get("type") in TYPER or (r.get("type") == "cost" and KOSTTAK.search(r.get("text") or ""))]
        print(f"  {len(reqs)} krav totalt, {len(valda)} valda "
              f"(eligibility/formal/time/co_financing/kostnadstak)")

        svar = []
        BATCH = 40
        for i in range(0, len(valda), BATCH):
            batch = valda[i:i + BATCH]
            kravlista = "\n".join(
                f'{r["requirement_id"]} [{r.get("type")}{"|obligatoriskt" if r.get("mandatory") else ""}]: '
                f'{korta(r.get("text"))}'
                for r in batch)
            user = f"""BOLAGSPROFIL:
{profil[:2000]}

SKRAPAT MATERIAL FRÅN BOLAGETS WEBBPLATS:
{material}

KRAV ATT BESVARA ({len(batch)} st, omgång {dnr}):
{kravlista}"""
            content, usage = chat(
                [{"role": "system", "content": SYSTEM},
                 {"role": "user", "content": user}],
                model=args.model, max_tokens=6000, temperature=0.0)
            try:
                start = content.index("[")
                end = content.rindex("]") + 1
                svar.extend(json.loads(content[start:end]))
            except (ValueError, json.JSONDecodeError) as e:
                print(f"  !! JSON-fel batch {i}: {e}")
            print(f"  batch {i + 1}-{min(i + BATCH, len(valda))}: {usage.get('total_tokens', '?')} tokens")

        by_id = {s.get("requirement_id"): s for s in svar}
        krav_ut = []
        for r in valda:
            s = by_id.get(r["requirement_id"], {})
            prov = r.get("provenance") or {}
            krav_ut.append({
                "requirement_id": r["requirement_id"],
                "type": r.get("type"),
                "mandatory": r.get("mandatory"),
                "checkable": r.get("checkable"),
                "text": r.get("text"),
                "status": s.get("status", "okant"),
                "fakta": s.get("fakta"),
                "kommentar": s.get("kommentar"),
                "prov_terms_id": prov.get("terms_id"),
                "prov_anchor": prov.get("anchor") or (prov.get("trace") or {}).get("anchor"),
                "prov_quote": korta(prov.get("quote"), 260),
            })

        motor = None
        if party:
            payload = {"round_dnr": dnr, **party}
            try:
                motor = api_post("/v1/eligibility/check", payload).get("data", {})
                motor = {k: motor.get(k) for k in
                         ("eligible", "automatic_count", "not_met_count",
                          "needs_review_count", "explanation", "outcomes", "review")}
            except Exception as e:  # noqa: BLE001
                motor = {"error": str(e)}
            print(f"  motor: eligible={motor.get('eligible')} "
                  f"(auto {motor.get('automatic_count')}, "
                  f"ej uppfyllda {motor.get('not_met_count')}, "
                  f"granskas {motor.get('needs_review_count')})")

        antal = {}
        for k in krav_ut:
            antal[k["status"]] = antal.get(k["status"], 0) + 1
        print(f"  fakta: {antal}")

        result["rounds"].append({
            "dnr": dnr, "title": item["title"], "funder": item.get("funder"),
            "state": item.get("state"), "can_apply_now": item.get("can_apply_now"),
            "closing_date": item.get("closing_date"),
            "totalt": item.get("totalt"), "motivering": item.get("motivering"),
            "risker": item.get("risker"),
            "krav": krav_ut, "stats": antal, "motor": motor,
        })

    out = os.path.join(HERE, "output", f"krav_fakta_{tag}.json")
    json.dump(result, open(out, "w"), ensure_ascii=False, indent=1)
    print(f"\nSparat: {out}")


if __name__ == "__main__":
    main()
