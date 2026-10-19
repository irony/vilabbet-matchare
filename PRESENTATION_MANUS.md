# Manus — PPT: "Från sandlåda till agentisk app"
### Hur man bygger Vinnova-matcharen på Vilabbet-sandlådan + Bergets API:er

Målgrupp: tekniskt vana (konsulter, partners, Berget-internt).
Berättelsens kärna: **sandlådan + Bergets API:er räcker från idé till
agentisk slutanvändar-app på en arbetsdag** — utan egen vektordatabas,
utan filhosting, utan dokumentserver-infrastruktur.

---

## Bild 1 — Titel
**Från sandlåda till agentisk app — Vinnova-matcharen med Vilabbet + Bergets API:er**

- Utgångspunkt: Vilabbet-sandlådan (Vinnova-/Formas-/VR-korpus med krav,
  formulärfrågor och fakta per utlysning) och Bergets AI-gateway
  (chat completions med function calling, embeddings, firecrawl-proxy,
  search-index).
- Resultat: en app som tar en mejladress → bolagsmatchning → kravanalys →
  ansökningsutkast → granskning → redigerbart i Eurooffice → agentchatt.
- Öppen, replikerbar arkitektur: `github.com/irony/vilabbet-matchare`.

**Tal**: Vi vill visa att det här är möjligt att bygga som konsult eller
partner — med de byggstenar som finns i sandlådan och hos Berget redan idag.

---

## Bild 2 — Arkitekturen i en bild
- **Vilabbet-sandlådan (REST)**: utlysningar + krav per dnr +
  formulärfrågor + testdata (utförbarhets-vänliga dnr för demos).
- **Bergets AI-gateway**: `/chat/completions` (med tools), `/embeddings`,
  `/firecrawl`-proxy (map/scrape), `search.dmz.berget.ai`
  (hybrid/vektorsök, ~75k svenskt index), Eurooffice/OnlyOffice-redigerare.
- **Tunn FastAPI-session (Python)**: endpoint per fas, in-memory job-state,
  React-SPA som UI. Hela appen får plats i ett repo.

**Tal**: Poängen är att sandlådan är **innehållsrik** (riktiga krav, riktiga
utlysningar) och Bergets redan är **färdig infrastruktur** — vi skriver
ingen vektordatabas, ingen scrape-worker, ingen dokumentserver.

---

## Bild 3 — Flödet i korthet
1. E-post in → domän → **bolagsgissning** (namn ur förstasidan +
   Bolagsverkets register offline) med registerfakta för förtroende
   (orgnr, anställda, omsättning, ort) — innan pipelinen startar.
2. **Embedding-matchning**: bolagsprofil ↔ utlysningar (cosine).
3. **Kravanalys per krav**: bevis letas i bolagets skrapade hemsidesidor.
4. **Ansökningsutkast** genererat per utlysning.
5. **Färska-ögon-granskning** — bolagsblind, som en riktig granskare.
6. **Gap-stöd**: andra varvet — svaren på gap-felen i bolagets egna case-/
   team-sidor (konsortiekandidater, personer/CV-prepar, citat med källa).
7. **Eurooffice + agentchatt**: redigera själv eller be agenten (split-vy).

**Tal**: Varje fas är en separat, testbar enhet — viktigt både för demo och
för att lägga in en kvalitetsgrind mellan stegen.

---

## Bild 4 — Lärdom 1: UX börjar före pipelinen — mejlförst
- Användaren klistrar INTE in URL eller orgnr — mejladressen räcker.
- Servern härleder domän → skrapar förstasidan → namngissning →
  register-autocomplete. Människan väljer bolag, maskinen kör.
- Effekt: "den förstår vem jag är på en sekund" — pipeline-känsla växer.
- Privat domän (gmail etc.) faller tillbaka på URL-fält men visar samma
  gissnings-UI.

**Tal**: Bygg det första beslutet mänskligt — det är billigt och skapar
tillit. Verifiering vis-à-vis registret (inte LLM) bär demo-argumentet.

---

## Bild 5 — Lärdom 2: lokal referensdata + gateway = fullständig stack
- Bolagsverkets register → lokal sqlite (~1,9 milj. bolag, byggd från öppen
  data-post) — namnsök + orgnr direkt, offline.
