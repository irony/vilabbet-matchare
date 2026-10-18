# vilabbet-matchare

Internt verktyg som matchar ett bolags webbplats mot Vinnovas utlysningskorpus
(Vilabbet) och tar fram en bevisgraderad kravmatris plus ansökningsutkast —
granskad med "färska ögon" innan den lämnas över till en människa.

Repon innehåller två saker: ett litet, återanvändbart **Python-paket** som är
själva produkten, och en **demo-webbapp** (FastAPI + två frontends) som kör
pipelinen mot en sandboxad Vinnova-korpus.

## Vad som är värt att återanvända

| Del | Fil | Kommentar |
|-----|-----|-----------|
| Publik pipeline | `vilabbet/pipeline.py` | `PipelineJob` — hela orkestreringen (`börja`, `välj`, `analysera`, `fortsätt`), fas-maskin, progress-logg, jobb-state. UI-agnostisk. |
| Byggstenar | `vilabbet/byggstenar.py` | ~10 re-exporterade primitives: firecrawl-skrapa, namngissning, profilering (LLM), embedding-matchning, kravanalys, bevissök, ansökningsgenerering, färska-ögon-granskning, Excel-byggare. |
| HTTP-klient | `vilabbet/klient.py` | Tunnt `httpx`-lager mot Vilabbets REST + AI-gateway (re-export av `vilabbet_client.py`). |
| Bolagsregister | `foretagsregister.py` | Hämtar Bolagsverkets fria bulkfil → SQLite (1,94 milj. bolag), autocomplete-sök + orgnr-slåning. Kopplas in i analyser för hårda fakta (grundat år, bolagsform, likvidation). |

Även `demo_core.py` är en guldgruva för exempel på prompt-design och
betygsradering — men den är inte paketerad som API.

## Köra demot

```bash
# 1) hemligheter — aldrig commitas
cp sandbox.env.example sandbox.env  # fyll i BERGET_API_KEY mm.
set -a; source sandbox.env; set +a

# 2) register-databasen (en gång; ~34 s, 720 MB sqlite → cache/)
python3 foretagsregister.py --bygg

# 3) bygg React-frontenden (behövs ej för vanilla-demot)
cd frontend && pnpm install && pnpm build && cd ..

# 4) starta servern
uv run --with fastapi --with uvicorn --with openpyxl \
  uvicorn demo_server:app --host 127.0.0.1 --port 8377
```

Två webbgränssnitt:

