"""Demo-server: tunn FastAPI-oöskörning över vilabbet-paketet.

Kör:  set -a; source sandbox.env; set +a
      uv run --with fastapi --with uvicorn --with openpyxl \\
        uvicorn demo_server:app --port 8377

Flöde: POST /api/start → job {id, phase}
       GET  /api/job/{id} → state + data (pollar)
       POST /api/select → väljer upp till 3 omgångar
       POST /api/analysera → bevissökning
       POST /api/fortsatt → dokument + granskning
       GET  /api/download/{job_id}/excel|ansokan|granskning
        GET  /api/bolag?q= → autocomplete (Bolagsverkets register)
        POST /api/gissa_bolag → domän → skrapa 1 sida → namn → registerträffar
"""
import os
import re
import sys
import threading
import traceback

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import demo_core  # noqa: E402
from vilabbet import PipelineJob  # noqa: E402
from vilabbet.pipeline import new_job_state, public_view  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(title="Utlysningsmatchning — demo")

JOBS = {}


class StartIn(BaseModel):
    url: str
    orgnr: str | None = None
    email: str | None = None


class SelectIn(BaseModel):
    job_id: str
    dnrs: list[str]


class JobIn(BaseModel):
    job_id: str


class FeedbackIn(BaseModel):
    job_id: str
    dnrs: dict          # dnr -> {"punkter": {nr: {...}}, "kommentar": str}


def _run_in_thread(fn, *args):
    threading.Thread(target=fn, args=args, daemon=True).start()


def _job_or_404(inp: JobIn):
    job = JOBS.get(inp.job_id)
    if not job:
        raise HTTPException(404, "okänt jobb")
    return job


@app.post("/api/start")
def start(inp: StartIn):
    if not inp.url.startswith(("http://", "https://")):
        inp.url = "https://" + inp.url
    jid, job = new_job_state()
    JOBS[jid] = job
    job["phase"] = "skrapar"
    if inp.email:
        job["_email"] = inp.email.strip().lower()
    pj = PipelineJob(job)
    _run_in_thread(pj.börja, inp.url, inp.orgnr)
    return {"job_id": jid, "phase": "skrapar"}


@app.get("/api/bolag")
def bolag_search(q: str = ""):
    """Autocomplete mot vår lokala kopia av Bolagsverkets register."""
    try:
        import foretagsregister
        return {"träffar": foretagsregister.search(q)}
    except Exception as e:  # noqa: BLE001
        return {"träffar": [], "varning": f"register ej tillgängligt: {e}"}


class GissaIn(BaseModel):
    url: str


def _rensa_gissning(s: str) -> str:
    """Title/h1 till sårent bolagssök-ord: första segmentet före | – — : ;"""
    s = re.split(r"[|–—:;·•]", s)[0].strip()
    return re.sub(r"\s+\(?Konsult(ing)?\)?$", "", s, flags=re.I).strip()


@app.post("/api/gissa_bolag")
def gissa_bolag(inp: GissaIn):
    """Domän → skrapa 1 sida → bolagsnamn-gissning → registersök.

    Används av startskärmen för att föreslå orgnr direkt: användaren skriver
    in webbadressen, vi skrapar förstasidan (og:site_name/title/h1/domän),
    letar i Bolagsverkt-registret, och returnerar upp till 3 träffar att
    bekräfta eller pröva själva.
    """
    url = inp.url if inp.url.startswith(("http://", "https://")) else "https://" + inp.url
    domän = re.sub(r"https?://(www\.)?", "", url).split("/")[0]
    return _gissa_från_domän(domän, url=url)


def _gissa_från_domän(domän: str, url: str | None = None) -> dict:
    """Skrapa 1 sida på domänen och leta bolag i registret.

    Returnerar {"namn_gissning", "träffar", "url"}.
    """
    import foretagsregister
    url = url or ("https://" + domän)
    md, meta = "", {}
    try:
        r = demo_core._fc("scrape", {"url": url, "formats": ["markdown"],
                                     "onlyMainContent": True})
        d = r.get("data") or {}
        md = d.get("markdown") or ""
        meta = d.get("metadata") or {}
    except Exception:  # noqa: BLE001
        md, meta = "", {}

    kandidater: list[str] = []
    for nyckel in ("og:site_name", "ogSiteName", "title"):
        v = meta.get(nyckel)
        if v:
            kandidater.append(str(v))
    h1 = re.search(r"^#\s+(.+?)\s*$", md, re.M)
    if h1:
        kandidater.append(h1.group(1))
    if domän:
        kandidater.append(domän.split(".")[0])

    def sok(namn: str):
        t = foretagsregister.search(namn, limit=3)
        if not t and " " in namn:
            t = foretagsregister.search(namn.split()[0], limit=3)
        return t

    for kand in kandidater:
        namn = _rensa_gissning(kand)
        if len(namn) >= 2:
            träffar = sok(namn)
            if träffar:
                return {"namn_gissning": namn, "träffar": träffar,
                        "url": url}
    namn = _rensa_gissning(kandidater[0]) if kandidater else None
    return {"namn_gissning": namn, "träffar": [], "url": url}


