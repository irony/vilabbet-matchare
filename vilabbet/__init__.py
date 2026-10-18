"""Vilabbet-matcharen — återanvändbar pipeline för utlysningsmatchning.

Publikt API (stabla exponeringar):

- :class:`PipelineJob`        — fullständig orkestrering, UI-agnostik
- :class:`VilabbetApiClient`  — via `vilabbet_klient`-modulen (thin httpx-lager)

Alla lågnivå-byggstenar (scrape, profilering, matchning, kravanalys, bevissök,
dokumentgenerering, granskning) finns i `demo_core`. Paketet tänjer dem till
sammansatta, återanvändbara steg med progress-återkoppling.
"""
from . import byggstenar, klient  # noqa: F401
from .pipeline import PHASES, PipelineJob

__version__ = "0.2.0"
__all__ = ["PipelineJob", "PHASES", "byggstenar", "klient", "__version__"]
