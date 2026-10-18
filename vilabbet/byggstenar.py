"""Byggstenarna — allt som behövs för att bygga egna flöden.

Re-exporter från demo_core så att externa användare slipper bry sig om
intern layout:

- scrape_company         — skrapa bolagswebben (Firecrawl) + bygg profil
- bolagsfakta_from_sites — orgnr → registerverifierade fakta (Bolagsverket)
- match_rounds           — embeddings-grovsil + LLM-poäng (0–100) per omgång
- hämta_kravobj          — relevanta krav per omgång
- gruppera_krav          — embedding-dedup (cosine ≥ .94) + ämnesbuckets
- analysera              — bevissök per omgång + officiell regelmotor
- build_kravmatris_xlsx  — kravmatris-Excel (bytes)
- build_application_doc  — ansökningshandling (markdown)
- granska_ansokan        — färska-ögon-granskning (bolagsblind)
- bygg_gransknings_xlsx  — granskningsformulär som Excel (bytes)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from demo_core import (  # noqa: E402,F401
    analysera,
    bolagsfakta_from_sites,
    build_application_doc,
    build_kravmatris_xlsx,
    bygg_gransknings_xlsx,
    granska_ansokan,
    gruppera_krav,
    hämta_kravobj,
    match_rounds,
    scrape_company,
)

__all__ = [
    "analysera", "bolagsfakta_from_sites", "build_application_doc",
    "build_kravmatris_xlsx", "bygg_gransknings_xlsx", "granska_ansokan",
    "gruppera_krav", "hämta_kravobj", "match_rounds", "scrape_company",
]
