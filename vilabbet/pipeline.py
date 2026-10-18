"""PipelineJob — återanvändbar orkestrering av hela matchningspipelinen.

UI-agnostisk: all interaktion går via job-state + progress-callbacks. Används
av demo_server (FastAPI/polling), men kan lika gärna köras från CLI, en
batch eller ett annat ramverk:

    job = PipelineJob(url="https://exempel.se", orgnr="556000-0000")
    job.börja()                     # skrapar → matchar → valet
    ...visa job["matches"] för användaren...
    job.välj(["2025-04831"])        # hamtar_krav → kravsum (grupperade krav)
    job.analysera()                 # analyserar → bevissum (bevissökning)
    job.fortsätt()                  # dokumenterar → granskar → klar (docs)

Job-state är en ren dict (JSON-vänlig) med kända fält: phase, log, items,
company, orgnr, nyckelfakta, profil, matches, kravsum, grupper, results,
docs, granskning, feedback, done, error.

Faser (job["phase"]):
    startad → skrapar → matchar → valet →  (användare väljer)
    hamtar_krav → kravsum →                (användare bekräftar)
    analyserar → bevissum →                (användare bekräftar)
    dokumenterar → granskar → klar
    (fel om något går snett)
"""
import os
import sys
import traceback
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import demo_core  # noqa: E402

PHASES = ("startad", "skrapar", "matchar", "valet", "hamtar_krav", "kravsum",
          "analyserar", "bevissum", "dokumenterar", "granskar", "klar", "fel")

# fält i job-state som inte exponeras publikt (interna rådata/binärer)
PRIVATE_KEYS = ("log", "_company_data", "_bolagsfakta", "_kravobj",
                "_results_full", "_excel", "_granskning_xlsx", "_email")


def new_job_state():
    jid = uuid.uuid4().hex[:10]
    job = {"phase": "startad", "log": [], "items": [], "done": False,
           "error": None}
    return jid, job


def public_view(job):
    """Oförändrad dict men utan interna fält; utökad med step/log-svans."""
    return {k: v for k, v in job.items() if k not in PRIVATE_KEYS} | {
        "step": job["log"][-1] if job["log"] else job["phase"],
        "log": job["log"][-8:],
        "items": job["items"],
    }


