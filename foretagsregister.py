#!/usr/bin/env python3
"""Lokal registerkopia av Bolagsverkets 'värdefulla datamängder' (avgiftsfri).

pipelin:
  1. ladda ner bulkfil (eller återanvänd en befintlig zip via --zip)
  2. ström-parsa 988 MB txt direkt ur zip → SQLite med tre index
  3. API: lookup(orgnr) / search(prefix) för autocomplete i demon

Ingen autentisering krävs (EU-beslut 3 feb 2025). Datakälla:
https://vardefulla-datamangder.bolagsverket.se/bolagsverket/bolagsverket_bulkfil.zip

Användning:
  python3 foretagsregister.py --bygg [--zip sökväg.zip]
  python3 foretagsregister.py --sok i-team        # prefixsök autocomplet
  python3 foretagsregister.py --org 5565516928    # exakt slåning
"""
import io
import os
import re
import sqlite3
import sys
import time
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "cache", "foretagsregister.sqlite")
BULK_URL = ("https://vardefulla-datamangder.bolagsverket.se/"
            "bolagsverket/bolagsverket_bulkfil.zip")

FORM_MAP = {"AB-ORGFO": "Aktiebolag", "EF-ORGFO": "Enskild firma",
            "KF-ORGFO": "Kommanditbolag", "KB-ORGFO": "Kommanditbolag",
            "HB-ORGFO": "Handelsbolag", "BRF-ORGFO": "Bostadsrättsförening",
            "I-ORGFO": "Ideell förening", "S-ORGFO": "Stiftelse",
            "EK-ORGFO": "Ekonomisk förening"}


def hämta_bulk(dest, progress=None):
    req = urllib.request.Request(BULK_URL, headers={"User-Agent":
                                                    "vilabbet-check/0.1"})
    with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    return dest


def _wall(fält):
    """Parsar postadress 'Götgatan 18$$STOCKHOLM$11846$SE-LAND'."""
    if not fält:
        return "", "", ""
    delar = fält.split("$")
    delar = [d for d in delar if d]
    gata = delar[0] if delar else ""
    ort = delar[1] if len(delar) > 1 else ""
    postnr = delar[2] if len(delar) > 2 else ""
    return gata, ort, postnr


