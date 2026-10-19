"""Agentisk chatt kring gap-listan och dokumenten i ett demo-jobb.

En agent-loop mot gemma-4 (Bergets gateway) med verktyg:
webbsök (search.dmz.berget.ai), skrapa (firecrawl), bolagssök
(Bolagsverkets register) samt läsa/skriva i jobbets tre dokument
(kravmatris-xlsx, ansökan-md, granskning-xlsx).

Varje skrivåtgärd bygger om xlsx-byten direkt och ogiltigförklarar
jobbets Eurooffice-spårning (_eo_files) — nästa /r-klick laddar
då upp den nya versionen till dokumentredigeraren.
"""
import json
import os
import re
import urllib.parse
import urllib.request

import demo_core
import foretagsregister

AGENT_MODELL = "google/gemma-4-31B-it"
_BERGET_BASE = os.environ.get("BERGET_API_BASE",
                             "https://api.berget.ai/v1").rstrip("/")
_BERGET_KEY = os.environ.get("BERGET_API_KEY", "")
_SEARCH_BASE = "https://search.dmz.berget.ai"


def _berget_chat(messages, model=AGENT_MODELL, max_tokens=2400,
                 temperature=0.15, tools=None, tool_choice=None):
    """Chat completions mot RERETS gateway (där gemma-4 bor)."""
    payload = {"model": model, "messages": messages,
               "max_tokens": max_tokens, "temperature": temperature}
    if tools is not None:
        payload["tools"] = tools
        payload["tool_choice"] = tool_choice or "auto"
    req = urllib.request.Request(
        f"{_BERGET_BASE}/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {_BERGET_KEY}",
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read().decode())
    return data

# ---------------------------------------------------------------- webb/sök

def _webbsök(fråga, antal=5):
    url = (f"{_SEARCH_BASE}/search?"
           + urllib.parse.urlencode({"q": fråga, "limit": min(antal, 20)}))
    req = urllib.request.Request(url, headers={"User-Agent": "vilabbet-agent/1"})
    with urllib.request.urlopen(req, timeout=40) as r:
        respons = json.loads(r.read().decode())
    träffar = (respons.get("hits") or respons.get("results")
               or []) if isinstance(respons, dict) else respons
    return [{"titel": t.get("title"), "url": t.get("url"),
             "snippet": re.sub(r"</?b>", "", t.get("snippet") or "")[:400],
             "match": t.get("match")}
            for t in träffar[:antal]]


def _skrapa(url):
    try:
        r = demo_core._fc("scrape", {"url": url,
                                     "formats": ["markdown"]}, timeout=90)
        data = r.get("data") or r
        md = (data.get("markdown") or "")[:6000]
        return {"url": url, "titel": (data.get("metadata") or {}).get("title"),
                "markdown": md}
    except Exception as e:  # noqa: BLE001
        return {"url": url, "fel": str(e)}


# ---------------------------------------------------------------- job-docs

def _docs_i_jobb(job):
    out = []
    dnrs = [a.get("dnr") for a in (job.get("docs") or {})
            .get("ansokningar", [])]
    for dnr in dnrs:
        out.append({"kind": "ansokan", "dnr": dnr,
                    "beskrivning": "ansökningsutkastet (md)"})
        if (job.get("_excel") or {}).get(dnr):
            out.append({"kind": "excel", "dnr": dnr,
                        "beskrivning": "kravmatrisen (xlsx)"})
        if (job.get("granskning") or {}).get(dnr):
            out.append({"kind": "granskning", "dnr": dnr,
                        "beskrivning": "gap-listan (xlsx)"})
    return out


def _bridge_kravmatris(job, dnr):
    res = next((r for r in (job.get("_results_full") or [])
                if r.get("dnr") == dnr), None)
    if not res:
        return None
    rader = []
    for k in res.get("krav") or []:
        rader.append("| {id} | {typ} | {status} | {text} | {fakta} |"
                     .format(id=k.get("id") or k.get("requirement_id") or "",
                             typ=k.get("typ") or "",
                             status=(k.get("status") or "").replace("_", " "),
                             text=demo_core._korta(k.get("text"), 110),
                             fakta=demo_core._korta(k.get("fakta") or "", 80)))
    return ("| krav-id | typ | status | kravtext | bevis |\n"
            "|---|---|---|---|---|\n" + "\n".join(rader))