# domäner vars e-post inte berättar något om bolagets webbplats
PRIVATA_EPOSTDOMÄNER = {
    "gmail.com", "googlemail.com", "hotmail.com", "hotmail.se",
    "outlook.com", "live.com", "live.se", "msn.com", "icloud.com",
    "me.com", "mac.com", "yahoo.com", "yahoo.se", "proton.me",
    "protonmail.com", "aol.com", "telia.com", "comhem.se",
    "bredband.net", "bredband2.se", "tele2.se", "telenor.se",
    "spray.se", "passagen.se", "swipnet.se",
}


class MailIn(BaseModel):
    email: str


@app.post("/api/från_mail")
def från_mail(inp: MailIn):
    """E-postadress → domän → bolagsgissning.

    Startskärmed v-2: användaren svarar bara på sin arbetsmail. Domänen
    berättar nästan alltid bolagets webbplats; privat domän (gmail etc.)
    faller tillbaka på att fråga om webbadressen direkt.
    """
    mail = inp.email.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", mail):
        raise HTTPException(400, "ogiltig e-postadress")
    domän = mail.split("@")[-1]
    if domän in PRIVATA_EPOSTDOMÄNER:
        return {"ok": False, "privat_domän": True, "domän": domän}
    svar = _gissa_från_domän(domän)
    svar["ok"] = True
    svar["domän"] = domän
    return svar


@app.get("/api/job/{jid}")
def get_job(jid: str):
    job = JOBS.get(jid)
    if not job:
        raise HTTPException(404, "okänt jobb")
    return public_view(job)


@app.post("/api/select")
def select(inp: SelectIn):
    job = _job_or_404(inp)
    if job["phase"] not in ("valet", "kravsum", "bevissum"):
        raise HTTPException(409, f"jobbet är i fas '{job['phase']}'")
    if not inp.dnrs:
        raise HTTPException(400, "välj minst en omgång")
    inp.dnrs = inp.dnrs[:3]  # håll demon snabbt
    _run_in_thread(PipelineJob(job).välj, inp.dnrs)
    return {"ok": True, "antal": len(inp.dnrs)}


@app.post("/api/analysera")
def analysera(inp: JobIn):
    job = _job_or_404(inp)
    if job["phase"] != "kravsum":
        raise HTTPException(409, f"jobbet är i fas '{job['phase']}'")
    _run_in_thread(PipelineJob(job).analysera)
    return {"ok": True}


@app.post("/api/fortsatt")
def fortsatt(inp: JobIn):
    job = _job_or_404(inp)
    if job["phase"] != "bevissum":
        raise HTTPException(409, f"jobbet är i fas '{job['phase']}'")
    jid = inp.job_id

    def _fortsätt_och_maila():
        PipelineJob(job).fortsätt()
        if job["phase"] == "klar" and job.get("_email"):
            _maila_klar(jid, job)

    _run_in_thread(_fortsätt_och_maila)
    return {"ok": True}