- **/** — originaldemot (vanilla JS i `demo_static/index.html`)
- **/app/** — React-frontend (kräver `frontend/dist`, byggs i steg 3)

### Env-variabler (i `sandbox.env`, gitignoras)

- `BERGET_API_KEY` — AI-gateway (modeller `default`/`snabb`/`embedding`)
- `FIRECRAWL_API_KEY` (i `sandbox.env`) — webbskrapning
- Vilabbet REST-creds — se `vilabbet_client.py`

## Flöde

```
arbetsmail (eller webbadress)
  → från_mail (domän → skrapa förstasidan → registerträff → bekräfta org.nr)
  → skrapar   (firecrawl: startsida + undersidor)
  → matchar   (embedding-relevans mot 303 öppna utlysningar → LLM-poängradi)
  → valet     (användaren bocknar i utlysningar)
  → hämtar krav / kravsum (skrapar + grupperar omgångens krav)
  → analyserar (bevissök: styrkt / okant / strukturkrav per krav)
  → bevissum
  → dokumenterar (kravmatris-xlsx + ansökningsutkast-md per utlysning)
  → granskar    (bolagblind LLM: blockerare först) → granskning-xlsx (ifyllbart)
  → klar        (nedladdningar + feedbackformulär som fyller i xlsx)
  → e-post      (resultatmailet med länkar går ut även om fliken stängts)
```

### Mejlförsta-start

Startskärmen ber om arbetsmail (`POST /api/från_mail`): domänen berättar
bolagets webbplats; servern skrapar förstasidan, gissar bolagsnamn och slår i
registret — visar "Vi tror det är **X AB** (org.nr). Är det här bolaget?" med
Ja/alternativ/Nej. Privata domäner (gmail m.fl.) faller tillbaka på att fråga
om webbadress. Mejlen sparas privat i jobbet och används för resultatmailet.

### Redigera i Eurooffice (OnlyOffice-flöde)

Resultatskärmens dokument-kort har klicka "✒ Öppna i Eurooffice ↗" — servern
renderar en OnlyOffice integrationsida (`/r/{jobb}/{excel|ansokan|granskning}/{dnr}`)
som låter `eurooffice.berget.ai` (samma API som ONLYOFFICE Docs) dra filen
från `/r-file/…` och spara tillbaka via `/r-save/…` (callbackUrl). Ansökan
(.md) konverteras till .docx on-the-fly (`python-docx` — lägg med i run-raden).
Redigeringar landar i job-state och därmed i nedladdningslänkarna direkt.

Nyttiga env-variabler:

- `PUBLIC_BASE` — måste nås från eurooffice-servern (i produktion: publikt
  dns-namn; vid lokala live-demos: en tunnel-URL, t.ex. cloudflared quick
  tunnel). Default `http://localhost:8377` (redigeraren ramlar vidare men
  dokumentservern kan ej dra filen).
- `EUROOFFICE_HOST` — default `https://eurooffice.berget.ai`
- `EUROOFFICE_JWT_SECRET` — om OnlyOffice-instansen kräver JWT på configens
  kontraktsområde, sätt den samma hemligheten här (HS256 signeras automatiskt)

Körservern: `--with python-docx` till i uv-kommandot (för ansökan),
`--host 0.0.0.0` om den ska nås utifrån.

### Resultatmail

När jobbet landar i `klar` och mejl angivits går ut ett mail med
nedladdningslänkar + länk tillbaka till resultatsidan (`{base}/app/?jobb=<id>` —
React-appen återupptar jobbet i rätt fas). Transport via env:

| Env | Betydelse |
|-----|-----------|
| `MAIL_WEBHOOK_URL` | POST:ar payload `{till, ämne, bröd, länkar, job_id}` till en webhook (t.ex. n8n) som skickar mailet |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `MAIL_FROM` | smtplib SSL direkt |
| `PUBLIC_BASE` | bas-URL för länkar i mailet (default `http://localhost:8377`) |
| ingen | logg-only: "skulle ha mailat …" (tyst-säkert för lokala demos) |

### Flödesvy (ReactFlow)

Arbets-/analysskärmarna är en interaktiv processkarta (`@xyflow/react`):
domän → crawling (en nod per skrapad sida) → summering → hitta anslag →
filtrera & prioritera → krav per omgång (klusternoder) → beslutsprocesser
(en beslutsknut per krav, färg per verdict + källrad) → bevissum → artefakter
(kravmatris/ansökan/granskning) → e-post. Datan byggs av den strukturerade
`items`-ström som `demo_core` redan producerar — ingen pacing/trickeri bara
live-telemetri. Växla tillbaka till klassisk text-logg: knappen nere till
vänster.

## Restraint-att-tänka-på

- `Systempromptar och nyckelord är skräddarsydda för svensk SMB-kontext och
  ej licensierade för återbruk utanför Berget AI.` (Repo-etikett, kedja med
  företagshemligheter: `sandbox.env` får aldrig committas.)

## Nästa steg (idébank)

- Excel-style siffervalue-downloads (valutakoder) på byggstenar för extern
  export
- Redis/SQLite-persistent job-state (idag in-memory i serverinstansen)
- WebSockets/SSE i stället för 1,5 s-polling på `/api/job/<id>`
- Fortsatt granskning-loop: när användaren sparat feedback ersätts ännu inte
  ansökningstexten av den korrigerade versionen — formuleringssoneten jobbar
  på etikett-nivå