def _läs_dok(job, kind, dnr):
    if kind == "ansokan":
        a = next((a for a in (job.get("docs") or {}).get("ansokningar", [])
                  if a.get("dnr") == dnr), None)
        return None if not a else a.get("md", "")[:14000]
    if kind == "excel":
        return _bridge_kravmatris(job, dnr)
    if kind == "granskning":
        g = (job.get("granskning") or {}).get(dnr)
        if not g:
            return None
        rader = []
        for p in g.get("punkter") or []:
            rader.append(f"| {p['nr']} | {p['kategori']} | {p['allvar']} | "
                         f"{demo_core._korta(p.get('beskrivning'), 100)} | "
                         f"{demo_core._korta(p.get('atgard'), 90)} |")
        return ("| nr | kategori | allvar | brist | åtgärd |\n|---|---|---|---|---|\n"
                + "\n".join(rader))
    return None


def _invalidate_eo(job, *nycklar):
    spår = job.get("_eo_files") or {}
    for n in nycklar:
        spår.pop(n, None)


def _bygg_om_excel(job, dnr, ändrade):
    res = next((r for r in (job.get("_results_full") or [])
                if r.get("dnr") == dnr), None)
    if not res:
        return None
    job.setdefault("_excel", {})[dnr] = demo_core.build_kravmatris_xlsx(
        res, job.get("company", ""))
    _invalidate_eo(job, f"excel:{dnr}")
    ändrade.append({"kind": "excel", "dnr": dnr, "info": "kravmatrisen ombyggd"})
    return True


def _bygg_om_granskning(job, dnr, ändrade):
    g = (job.get("granskning") or {}).get(dnr)
    res = next((r for r in (job.get("_results_full") or [])
                if r.get("dnr") == dnr), None)
    if not g or not res:
        return None
    fyllning = (job.get("feedback") or {}).get(dnr)
    job.setdefault("_granskning_xlsx", {})[dnr] = \
        demo_core.bygg_gransknings_xlsx(res, g, job.get("company", ""),
                                        fyllning=fyllning)
    _invalidate_eo(job, f"granskning:{dnr}")
    ändrade.append({"kind": "granskning", "dnr": dnr,
                    "info": "gap-listan ombyggd"})
    return True


# ---------------------------------------------------------------- verktyg

TOOLS = [
    {"type": "function", "function": {
        "name": "webbsök",
        "description": "Sök på svenska webben (Berget index, ~75k sidor) efter "
                       "relevanta källor — Vinnova-sidor, myndigheter, "
                       "organisationer, statistik m.m.",
        "parameters": {"type": "object",
                       "properties": {
                           "fråga": {"type": "string", "description": "sökfrågan"},
                           "antal": {"type": "integer", "default": 5}},
                       "required": ["fråga"]}}},
    {"type": "function", "function": {
        "name": "skrapa",
        "description": "Hämta en specifik webbsida som markdown (t.ex. en "
                       "sida från webbsök eller bolagets egen webb).",
        "parameters": {"type": "object",
                       "properties": {
                           "url": {"type": "string"}},
                       "required": ["url"]}}},
    {"type": "function", "function": {
        "name": "bolagssök",
        "description": "Sök i Bolagsverkets register efter svenska bolag "
                       "(organisationnummer, namn) — bra för att verifiera "
                       "konsortiekandidater eller hitta bolagsnamn.",
        "parameters": {"type": "object",
                       "properties": {
                           "q": {"type": "string", "description": "företagsnamn"}},
                       "required": ["q"]}}},
    {"type": "function", "function": {
        "name": "visa_dok_punktlista",
        "description": "Lista jobbets dokument (kind + dnr) som agenten kan "
                       "läsa/skriva i: ansokan, excel (kravmatris), granskning.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "läs_dok",
        "description": "Läs ett dokuments nuvarande innehåll (ansokan → md; "
                       "excel → kravtabell som markdown; granskning → gap-tabell).",
        "parameters": {"type": "object",
                       "properties": {
                           "kind": {"type": "string",
                                    "enum": ["ansokan", "excel", "granskning"]},
                           "dnr": {"type": "string"}},
                       "required": ["kind", "dnr"]}}},
    {"type": "function", "function": {
        "name": "redigera_ansökan",
        "description": "Ersätt exakt text i ansökningsutkastet (md). Texten måste "
                       "matcha exakt (kopiera från läs_dok). Använd för att sätta "
                       "belopp, datum, partnarnamn o.dyl. i utkastet.",
        "parameters": {"type": "object",
                       "properties": {
                           "dnr": {"type": "string"},
                           "gammal_text": {"type": "string",
                                           "description": "exakt text som finns i utkastet"},
                           "ny_text": {"type": "string",
                                       "description": "ersättningstexten"}},
                       "required": ["dnr", "gammal_text", "ny_text"]}}},
    {"type": "function", "function": {
        "name": "skriv_kravstatus",
        "description": "Uppdatera status/bevis för ett krav i kravmatrisen "
                       "(även kommentar). xlsx byggs om direkt.",
        "parameters": {"type": "object",
                       "properties": {
                           "dnr": {"type": "string"},
                           "krav_id": {"type": "string"},
                           "status": {"type": "string",
                                      "enum": ["styrkt_uppfyllt",
                                               "styrkt_ej_uppfyllt", "okant"]},
                           "fakta": {"type": "string",
                                     "description": "bevis/kommentar för cellen"}},
                       "required": ["dnr", "krav_id", "status"]}}},
    {"type": "function", "function": {
        "name": "markera_granskpunkt",
        "description": "Sätt status på en gap-punkt (som i granskningsformuläret) "
                       "och försörj ombyggnad av gransknings-arket.",
        "parameters": {"type": "object",
                       "properties": {
                           "dnr": {"type": "string"},
                           "nr": {"type": "integer"},
                           "status": {"type": "string",
                                      "enum": ["Ej påbörjad", "Pågår", "Löst",
                                               "Behöver ej"]},
                           "ansvarig": {"type": "string"},
                           "kommentar": {"type": "string"}},
                       "required": ["dnr", "nr", "status"]}}},
]


