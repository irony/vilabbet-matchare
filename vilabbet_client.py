"""Minimal klient mot Vilabbet REST API + AI-gateway. Bara standardbibliotek."""
import json
import math
import os
import time
import urllib.request
import urllib.error

BASE = os.environ["KORPUS_API_URL"].rstrip("/")
TOKEN = os.environ["KORPUS_TOKEN"]
AI_BASE = os.environ["AI_BASE_URL"].rstrip("/")
AI_KEY = os.environ["AI_API_KEY"]


def _request(url, token, data=None, timeout=60, retries=3):
    body = json.dumps(data).encode() if data is not None else None
    for attempt in range(retries):
        req = urllib.request.Request(url, data=body)
        req.add_header("Authorization", f"Bearer {token}")
        if body:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            detail = e.read().decode()[:300]
            if e.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            raise RuntimeError(f"HTTP {e.code} {url}: {detail}") from e
        except (TimeoutError, ConnectionError, urllib.error.URLError):
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            raise


def api_get(path, **params):
    qs = ""
    if params:
        from urllib.parse import urlencode
        qs = "?" + urlencode({k: v for k, v in params.items() if v is not None})
    return _request(f"{BASE}{path}{qs}", TOKEN)


def api_post(path, payload):
    return _request(f"{BASE}{path}", TOKEN, data=payload, timeout=180)


def embed(texts, model="embedding"):
    """Embeddar en lista texter via gatewayn. Returnerar lista av vektorer."""
    if isinstance(texts, str):
        texts = [texts]
    resp = _request(f"{AI_BASE}/embeddings", AI_KEY,
                    data={"model": model, "input": texts}, timeout=180)
    order = sorted(resp["data"], key=lambda d: d["index"])
    return [d["embedding"] for d in order]


def chat(messages, model="snabb", max_tokens=800, temperature=0.2, response_format=None):
    payload = {"model": model, "messages": messages,
               "max_tokens": max_tokens, "temperature": temperature}
    if response_format:
        payload["response_format"] = response_format
    resp = _request(f"{AI_BASE}/chat/completions", AI_KEY, data=payload, timeout=300)
    choice = resp["choices"][0]["message"]["content"]
    return choice, resp.get("usage", {})


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0
