"""Steg 1: hämta alla omgångar + detaljer (what/who/how) till cache."""
import json
import os
from concurrent.futures import ThreadPoolExecutor

from vilabbet_client import api_get

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_LIST = os.path.join(HERE, "cache", "rounds_list.json")
CACHE_DETAIL = os.path.join(HERE, "cache", "rounds_detail.json")


def fetch_list():
    if os.path.exists(CACHE_LIST):
        return json.load(open(CACHE_LIST))
    rounds, offset = [], 0
    while True:
        resp = api_get("/v1/rounds", include_inactive="true", limit=100, offset=offset)
        data = resp.get("data", resp)
        if not data:
            break
        rounds.extend(data)
        print(f"  lista: {len(rounds)}/{resp.get('count', '?')}")
        if len(rounds) >= resp.get("count", len(rounds)):
            break
        offset += 100
    json.dump(rounds, open(CACHE_LIST, "w"), ensure_ascii=False)
    return rounds


def fetch_details(rounds):
    done = {}
    if os.path.exists(CACHE_DETAIL):
        done = json.load(open(CACHE_DETAIL))
    todo = [r["dnr"] for r in rounds if r["dnr"] not in done]
    print(f"  detaljer: {len(done)} cachade, {len(todo)} kvar")

    def get_one(dnr):
        resp = api_get(f"/v1/rounds/{dnr}")
        return dnr, resp.get("data", resp)

    with ThreadPoolExecutor(max_workers=8) as pool:
        for i, (dnr, detail) in enumerate(pool.map(get_one, todo)):
            done[dnr] = detail
            if (i + 1) % 25 == 0:
                json.dump(done, open(CACHE_DETAIL, "w"), ensure_ascii=False)
                print(f"  detaljer: {i + 1}/{len(todo)}")
    json.dump(done, open(CACHE_DETAIL, "w"), ensure_ascii=False)
    return done


if __name__ == "__main__":
    rounds = fetch_list()
    print(f"Totalt {len(rounds)} omgångar")
    details = fetch_details(rounds)
    print(f"Detaljer för {len(details)} omgångar")