def _kör_verktyg(job, namn, args, ändrade):
    if namn == "webbsök":
        return _webbsök(args.get("fråga") or "", args.get("antal") or 5)
    if namn == "skrapa":
        return _skrapa(args.get("url") or "")
    if namn == "bolagssök":
        träffar = foretagsregister.search(args.get("q") or "", limit=6)
        return [{"orgnr": t.get("orgnr"), "namn": t.get("namn"),
                 "form": t.get("form")} for t in träffar]
    if namn == "visa_dok_punktlista":
        return _docs_i_jobb(job)
    if namn == "läs_dok":
        data = _läs_dok(job, args.get("kind"), args.get("dnr"))
        if data is None:
            return {"fel": "dokument saknas"}
        return {"innehåll": data}
    if namn == "redigera_ansökan":
        a = next((a for a in (job.get("docs") or {}).get("ansokningar", [])
                  if a.get("dnr") == args.get("dnr")), None)
        if not a:
            return {"fel": "ansökan saknas"}
        gammal, ny = args.get("gammal_text") or "", args.get("ny_text") or ""
        if not gammal or gammal not in a["md"]:
            return {"fel": "texten hittades inte i utkastet — hämta exakt"
                           " stycke via läs_dok first"}
        if a["md"].count(gammal) > 1:
            return {"fel": "texten förekommer flera gånger — välj ett"
                           " längre, unikt utsnitt"}
        a["md"] = a["md"].replace(gammal, ny)
        job.setdefault("_ansokan_docx", {}).pop(args.get("dnr"), None)
        _invalidate_eo(job, f"ansokan:{args.get('dnr')}")
        ändrade.append({"kind": "ansokan", "dnr": args.get("dnr"),
                        "info": f"ersatte '{demo_core._korta(gammal, 30)}…'"})
        return {"ok": True}
    if namn == "skriv_kravstatus":
        res = next((r for r in (job.get("_results_full") or [])
                    if r.get("dnr") == args.get("dnr")), None)
        if not res:
            return {"fel": "omgång saknas"}
        k = next((k for k in res.get("krav") or []
                  if (k.get("id") or k.get("requirement_id"))
                  == args.get("krav_id")), None)
        if not k:
            return {"fel": f"krav {args.get('krav_id')} hittades inte"}
        k["status"] = args.get("status")
        if args.get("fakta"):
            k["fakta"] = args.get("fakta")
        _bygg_om_excel(job, args.get("dnr"), ändrade)
        return {"ok": True}
    if namn == "markera_granskpunkt":
        job.setdefault("feedback", {}).setdefault(
            args.get("dnr"), {"punkter": {}, "kommentar": ""})
        punkt = {"status": args.get("status")}
        for f in ("ansvarig", "kommentar"):
            if args.get(f):
                punkt[f] = args.get(f)
        job["feedback"][args.get("dnr")]["punkter"][str(args.get("nr"))] = punkt
        _bygg_om_granskning(job, args.get("dnr"), ändrade)
        return {"ok": True}
    return {"fel": f"okänt verktyg '{namn}'"}


