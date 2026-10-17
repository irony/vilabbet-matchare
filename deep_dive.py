"""Steg 4: eligibility-check för ett bolag på topp-öppna omgångar + kravlistor."""
import json
import os

from vilabbet_client import api_get, api_post

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "output", "eligibility.json")

# Exempelpart — ersätt med riktiga siffror för bolaget du undersöker.
EXAMPLE_PARTY = {
    "name": "Exempelbolaget AB",
    "legal_form": "limited_company",
    "registration_country": "SE",
    "operations_in_sweden": True,
    "is_research_organisation": False,
    "employees": 2,
    "founded": 2024,
    "turnover_ksek": 1000,
}

TARGETS = ["2025-04831", "2026-01892", "2026-01891"]


def main():
    results = {}
    for dnr in TARGETS:
        print(f"=== {dnr} ===")
        check = api_post("/v1/eligibility/check", {
            "round_dnr": dnr,
            "parties": [EXAMPLE_PARTY],
            "include_review": False,
        })
        data = check.get("data", check)
        summary = {k: v for k, v in data.items()
                   if not isinstance(v, (list, dict))}
        print(json.dumps(summary, ensure_ascii=False, indent=1))
        reqs_data = api_get(f"/v1/rounds/{dnr}/requirements")
        reqs = reqs_data.get("data", reqs_data)
        if isinstance(reqs, dict):
            reqs = reqs.get("requirements", reqs)
        results[dnr] = {"check": data, "requirements_count": len(reqs)
                        if isinstance(reqs, list) else reqs}
        checks = data.get("checks") or data.get("results") or []
        if isinstance(checks, list):
            for c in checks[:40]:
                if isinstance(c, dict):
                    status = c.get("status") or c.get("verdict") or c.get("result") or "?"
                    text = c.get("text") or c.get("requirement") or c.get("label") or ""
                    if status not in ("pass", "ok", "green", True):
                        print(f"  [{status}] {str(text)[:130]}")
        print()
    json.dump(results, open(OUT, "w"), ensure_ascii=False, indent=1)
    print(f"Sparat i {OUT}")


if __name__ == "__main__":
    main()
