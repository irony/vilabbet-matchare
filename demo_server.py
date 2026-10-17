"""Demo-server: Typeform-flöde för utlysningsmatchning.

Kör:  set -a; source sandbox.env; set +a; export BERGET_API_KEY=...
      uv run --with fastapi --with uvicorn uvicorn demo_server:app --port 8377

Flöde: POST /api/start -> job {id, phase}
       GET  /api/job/{id} -> status + data
       POST /api/select -> factfinding + dokument
       GET  /api/download/{job_id}/{doc}.md
"""
import os
import threading
import traceback
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import demo_core

HERE = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(title="Utlysningsmatchning — demo")

JOBS = {}


class StartIn(BaseModel):
    url: str
    orgnr: str | None = None


class SelectIn(BaseModel):
    job_id: str
    dnrs: list[str]


class JobIn(BaseModel):
    job_id: str


def new_job():
    jid = uuid.uuid4().hex[:10]
    JOBS[jid] = {"phase": "startad", "log": [], "items": [],
                 "done": False, "error": None}
    return jid, JOBS[jid]


def logger(job):
    def emit(msg):
        (job["items"] if isinstance(msg, dict) else job["log"]).append(msg)
        if len(job["items"]) > 400:
            del job["items"][:-400]
    return emit


def job_public(job):
    return {k: v for k, v in job.items()
            if k not in ("log", "_company_data", "_bolagsfakta",
                         "_kravobj", "_results_full", "_excel")} | {
        "step": job["log"][-1] if job["log"] else job["phase"],
        "log": job["log"][-8:],
        "items": job["items"],
    }


def run_match(jid, job, url, orgnr):
    try:
        job["phase"] = "skrapar"
        data = demo_core.scrape_company(url, progress=logger(job))
        job["company"] = data["company"]
        job["profil"] = data["profil"]
        job["_company_data"] = data

        bf = demo_core.bolagsfakta_from_sites(data, orgnr=orgnr,
                                              progress=logger(job))
        job["_bolagsfakta"] = bf
        job["orgnr"] = (bf or {}).get("orgnr")
        p = ((bf or {}).get("party") or {})
        reg = (bf or {}).get("registret") or {}
        job["nyckelfakta"] = {
            "orgnr": job.get("orgnr"),
            "namn": p.get("name"),
            "grundat": p.get("founded"),
            "antal_anstallda": p.get("employees"),
            "omsattning_tkr": p.get("turnover_ksek"),
            "balans_tkr": p.get("balance_sheet_total_ksek"),
            "ort": reg.get("ort") or p.get("ort"),
            "form": reg.get("form"),
            "likvidation": reg.get("likvidation_eller_rekonstruktion"),
            "kalla": (bf or {}).get("kalla"),
            "register_driven": bool(reg),
        }

        job["phase"] = "matchar"
        matches = demo_core.match_rounds(data["profil"], max_results=15,
                                         progress=logger(job))
        job["matches"] = matches
        job["phase"] = "valet"          # väntar på användarens val
    except Exception as e:  # noqa: BLE001
        job["error"] = str(e)
        job["phase"] = "fel"
        traceback.print_exc()
    finally:
        job["done"] = True


def run_kravsum(jid, job, dnrs):
    """Fas 1 efter val: hämta de identifierade kraven (ingen LLM-analys)."""
    job["done"] = False
    try:
        job["phase"] = "hamtar_krav"
        kravobj = []
        for i, dnr in enumerate(dnrs, 1):
            job["log"].append(f"Hämtar krav {i}/{len(dnrs)}: {dnr}")
            ko = demo_core.hämta_kravobj(dnr, progress=logger(job))
            if job.get("matches"):
                m = next((m for m in job["matches"] if m["dnr"] == dnr), None)
                ko["varfor"] = (m or {}).get("varfor", "")
                ko["similarity"] = (m or {}).get("matchpoang", 0) / 100 if m else 0
            kravobj.append(ko)
        job["_kravobj"] = kravobj
        job["kravsum"] = [{
            "dnr": k["dnr"], "title": k["title"],
            "closing_date": k["closing_date"], "state": k["state"],
            "funder": k["funder"], "similarity": k.get("similarity", 0),
            "varfor": k.get("varfor", ""),
            "n_krav_totalt": k["n_krav_totalt"],
            "n_relevanta": len(k["krav_objekt"]),
            "krav_preview": [{"type": r["type"], "text": r["text"]}
                             for r in k["krav_objekt"][:8]],
            "krav_full": [{"id": r["requirement_id"], "type": r.get("type"),
                           "text": demo_core._korta(r.get("text"), 160)}
                          for r in k["krav_objekt"]],
        } for k in kravobj]
        job["log"].append("Grupperar snarlika krav ämnessvis …")
        grupper = demo_core.gruppera_krav(kravobj)
        job["grupper"] = grupper
        job["log"].append(
            f"{sum(len(g['forekomster']) for g in grupper)} krav → "
            f"{len(grupper)} unika grupper")
        job["phase"] = "kravsum"
    except Exception as e:  # noqa: BLE001
        job["error"] = str(e)
        job["phase"] = "fel"
        traceback.print_exc()
    finally:
        job["done"] = True