def agent_svara(job, meddelande, max_rundor=6):
    """En turen i konversationen: användarfråga in → agent-loop med
    verktygsanrop → assistentsvar. Ändringar samlas i `ändrade`."""
    chatlog = job.setdefault("chat", [])
    chatlog.append({"roll": "användare", "innehåll": meddelande})

    company = job.get("company", "bolaget")
    dnrs = ", ".join(a.get("dnr") for a in (job.get("docs") or {})
                     .get("ansokningar", [])) or "(inga dokument klara än)"
    gplus = []
    for dnr, g in (job.get("granskning") or {}).items():
        for p in (g.get("punkter") or [])[:12]:
            rad = (f"- #{p['nr']} [{p['allvar']}] "
                   f"{demo_core._korta(p.get('beskrivning'), 90)}")
            s = p.get("stöd") or {}
            if s.get("organisationer"):
                rad += (" | gapstöd-org: "
                        + ", ".join(s["organisationer"][:8]))
            if s.get("personer"):
                rad += (" | gapstöd-pers: "
                        + ", ".join(s["personer"][:4]))
            if s.get("förslag"):
                rad += f" | gapstöd-förslag: {demo_core._korta(s['förslag'], 110)}"
            gplus.append(rad)
    gap_text = "\n".join(gplus) or "- (ingen gap-lista än)"
    docs = json.dumps(_docs_i_jobb(job), ensure_ascii=False)

    system = f"""Du är en hjälpsam redaktör-assistent för {company}:s
Vinnova-utlysning. Användaren ser gap-listorna och dokumenten i en split-vy
och kan själv redigera i Eurooffice — DU hanterar chattbaserade ändringar,
research och genomgångar.

Jobbets dokument (verksamheter som kan läsas/skrivas): {docs}
Diarienummer i jobbet: {dnrs}

Nuvarande gappunkter (toppen):
{gap_text}

Regler:
- Svara kort och sakligt på svenska.
- Ställ EN fråga åt gången — aldrig numrerade frågelistor. När användaren har
  svarat på en: bekräfta kort vad du gjort/påverkat, gå sedan till exakt EN
  nästa fråga (den mest brådskande öppna gapet).
- Hitta ALDRIG på fakta, namn eller organisationsnummer — använd webbsök/skrapa
  eller bolagssök för att hämta det du saknar, och citera källa (url). Varje
  föreslaget företag MÅSTE verifieras med bolagssök (orgnr) innan du nämner det.
- Gap-stöden i listan ovan kommer från bolagets egna skrapade sidor
  (case/team) — börja ALLTID där när konsortiepartners eller personer
  efterfrågas; komplettera väg webbsök vid behov.
- Vid redigeringar: kör alltid läs_dok först, hämta exakt text, ändra med
  redigera_ansökan / skriv_kravstatus / markera_granskpunkt. Antalet ändrade
  dokument sammanfattas i svaret.
- Lista gärna dokument-relaterade svar kompakt med punkt-punkter.
- Du Kliver inte över till andra jobb eller gör egna beslut; allt ska vara
  förankrat i dokumenten/utlysningen eller verksamheten runt bolaget."""
    messages = [{"role": "system", "content": system}]
    for m in chatlog[-16:]:
        roll = {"användare": "user", "assistent": "assistant"}.get(m["roll"])
        if roll:
            messages.append({"role": roll, "content": m["innehåll"]})

    ändrade, verktygslog, svar_text = [], [], ""
    for _runda in range(max_rundor):
        try:
            data = _berget_chat(messages, tools=TOOLS)
        except Exception as e:  # noqa: BLE001
            job["log"].append(f"⚠️ agent-anrop (tools) misslyckades: {e} — fallback")
            try:
                data = _berget_chat(messages)
            except Exception as e2:  # noqa: BLE001
                svar_text = f"⚠️ agenten fick inget svar: {e2}"
                chatlog.append({"roll": "assistent", "innehåll": svar_text})
                return {"svar": svar_text, "verktyg": [], "ändrade": []}
        val = data["choices"][0]
        msg = val.get("message") or {}
        if msg.get("tool_calls"):
            messages.append({"role": "assistant",
                             "content": msg.get("content") or "",
                             "tool_calls": msg["tool_calls"]})
            for tc in msg["tool_calls"]:
                fn = tc.get("function") or {}
                namn = fn.get("name")
                try:
                    argv = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    argv = {}
                try:
                    res = _kör_verktyg(job, namn, argv, ändrade)
                except Exception as e:  # noqa: BLE001
                    res = {"fel": f"verktyget '{namn}' misslyckades: {e}"}
                    job["log"].append(f"⚠️ agent-verktyg {namn}: {e}")
                verktygslog.append({"verktyg": namn, "args": argv})
                messages.append({"role": "tool",
                                 "tool_call_id": tc.get("id"),
                                 "content": json.dumps(
                                     res, ensure_ascii=False)[:4000]})
            continue
        svar_text = msg.get("content") or ""
        break

    if ändrade:
        svar_text += ("\n\n— ändrade " + str(len(ändrade))
                      + " dokument: "
                      + "; ".join(f"{a['kind']} {a['dnr']} ({a['info']})"
                                  for a in ändrade))
        svar_text += ("\n\n↻ Redigeraren laddar om till nya versionen när du "
                      "klickar 'Öppna i Eurooffice ↗' igen.")
    chatlog.append({"roll": "assistent", "innehåll": svar_text,
                    "verktyg": verktygslog, "ändrade": ändrade})
    job["log"].append(f"💬 Agent: {len(verktygslog)} verktygsanrop, "
                      f"{len(ändrade)} dokument ändrade")
    return {"svar": svar_text, "verktyg": verktygslog, "ändrade": ändrade}