- Sandlådans krav och formulärfrågor hämtas per dnr via REST.
- Kombinationen **offline-referensdata + färdiga proxytjänster** gör demon
  bärbara — inga dröjande integrationer.

**Tal**: En MVP ska inte kräva integration mot tio tjänster. Spara det man
kan lokalt (det är bara byten med små marginaler) och slå rester mot
färdiga systemservrar.

---

## Bild 6 — Lärdom 3: SPA-sajter kräver länkkrawl — kartan räcker inte
- Firecrawl `/map` kan ge 1 länk på moderna SPA-sajter (vår iteam.se =
  Next.js gav precis detta).
- Fallback: **bredd-först länkkrawl via scrape{markdown,links}** —
  6 pulser, 3 trådar → 8 innehållssidor ändå (räcker för analysen).
- Prioritera därmed URL:er som bär bevis (case, kunder, om-oss, team) —
  prioriteringsmönstret bestämmer vilka bevis som hittas.

**Tal**: Lösningen ligger i hemsideshanteringen, inte i LLM-anropet —
antag aldrig att sajten är crawl-vänlig.

---

## Bild 7 — Lärdom 4: parallellisera redan dag 1
- Skrapa ×4 trådar. Kranvanyls ×3 (batchad). Dokumentbygge ×3 per dnr
  (kravmatris, ansökan, granskning simultant).
- Resultat: hela kedjan ≈ 4 minuter för en runda — snabb nog för live-demo.

**Tal**: I en LLM-värld är väntetiden flaskhalsen, inte skrivhastigheten.
Identifiera beroendegrafen tidigt — det är både snabbare och log-mässigt
rätt.

---

## Bild 8 — Lärdom 5: andra varvet utan ny crawl — gap-stöd
- Färska-ögon-granskningen ger gap-lista: blockerare/viktiga/förslag med
  brist, åtgärd och status-fält.
- **Gap-stöd** = andra varvet: **inga nya scrape-calls** — svaret letas i
  sidorna som redan hämtats vid start-skrapningen.
- Per punkt: top-3 sidor via tema-hintar + nyckelords-överlap → LLM →
  fynd (citat + källa), personer (CV-start), organisationskandidater
  (konsortium), handlingsförslag. Bifogas på punkten.
- Verkligt exempel: konsortie-blockeraren → Leonh/Douglas von Euler-Chelpin,
  Nordea/Swedbank/Skatteverket-case, Skellefteå kommun + LTU-forskare —
  allt hämtat ur bolagets **egna** case-sidor.

**Tal**: Evidence-driven utan ny datakostnad — vi använder mer av samma
redan-skrapade sidor. Gap-listan slutar vara en rapport och blir ett
arbetsregister med inbyggd hjälp.

---

## Bild 9 — Lärdom 6: dokumentredigering utan filhosting
- Problem: OnlyOffice-integration kräver normalt att dokumentservern kan
  dra filen från oss → olämpligt lokalt / bakom NAT.
- Lösning: **Eurooffices example-app**. Servern postar bytes till
  `/example/upload`, redirectar användaren till `/example/editor?fileName=…`.
  Vid nästa nedladdning hämtar servern `/example/download` → senaste
  versionen synkas tillbaka till job-state.
- Ingen JWT, ingen publik URL, ingen reverse-tunnel.
- Docx genereras on-the-fly från ansökan-md (python-docx), kravmatris-/
  gap-ark som xlsx (openpyxl).

**Tal**: Det är OnlyOffice-composability som sätter redigerbarhet två klick
från varje dokument — utan egen Docs-Plugin-infrastruktur.

---

## Bild 10 — Lärdom 7: agentläget — människa och agent delar dokument
- Split-vy ("Lovable-läge"): Eurooffice-redigeraren i iframe till vänster,
  chatt till höger.
- **gemma-4 agent-loop** (Bergets gateway) med 8 verktyg: webbsök, skrapa,
  bolagssök, läs dokument, redigera_ansökan, skriv_kravstatus,
  markera_granskpunkt.