def run_facts(jid, job):
    """Fas 2: bevissökning i den skrapade textmassan (LLM)."""
    job["done"] = False
    try:
        job["phase"] = "analyserar"
        results = []
        kravobj = job["_kravobj"]
        for i, ko in enumerate(kravobj, 1):
            job["log"].append(f"Omgång {i}/{len(kravobj)}: {ko['dnr']}")
            res = demo_core.analysera(job["_company_data"], job.get("_bolagsfakta"),
                                      ko["dnr"], progress=logger(job),
                                      prefetched=ko)
            results.append(res)
        job["results"] = [
            {k: v for k, v in r.items() if k != "krav"}
            | {"krav_sample": r["krav"][:200]} for r in results]
        job["_results_full"] = results
        job["phase"] = "bevissum"
    except Exception as e:  # noqa: BLE001
        job["error"] = str(e)
        job["phase"] = "fel"
        traceback.print_exc()
    finally:
        job["done"] = True


def run_docs(jid, job):
    """Fas 3: per ansökan — kravmatris (Excel) + ansökningshandling (md)."""
    job["done"] = False
    log = logger(job)
    try:
        job["phase"] = "dokumenterar"
        results = job["_results_full"]
        company = job["company"]
        job["_excel"] = {}
        job["docs"] = {"ansokningar": []}
        for res in results:
            dnr = res["dnr"]
            log(f"Bygger kravmatris (Excel) — {dnr}")
            job["_excel"][dnr] = demo_core.build_kravmatris_xlsx(res, company)
            log({"kind": "doc_done", "dnr": dnr, "doc": "excel",
                 "title": f"📊 Kravmatris {dnr}",
                 "sub": f"{len(res['krav'])} kravrader klara"})
            log(f"Skriver ansökningshandling — {dnr}")
            md = demo_core.build_application_doc(job["_company_data"], res,
                                                 progress=log)
            job["docs"]["ansokningar"].append({
                "dnr": dnr, "title": res["title"],
                "filnamn_md": f"ansokan_{company}_{dnr}.md",
                "filnamn_xlsx": f"kravmatris_{company}_{dnr}.xlsx",
                "md": md,
            })
            log({"kind": "doc_done", "dnr": dnr, "doc": "ansokan",
                 "title": f"📝 Ansökningshandling {dnr}",
                 "sub": "utkast för mänsklig granskning"})
        job["phase"] = "klar"
    except Exception as e:  # noqa: BLE001
        job["error"] = str(e)
        job["phase"] = "fel"
        traceback.print_exc()
    finally:
        job["done"] = True


@app.post("/api/start")
def start(inp: StartIn):
    if not inp.url.startswith(("http://", "https://")):
        inp.url = "https://" + inp.url
    jid, job = new_job()
    job["phase"] = "skrapar"
    threading.Thread(target=run_match, args=(jid, job, inp.url, inp.orgnr),
                     daemon=True).start()
    return {"job_id": jid}


@app.get("/api/bolag")
def bolag_search(q: str = ""):
    """Autocomplete mot vår lokala kopia av Bolagsverkets register."""
    try:
        import foretagsregister
        return {"träffar": foretagsregister.search(q)}
    except Exception as e:  # noqa: BLE001
        return {"träffar": [], "varning": f"register ej tillgängligt: {e}"}


@app.get("/api/job/{jid}")
def get_job(jid: str):
    job = JOBS.get(jid)
    if not job:
        raise HTTPException(404, "okänt jobb")
    return job_public(job)


@app.post("/api/select")
def select(inp: SelectIn):
    job = JOBS.get(inp.job_id)
    if not job:
        raise HTTPException(404, "okänt jobb")
    if job["phase"] not in ("valet", "kravsum", "bevissum"):
        raise HTTPException(409, f"jobbet är i fas '{job['phase']}'")
    if not inp.dnrs:
        raise HTTPException(400, "välj minst en omgång")
    inp.dnrs = inp.dnrs[:3]  # håll demon snabbt
    threading.Thread(target=run_kravsum, args=(inp.job_id, job, inp.dnrs),
                     daemon=True).start()
    return {"ok": True, "antal": len(inp.dnrs)}


@app.post("/api/analysera")
def analysera(inp: JobIn):
    job = JOBS.get(inp.job_id)
    if not job:
        raise HTTPException(404, "okänt jobb")
    if job["phase"] != "kravsum":
        raise HTTPException(409, f"jobbet är i fas '{job['phase']}'")
    threading.Thread(target=run_facts, args=(inp.job_id, job),
                     daemon=True).start()
    return {"ok": True}


@app.post("/api/fortsatt")
def fortsatt(inp: JobIn):
    job = JOBS.get(inp.job_id)
    if not job:
        raise HTTPException(404, "okänt jobb")
    if job["phase"] != "bevissum":
        raise HTTPException(409, f"jobbet är i fas '{job['phase']}'")
    threading.Thread(target=run_docs, args=(inp.job_id, job),
                     daemon=True).start()
    return {"ok": True}


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


app.mount("/", StaticFiles(directory=os.path.join(HERE, "demo_static"),
                           html=True), name="static")