def agent_öppna(job):
    """Proaktiv öppning när chat-vyn visas första gången: agenten sammanfattar
    gap-listorna som en kort samtalsinbjudan — vad som saknas, vilka frågor
    som bör ställas, med gap-stöd-kandidater som förslag direkt i chatten."""
    chatlog = job.setdefault("chat", [])
    if chatlog:
        return None
    company = job.get("company", "bolaget")
    # samla gap-punkter över alla dnrs — blockerare och viktiga lägst 30-rader-fok
    punkter = []
    for dnr, g in (job.get("granskning") or {}).items():
        for p in g.get("punkter") or []:
            if p.get("allvar") in ("blockerare", "viktigt"):
                punkter.append((dnr, p))
    punkter.sort(key=lambda dp: (0 if dp[1].get("allvar") == "blockerare" else 1,
                                 dp[1].get("nr", 99)))
    rader = []
    for dnr, p in punkter[:12]:
        rad = (f"- #{p['nr']} [{p['allvar']}] "
               f"brist: {demo_core._korta(p.get('beskrivning'), 110)} | "
               f"åtgärd: {demo_core._korta(p.get('atgard'), 90)}")
        s = p.get("stöd") or {}
        if s.get("organisationer"):
            rad += f" | kandidater: {', '.join(s['organisationer'][:6])}"
        if s.get("personer"):
            rad += f" | personer: {', '.join(s['personer'][:3])}"
        rader.append(rad)
    gap_text = "\n".join(rader) or "- (inga blockerare/viktiga gap hittade)"
    system = f"""Du börjar precis din första konversation med representanten
för {company}. De har precis fått ett ansökningsutkast, en kravmatris och en
gap-lista per Vinnova-omgång valda för dem. Nu är det din uppgift att
presentera det snabbt och driva samtalet mot att STYDA gap-listorna.

Skriv ett öppningsmeddelande (svenska, ≤220 ord) som:
1. Välkomnar och enradigt säger vad som ligger framför dem (ansökan,
   kravmatris, gap-lista — och att du kan ändra i alla direkt).
2. Nämner de 3–4 MEST brådskande gapen ÖVERSIKTLIGT (max en rad per gap,
   vanlig text) — som sammanhang, INTE som frågelista. Nämna kort
   gap-stöd-kandidater (organisationer/personer) där de finns.
3. Ställ sedan EXAKT EN konkret fråga — den mest brådskande först (oftast
   konsortiepartner eller sökt belopp), gärna med förslag rakt i frågan
   ("vill du ha Leonh AB eller Nordea?").
4. Slutar med en stödjande inbjudan: "vi tar dem en i taget — jag ändrar
   i dokumenten direkt när du svarar".

GAPEN (i prioritetsordning):
{gap_text}"""
    try:
        data = _berget_chat(
            [{"role": "system", "content": system},
             {"role": "user", "content": "Skriv öppningsmeddelandet nu."}],
            max_tokens=600)
        text = (data["choices"][0].get("message") or {}).get("content") or ""
    except Exception as e:  # noqa: BLE001
        text = (f"Hej! Jag hittade ett antal gap i ansökningsutkastet för "
                f"{company}. (Agentens öppning kunde inte nås: {e}). Svara gärna "
                "en i taget — jag ändrar i dokumenten direkt.")
    chatlog.append({"roll": "assistent", "innehåll": text, "öppning": True})
    return {"svar": text}