def bygg_index(zip_path, db_path=DB, progress=print):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    if os.path.exists(db_path):
        os.remove(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""CREATE TABLE bolag (
        orgnr TEXT PRIMARY KEY,     -- 10 siffror, utan bindestreck
        namn TEXT NOT NULL,
        form_kod TEXT, form TEXT,
        reg_datum TEXT, grundat_ar INT,
        avreg_datum TEXT, avveckling INT,          -- 1 om likvidation/rekonstruktion
        verksamhet TEXT,
        gata TEXT, ort TEXT, postnr TEXT)""")
    t0 = time.time()
    n = 0
    cur = conn.cursor()
    with zipfile.ZipFile(zip_path) as z:
        namn_in = z.namelist()[0]
        with z.open(namn_in) as f, io.TextIOWrapper(f, encoding="utf-8-sig",
                                                    errors="ignore") as txt:
            header = txt.readline()  # rubrikrad
            batch = []
            for line in txt:
                line = line.strip().strip('"').replace('";"', "\x01")
                delar = line.split("\x01")
                if len(delar) < 11:
                    continue
                orgnr_full, _nskydd, _land, namn_full, form_kod, avreg, _avrors, pag, reg, verk, adr = delar[:11]
                orgnr = orgnr_full.split("$")[0].strip()
                if not re.fullmatch(r"\d{10}", orgnr):
                    continue
                namn = namn_full.split("$FORETAGSNAMN-ORGNAM$")[0] \
                       .split("$")[0].strip()
                gata, ort, postnr = _wall(adr)
                batch.append((orgnr, namn, form_kod,
                              FORM_MAP.get(form_kod, form_kod or ""),
                              reg, int(reg[:4]) if reg[:4].isdigit() else None,
                              avreg or "", 1 if pag else 0,
                              verk, gata, ort.title(), postnr))
                n += 1
                if len(batch) >= 20000:
                    cur.executemany("INSERT OR IGNORE INTO bolag VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", batch)
                    conn.commit()
                    batch = []
                    progress(f"  {n:,} rader …")
            if batch:
                cur.executemany("INSERT OR IGNORE INTO bolag VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", batch)
                conn.commit()
    progress("  indexerar (namn + orgnr-prefix) …")
    conn.execute("CREATE INDEX idx_namn ON bolag (namn COLLATE NOCASE)")
    conn.execute("CREATE INDEX idx_orgnr ON bolag (orgnr)")
    conn.commit()
    conn.close()
    progress(f"✓ {n:,} bolag indexerade på {time.time() - t0:.0f} s → {db_path}")
    return n


def _conn():
    return sqlite3.connect(DB)


def lookup(orgnr):
    """Slå upp ett bolag exakt på orgnr (med eller utan bindestreck)."""
    digits = re.sub(r"\D", "", orgnr)
    if len(digits) != 10:
        return None
    with _conn() as c:
        row = c.execute(
            "SELECT orgnr,namn,form,grundat_ar,avveckling,ort,verksamhet,reg_datum,avreg_datum,gata,postnr "
            "FROM bolag WHERE orgnr = ?", (digits,)).fetchone()
    if not row:
        return None
    keys = ("orgnr", "namn", "form", "grundat_ar", "avveckling", "ort",
            "verksamhet", "reg_datum", "avreg_datum", "gata", "postnr")
    d = dict(zip(keys, row))
    d["likvidation_eller_rekonstruktion"] = bool(d["avveckling"])
    d["orgnr_pretty"] = f"{d['orgnr'][:6]}-{d['orgnr'][6:]}"
    d["källa"] = "Bolagsverkets officiella register (värdefulla datamängder)"
    return d


def search(q, limit=8):
    """Prefix-autocomplete på bolagsnamn eller orgnr. Returnerar lätta träffar."""
    q = (q or "").strip()
    if len(q) < 2:
        return []
    digits = re.sub(r"\D", "", q)
    like = q.replace("%", "") + "%"
    with _conn() as c:
        if digits and len(digits) >= 3:
            rows = c.execute(
                "SELECT orgnr,namn,form,grundat_ar,ort FROM bolag "
                "WHERE orgnr LIKE ? ORDER BY orgnr LIMIT ?", (digits + "%", limit)).fetchall()
        else:
            rows = c.execute(
                "SELECT orgnr,namn,form,grundat_ar,ort FROM bolag "
                "WHERE namn LIKE ? COLLATE NOCASE ORDER BY namn LIMIT ?", (like, limit)).fetchall()
    return [{"orgnr": f"{o[:6]}-{o[6:]}", "namn": n,
             "form": f, "grundat_ar": g, "ort": ort}
            for o, n, f, g, ort in rows]


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return
    if "--bygg" in args:
        zip_path = None
        if "--zip" in args:
            i = args.index("--zip")
            zip_path = args[i + 1]
        else:
            zip_path = os.path.join(os.path.dirname(DB), "bulkfil.zip")
            if not os.path.exists(zip_path):
                print("laddar ner bulkfil (~251 MB) …")
                hämta_bulk(zip_path)
        bygg_index(zip_path)
        return
    if "--org" in args:
        i = args.index("--org")
        org = args[i + 1]
        import json
        print(json.dumps(lookup(org), ensure_ascii=False, indent=2))
        return
    if "--sok" in args:
        i = args.index("--sok")
        q = args[i + 1] if i + 1 < len(args) else ""
        import json
        print(json.dumps(search(q), ensure_ascii=False, indent=2))
        return


if __name__ == "__main__":
    main()
