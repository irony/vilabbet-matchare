"""Prefetch-cacher — gör demoupplevelsen upplevt mycket snabbare.

Två väntställen i flödet flyger på förhandsbakken:
 1. Sid-crawlen startas så fort användaren valt sitt bolag (orgnr) i
    förstaskärmen — innan knapptrycket på "fortsätt".
 2. Kravhämtningen per dnr startas i bakgrunden för topp-3 matchningarna
    direkt när matchningsskedet är klart, medan användaren står och
    granskar sammanfattningen.

Både skrapning och kravhämtning sparar även progress-strömmen
(str/dict-händelser i samma ordning som _tell skickar dem) så steget
som "ärver" resultatet kan mata in identiskt flöde i jobbets logg/kort
— processvisualiseringen förblir sann.
"""
import threading
import time

TTL_S = 2 * 3600          # cachen lever en demo-session lång
KRAV_ANTAL_PREFETCH = 3   # topp-N matchningar att förhämta krav för

_lock = threading.Lock()
_crawl: dict = {}   # domän -> {ts, state: "pågår"|"klar"|"fel", data, events}
_krav: dict = {}    # dnr   -> {ts, state, ko, events}


def _rensa(cache: dict) -> None:
    for k, v in list(cache.items()):
        if time.time() - v["ts"] > TTL_S:
            del cache[k]


def _färsk(ent) -> bool:
    return bool(ent and ent["state"] == "klar"
                and time.time() - ent["ts"] <= TTL_S)


# ---------------------------------------------------------------- crawl
def domän_av(url: str) -> str:
    host = (url or "").split("//")[-1].split("/")[0].lower()
    return host[4:] if host.startswith("www.") else host


def crawl_starta(url: str) -> bool:
    """Starta (eller starta om sid om cachen är trasig) en bakgrundscrawl
    av domänen. Returnerar True om en tråd sätts igång."""
    import demo_core  # undvik cirkulär import vid modul-laddning
    d = domän_av(url)
    if not d:
        return False
    with _lock:
        _rensa(_crawl)
        ent = _crawl.get(d)
        if ent and ent["state"] != "fel" and time.time() - ent["ts"] <= TTL_S:
            return False  # pågår redan eller färsk — inga dubbletter
        _crawl[d] = {"ts": time.time(), "state": "pågår", "events": []}
    th = threading.Thread(target=_crawl_kör, args=(d, url, demo_core),
                          daemon=True)
    th.start()
    return True


def _crawl_kör(domän: str, url: str, demo_core) -> None:
    buf: list = []
    try:
        data = demo_core.scrape_company(url, progress=buf.append)
        with _lock:
            _crawl[domän] = {"ts": time.time(), "state": "klar",
                             "data": data, "events": buf}
    except Exception:  # noqa: BLE001
        with _lock:
            _crawl[domän]["state"] = "fel"


def crawl_hämta(url: str):
    """Returnerar färsk crawl-entrè ({"data","events"}) eller None."""
    with _lock:
        ent = _crawl.get(domän_av(url))
        return ent if _färsk(ent) else None


# ---------------------------------------------------------------- krav
def krav_starta(dnrs: list) -> int:
    """Kör hämta_kravobj för de KRAV_ANTAL_PREFETCH första dnrs i
    bakgrunden. Returnerar antalet nya trådar som satts igång."""
    import demo_core
    startade = 0
    for dnr in dnrs[:KRAV_ANTAL_PREFETCH]:
        with _lock:
            _rensa(_krav)
            ent = _krav.get(dnr)
            if ent and ent["state"] != "fel" \
                    and time.time() - ent["ts"] <= TTL_S:
                continue
            _krav[dnr] = {"ts": time.time(), "state": "pågår", "events": []}
        threading.Thread(target=_krav_kör, args=(dnr, demo_core),
                         daemon=True).start()
        startade += 1
    return startade


def _krav_kör(dnr: str, demo_core) -> None:
    buf: list = []
    try:
        ko = demo_core.hämta_kravobj(dnr, progress=buf.append)
        with _lock:
            _krav[dnr] = {"ts": time.time(), "state": "klar",
                          "ko": ko, "events": buf}
    except Exception:  # noqa: BLE001
        with _lock:
            _krav[dnr]["state"] = "fel"


def krav_hämta(dnr: str):
    """Returnerar färsk krav-entrè ({"ko","events"}) eller None."""
    with _lock:
        ent = _krav.get(dnr)
        return ent if _färsk(ent) else None
