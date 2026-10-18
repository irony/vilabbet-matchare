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
url/orgnr
  → skrapar   (firecrawl: startsida + några undersidor)
  → matchar   (embedding-relevans mot 303 öppna utlysningar → LLM-poängradi)
  → valet     (användaren bocknar i utlysningar)
  → hämtar krav / kravsum (skrapar + grupperar omgångens krav)
  → analyserar (bevissök: styrkt / okant / strukturkrav per krav)
  → bevissum
  → dokumenterar (kravmatris-xlsx + ansökningsutkast-md per utlysning)
  → granskar    (bolagblind LLM: blockerare först) → granskning-xlsx (ifyllbart)
  → klar        (nedladdningar + feedbackformulär som fyller i xlsx)
```

Bonus: när användaren knappar in domänen i startskärmen gör servern
`POST /api/gissa_bolag` → skrapar förstasidan → gissar bolagsnamn → slår i
registret → föreslår orgnr (med Ja/Nej/alternativ) **innan** flödet startar.

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