class PipelineJob:
    """Håller all tillståndsdatan + progress-callbacks för ett jobb.

    on_log(str)  — stödjande händelser (mänsklig läsbar rad)
    on_item(dict) — visuella kort-objekt {kind, title, sub, ...}
    """

    def __init__(self, job, on_log=None, on_item=None):
        self.job = job
        self._on_log = on_log
        self._on_item = on_item

    # ------------------------------------------------------- progress
    def logg(self, msg):
        (self.job["items"] if isinstance(msg, dict) else
         self.job["log"]).append(msg)
        if len(self.job["items"]) > 400:
            del self.job["items"][:-400]
        callback = self._on_item if isinstance(msg, dict) else self._on_log
        if callback:
            callback(msg)

    def _fel(self, e):
        self.job["error"] = str(e)
        self.job["phase"] = "fel"
        traceback.print_exc()

    # ------------------------------------------------------- steg
    def börja(self, url, orgnr=None):
        """Skrapar webbplatsen, bygger bolagsprofil och matchar mot 303
        omgångar. Slutfas: 'valet'."""
        try:
            self.job["phase"] = "skrapar"
            data = demo_core.scrape_company(url, progress=self.logg)
            self.job["company"] = data["company"]
            self.job["profil"] = data["profil"]
            self.job["_company_data"] = data

            bf = demo_core.bolagsfakta_from_sites(data, orgnr=orgnr,
                                                  progress=self.logg)
            self.job["_bolagsfakta"] = bf
            self.job["orgnr"] = (bf or {}).get("orgnr")
            p = ((bf or {}).get("party") or {})
            reg = (bf or {}).get("registret") or {}
            self.job["nyckelfakta"] = {
                "orgnr": self.job.get("orgnr"),
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

            self.job["phase"] = "matchar"
            self.job["matches"] = demo_core.match_rounds(
                data["profil"], max_results=15, progress=self.logg)
            self.job["phase"] = "valet"
        except Exception as e:  # noqa: BLE001
            self._fel(e)
        finally:
            self.job["done"] = True
        return self.job

    def välj(self, dnrs):
        """Upp till 3 omgångar: hämtar de identifierade kraven och
        grupperar snarlika krav. Slutfas: 'kravsum'."""
        self.job["done"] = False
        try:
            self.job["phase"] = "hamtar_krav"
            kravobj = []
            for i, dnr in enumerate(dnrs, 1):
                self.logg(f"Hämtar krav {i}/{len(dnrs)}: {dnr}")
                ko = demo_core.hämta_kravobj(dnr, progress=self.logg)
                if self.job.get("matches"):
                    m = next((m for m in self.job["matches"]
                              if m["dnr"] == dnr), None)
                    ko["varfor"] = (m or {}).get("varfor", "")
                    ko["similarity"] = (m or {}).get("matchpoang", 0) / 100 \
                        if m else 0
                kravobj.append(ko)
            self.job["_kravobj"] = kravobj
            self.job["kravsum"] = [{
                "dnr": k["dnr"], "title": k["title"],
                "closing_date": k["closing_date"], "state": k["state"],
                "funder": k["funder"], "similarity": k.get("similarity", 0),
                "varfor": k.get("varfor", ""),
                "n_krav_totalt": k["n_krav_totalt"],
                "n_relevanta": len(k["krav_objekt"]),
                "krav_preview": [{"type": r["type"], "text": r["text"]}
                                 for r in k["krav_objekt"][:8]],
                "krav_full": [{"id": r["requirement_id"],
                               "type": r.get("type"),
                               "text": demo_core._korta(r.get("text"), 160)}
                              for r in k["krav_objekt"]],
            } for k in kravobj]
            self.logg("Grupperar snarlika krav ämnessvis …")
            grupper = demo_core.gruppera_krav(kravobj)
            self.job["grupper"] = grupper
            self.logg(f"{sum(len(g['forekomster']) for g in grupper)} krav → "
                      f"{len(grupper)} unika grupper")
            self.job["phase"] = "kravsum"
        except Exception as e:  # noqa: BLE001
            self._fel(e)
        finally:
            self.job["done"] = True
        return self.job

    def analysera(self):
        """Bevissökning för alla valda omgångar i den skrapade textmassan
        (LLM-källa-kopplad faktasökning). Slutfas: 'bevissum'."""
        self.job["done"] = False
        try:
            self.job["phase"] = "analyserar"
            results = []
            kravobj = self.job["_kravobj"]
            for i, ko in enumerate(kravobj, 1):
                self.logg(f"Omgång {i}/{len(kravobj)}: {ko['dnr']}")
                res = demo_core.analysera(self.job["_company_data"],
                                          self.job.get("_bolagsfakta"),
                                          ko["dnr"], progress=self.logg,
                                          prefetched=ko)
                results.append(res)
            self.job["results"] = [
                {k: v for k, v in r.items() if k != "krav"}
                | {"krav_sample": r["krav"][:200]} for r in results]
            self.job["_results_full"] = results
            self.job["phase"] = "bevissum"
        except Exception as e:  # noqa: BLE001
            self._fel(e)
        finally:
            self.job["done"] = True
        return self.job

    def fortsätt(self):
        """Per ansökan: kravmatris (Excel) + ansökningshandling (md),
        därefter färska-ögon-granskning av utkastet. Slutfas: 'klar'."""
        self.job["done"] = False
        try:
            self.job["phase"] = "dokumenterar"
            results = self.job["_results_full"]
            company = self.job["company"]
            self.job["_excel"] = {}
            self.job["docs"] = {"ansokningar": []}
            for res in results:
                dnr = res["dnr"]
                self.logg(f"Bygger kravmatris (Excel) — {dnr}")
                self.job["_excel"][dnr] = demo_core.build_kravmatris_xlsx(
                    res, company)
                self.logg({"kind": "doc_done", "dnr": dnr, "doc": "excel",
                           "title": f"📊 Kravmatris {dnr}",
                           "sub": f"{len(res['krav'])} kravrader klara"})
                self.logg(f"Skriver ansökningshandling — {dnr}")
                md = demo_core.build_application_doc(
                    self.job["_company_data"], res, progress=self.logg)
                self.job["docs"]["ansokningar"].append({
                    "dnr": dnr, "title": res["title"],
                    "filnamn_md": f"ansokan_{company}_{dnr}.md",
                    "filnamn_xlsx": f"kravmatris_{company}_{dnr}.xlsx",
                    "md": md,
                })
                self.logg({"kind": "doc_done", "dnr": dnr, "doc": "ansokan",
                           "title": f"📝 Ansökningshandling {dnr}",
                           "sub": "utkast för mänsklig granskning"})
            # --- färska-ögon-granskning, bolagsblind ---
            self.job["phase"] = "granskar"
            self.job["granskning"] = {}
            self.job["_granskning_xlsx"] = {}
            for res in results:
                dnr = res["dnr"]
                md = next((a["md"] for a in self.job["docs"]["ansokningar"]
                           if a["dnr"] == dnr), "")
                try:
                    g = demo_core.granska_ansokan(res, md, progress=self.logg)
                except Exception as e:  # noqa: BLE001
                    g = {"sammanfattning": f"Granskningen misslyckades: {e}",
                         "punkter": [], "antal": {}}
                g["filnamn_xlsx"] = f"granskning_{company}_{dnr}.xlsx"
                self.job["granskning"][dnr] = g
                self.job["_granskning_xlsx"][dnr] = \
                    demo_core.bygg_gransknings_xlsx(res, g, company)
                self.logg({"kind": "doc_done", "dnr": dnr, "doc": "granskning",
                           "title": f"🔍 Granskning {dnr}",
                           "sub": f"{len(g['punkter'])} punkter — "
                                  f"{(g.get('antal') or {}).get('blockerare', 0)} "
                                  f"blockerare"})
            self.job["phase"] = "klar"
        except Exception as e:  # noqa: BLE001
            self._fel(e)
        finally:
            self.job["done"] = True
        return self.job