# --- resultatmail: transport styrs av env ---
#   MAIL_WEBHOOK_URL       → POST:ar payload till en webhook (t.ex. n8n) som mailar
#   SMTP_HOST/PORT/USER/PASS/FROM → smtplib SSL direkt
#   PUBLIC_BASE            → bas-URL för nedladdningslänkar (default localhost)
#   ingen av dessa → logg-only ("skulle ha mailat …") så demot är tyst-säkert
def _maila_klar(jid: str, job: dict):
    """Mailar nedladdningslänkarna om användaren angett e-post.

    Körs när förstatt-tråden landar i 'klar'. Avsedd för fallet att användaren
    stängt fliken: jobbet rullar färdigt server-side, mailet landar ändå.
    """
    import json
    import urllib.request
    base = os.environ.get("PUBLIC_BASE", "http://localhost:8377").rstrip("/")
    emails = [a for a in (job.get("docs") or {}).get("ansokningar", [])]
    länkar = []
    for a in emails:
        länkar.append(f"Kravmatris {a['dnr']}: "
                      f"{base}/api/download/{jid}/excel/{a['dnr']}.xlsx")
        länkar.append(f"Ansökning {a['dnr']}: "
                      f"{base}/api/download/{jid}/ansokan/{a['dnr']}.md")
        länkar.append(f"Granskning {a['dnr']}: "
                      f"{base}/api/download/{jid}/granskning/{a['dnr']}.xlsx")
    payload = {
        "till": job["_email"],
        "ämne": f"Dina Vinnova-dokument för {job.get('company', '')} är klara",
        "bröd": ("Hej!\n\nDin matchning är färdig. Ladda hem dokumenten "
                 "(länkarna gäller så länge demot körs):\n\n"
                 + "\n".join(f"- {l}" for l in länkar)
                 + f"\n\nGranska ansökan på: {base}/app/?jobb={jid}\n"
                   "Granskningsformuläret på resultatsidan återifyller "
                   "matrisen när ni gått igenom den internt.\n\n"
                   "Vänliga hälsningar,\nVinnova-matcharen"),
        "job_id": jid,
        "länkar": länkar,
    }
    hook = os.environ.get("MAIL_WEBHOOK_URL")
    try:
        if hook:
            req = urllib.request.Request(
                hook, data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                job["log"].append(f"📧 Resultatmail skickat via webhook → "
                                  f"{job['_email']} ({resp.status})")
        elif os.environ.get("SMTP_HOST"):
            import smtplib
            from email.message import EmailMessage
            m = EmailMessage()
            m["From"] = os.environ.get("MAIL_FROM", "noreply@localhost")
            m["To"] = payload["till"]
            m["Subject"] = payload["ämne"]
            m.set_content(payload["bröd"])
            with smtplib.SMTP_SSL(
                os.environ["SMTP_HOST"],
                int(os.environ.get("SMTP_PORT", "465")),
                timeout=20,
            ) as s:
                if os.environ.get("SMTP_USER"):
                    s.login(os.environ["SMTP_USER"],
                            os.environ.get("SMTP_PASS", ""))
                s.send_message(m)
            job["log"].append(f"📧 Resultatmail skickat → {job['_email']}")
        else:
            job["log"].append(
                f"📧 (mail utan konfiguration — skulle ha mailat "
                f"{job['_email']} med {len(länkar)} nedladdningslänkar)")
        job["_mail_skickat"] = True
        job["mail_skickat"] = True   # publik status för flödesvyn
        job["items"].append({"kind": "mail",
                             "title": f"📧 Resultatmail → {job['_email']}",
                             "sub": f"{len(länkar)} nedladdningslänkar"})
    except Exception as e:  # noqa: BLE001
        job["log"].append(f"⚠️ Resultatmail misslyckades: {e}")


@app.post("/api/feedback")
def feedback(inp: FeedbackIn):
    """Sparar det ifyllda granskningsformuläret (per ansökan)."""
    job = JOBS.get(inp.job_id)
    if not job:
        raise HTTPException(404, "okänt jobb")
    job.setdefault("feedback", {})
    n = 0
    for dnr, data in inp.dnrs.items():
        job["feedback"][dnr] = data
        n += len((data.get("punkter") or {}) if isinstance(data, dict) else {})
    job["log"].append(f"Granskningsformulär sparat — {n} svar ifyllda")
    return {"ok": True, "svar": n}


@app.get("/api/download/{jid}/excel/{dnr}.xlsx")
def dl_excel(jid: str, dnr: str):
    job = JOBS.get(jid)
    data = (job or {}).get("_excel", {}).get(dnr)
    if not data:
        raise HTTPException(404)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument"
                   ".spreadsheetml.sheet",
        headers={"Content-Disposition":
                 f'attachment; filename="kravmatris_{job["company"]}_{dnr}.xlsx"'})


@app.get("/api/download/{jid}/ansokan/{dnr}.md", response_class=PlainTextResponse)
def dl_ansokan(jid: str, dnr: str):
    job = JOBS.get(jid)
    if not job or not job.get("docs"):
        raise HTTPException(404)
    a = next((a for a in job["docs"]["ansokningar"] if a["dnr"] == dnr), None)
    if not a:
        raise HTTPException(404)
    return PlainTextResponse(a["md"], media_type="text/markdown; charset=utf-8")


@app.get("/api/download/{jid}/granskning/{dnr}.xlsx")
def dl_granskning(jid: str, dnr: str):
    """Granskningsformuläret som Excel; återifyllt om formuläret sparats."""
    job = JOBS.get(jid)
    g = (job or {}).get("granskning", {}).get(dnr)
    res = next((r for r in (job or {}).get("_results_full", [])
                if r["dnr"] == dnr), None) if job else None
    if not g or not res:
        raise HTTPException(404)
    fyllning = ((job.get("feedback") or {}).get(dnr)) if job else None
    if fyllning:
        data = demo_core.bygg_gransknings_xlsx(res, g, job["company"],
                                               fyllning=fyllning)
    else:
        data = job["_granskning_xlsx"].get(dnr)
    if not data:
        raise HTTPException(404)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument"
                   ".spreadsheetml.sheet",
        headers={"Content-Disposition":
                 f'attachment; filename="granskning_{job["company"]}_{dnr}.xlsx"'})


# React-app (byggd från frontend/, se README) — fallback: vanilla-demon
_REACT_DIST = os.path.join(HERE, "frontend", "dist")
if os.path.isdir(_REACT_DIST):
    app.mount("/app", StaticFiles(directory=_REACT_DIST, html=True),
              name="react-app")

app.mount("/", StaticFiles(directory=os.path.join(HERE, "demo_static"),
                           html=True), name="static")
