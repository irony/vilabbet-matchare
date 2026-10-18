"""Thin klient mot Vilabbet-API:n.

Re-exporterar funktionerna från vilabbet_client.py:
- api_get / api_post   — korpus-REST (rounds, requirements, eligibility, ...)
- chat                 — chat/completions mot AI-gateway (default/snabb)
- embed                — embedding-vektorer via gatewayn
- cosine               — cosine-likhet

All autentisering via env: KORPUS_API_URL, KORPUS_TOKEN, AI_BASE_URL, AI_API_KEY.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vilabbet_client import api_get, api_post, chat, cosine, embed  # noqa: E402,F401

__all__ = ["api_get", "api_post", "chat", "embed", "cosine"]
