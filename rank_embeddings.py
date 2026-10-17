"""Steg 2: embeddings-rankning av alla omgångar mot en företagsprofil.

Användning: python3 rank_embeddings.py [--profil profil.txt] [--tag bolag]
"""
import argparse
import json
import os

from vilabbet_client import embed, cosine

HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument("--profil", default="profil.txt")
ap.add_argument("--tag", default="bolag")
args = ap.parse_args()
TAG = args.tag
PROFIL = open(os.path.join(HERE, args.profil)).read().strip()
PROFIL_KEY = f"__profil__:{TAG}"
CACHE = os.path.join(HERE, "cache", "embeddings.json")
OUT = os.path.join(HERE, "output", f"ranking_embeddings_{TAG}.json")


def round_text(d):
    parts = [d.get("title") or ""]
    if d.get("description"):
        parts.append(d["description"])
    for f in ("what", "who", "how"):
        v = (d.get(f) or {}).get("sv")
        if v:
            parts.append(v)
    return "\n".join(parts)[:3000]


def main():
    rounds = json.load(open(os.path.join(HERE, "cache", "rounds_list.json")))
    details = json.load(open(os.path.join(HERE, "cache", "rounds_detail.json")))

    texts = {PROFIL_KEY: PROFIL}
    for r in rounds:
        d = details.get(r["dnr"])
        if d:
            texts[r["dnr"]] = round_text(d)

    cached = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    todo = [k for k, t in texts.items() if k not in cached or cached[k].get("text") != t]
    print(f"{len(cached)} cachade embeddings, {len(todo)} nya att embedda")

    BATCH = 32
    keys = todo
    for i in range(0, len(keys), BATCH):
        chunk = keys[i:i + BATCH]
        vecs = embed([texts[k] for k in chunk])
        for k, v in zip(chunk, vecs):
            cached[k] = {"text": texts[k], "vec": v}
        json.dump(cached, open(CACHE, "w"))
        print(f"  embeddat {min(i + BATCH, len(keys))}/{len(keys)}")

    profil_vec = cached[PROFIL_KEY]["vec"]
    ranking = []
    for r in rounds:
        dnr = r["dnr"]
        if dnr not in cached:
            continue
        sim = cosine(profil_vec, cached[dnr]["vec"])
        st = (details.get(dnr) or {}).get("status") or r.get("status") or {}
        ranking.append({
            "dnr": dnr,
            "title": r["title"],
            "funder": r.get("funder"),
            "similarity": round(sim, 4),
            "state": r.get("state"),
            "can_apply_now": st.get("can_apply_now"),
            "closing_date": r.get("closing_date"),
            "warnings": st.get("warnings", []),
        })
    ranking.sort(key=lambda x: -x["similarity"])
    json.dump(ranking, open(OUT, "w"), ensure_ascii=False, indent=1)
    print(f"\nTopp 25 av {len(ranking)} (cosine similarity):")
    for r in ranking[:25]:
        flag = "ÖPPEN" if r["can_apply_now"] else (r["state"] or "?")
        print(f"  {r['similarity']:.3f}  [{flag:8}] {r['dnr']}  {r['title'][:75]}")


if __name__ == "__main__":
    main()