- När agenten skriver: xlsx byggs om direkt + Eurooffice-spårningen
  ogiltigförklaras → iframen laddar ny version automatiskt. Båda
  riktningarna synkar — människan via editorn ("hämta tillbaka"),
  agenten via job-state ("ladda upp ny").
- Direktiv i systemprompten: aldrig hittonda fakta — gap-stöd injicerat,
  varje föreslaget företag måste verifieras via bolagssök innan det nämns,
  citera källa.

**Tal**: Samma disciplin som i alla agentiska UI:er — läs först, ersätt
exakt, verifiera kandidater. Internettestet gav konkret Leonh AB (orgnr
559369-8581) som partnerkandidat + verktygs-logg som bevis för träningsgrupp.

---

## Bild 11 — Lärdom 8: demo-praktikalität — persistence, mejl, synlighet
- Job-state i minnet är snabbt **men** `--reload` eller omstart rensar —
  lösning: pickle-dump var 8:e sekund → laddas vid uppstart.
- Resultatmejl via env-valbar transport (webhook/SMTP, fallback log-only)
  med nedladdningslänkar + ?jobb=-resume-länk direkt in i rätt fas.
- Flow-vy i ReactFlow: grind-band per fas (skrapar→matchar→…→klar) —
  synlig process = demomständig tillit.

**Tal**: Upplevelsen byggs av små hantverksdetaljer: synlig pipeline-
progress, mejl som faktiskt går ut, och state som överlever en omstart.

---

## Bild 12 — Verifierade exempel (kan visas i demo)
- iteam.se: bolagsgissning → registrerat orgnr-val (Iteam Solutions
  Aktiebolag, 556551-6928) — 100 % registerbaserat.
- Kravanalys: 58 krav kollade med bevis ur 8 skrapade sidor.
- Granskning: 9/9 prioriterade gap-punkter fick stöd (org/person/källa).
- Agent: användares "sätt belopp + projektstart, markera gap 2 och 4" →
  korrekt utförda i public job-state + ombyggd xlsx.

**Tal**: Inga mock-data — live-pipeline från mejladress till redigerbar
dokumentbunta i Eurooffice på några minuter.

---

## Bild 13 — Bygg själv (start minutes)
- `git clone irony/vilabbet-matchare`
- `sandbox.env` (ej committad): KORPUS_API_URL/TOKEN (sandlådan) +
  `BERGET_API_KEY`.
- Server: `uv run --with fastapi --with uvicorn --with openpyxl
  --with python-docx --with httpx uvicorn demo_server:app --port 8377`
  → öppna `/app/`.
- Frontend byggs in (React dist mountas i FastAPI).

**Tal**: Stacken är Python + React, inga nya frameworks. Komplexiteten
sidor i byggstenar som är värda att läsa om man ska återskapa det.

---

## Bild 14 — De tre sakerna att ta med sig
1. **Byggstenar > egna micro-API:er** — kravdata, register, sök, scrape,
   redigerare finns redan; koppla dem mot Bergets gateway.
2. **Parallellisera och persista tidigt** — demovärdet ligger i kännliga
   takt (4 min E2E) och i att state överlever.
3. **Låt människa och agent dela samma dokument** — via Eurooffices
   example-app + dokumentknappar; hybridet gör appen brukbar.

**Tal**: Vi byggde detta på en arbetsdag utifrån sandlådan. Förändringen
för er är att återskapandet inte kräver ny infrastruktur — bara koppling.

---

# Bilaga A — Demoförberedelse (fuskkort)

- På start: öppna `/app/` → mejlfältet (iteam-se-domen går snabbast).
- Test-jobb klart att återuppta vid demo: `?jobb=<klart-jobb-id>` —
  restaureras från pkl-state vid omstart.
- Chatt-fraser som alltid visar verktygsarbete:
  - "verifiera Leonh AB i bolagsregistret och svara med orgnr"
  - "sätt sökt belopp till 4 900 000 kr i ansökan" (visa i läs_dok-verktyget)
  - "markera gap #2 och #4 som Pågår med ansvarig Christian"
- Eurooffice-demo: klicka "✒ Öppna i Eurooffice ↗" på kravmatris-kortet
  → kalkyl öppnas; ändra en cell; "↻ ladda om editorn" efter.
