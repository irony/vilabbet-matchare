import { useEffect, useMemo, useRef } from "react";
import {
  Background, Controls, Handle, MarkerType, Position, ReactFlow,
  ReactFlowProvider,
  useReactFlow, type Edge, type Node, type NodeProps,
} from "@xyflow/react";
import type { JobState } from "@/lib/api";

/** Interaktiv process-visualisering: domän → crawl → summering → anslag →
  filtrera → krav → beslutsprocesser → bevissum → artefakter → mail.
  Konsumerar job["items"]-strömmen (redan strukturerad i demo_core). */

const KOLUMNER = {
  domän: 0, crawl: 380, summering: 760, anslag: 1140, filtrera: 1520,
  krav: 1900, bevis: 2280, bevissum: 2660, artefakt: 3040, mail: 3420,
} as const;
type Lane = keyof typeof KOLUMNER;

const LANE_TITEL: Record<Lane, string> = {
  domän: "Domän", crawl: "Crawling", summering: "Summering",
  anslag: "Hitta anslag", filtrera: "Filtrera & prioritera",
  krav: "Krav per omgång", bevis: "Beslutsprocesser",
  bevissum: "Bevissum", artefakt: "Artefakter", mail: "E-post",
};

/** Pedagogisk en-radare per band — vad steget gör och varför. */
const LANE_SYFTE: Record<Lane, string> = {
  domän: "Din mejladress pekar ut bolagets webbplats",
  crawl: "Hämtar hemsidesidorna — alla beslut bygger på dem",
  summering: "Kokar sidorna till en bolagsprofil (LLM)",
  anslag: "Embedding-matchar profilen mot alla utlysningar",
  filtrera: "Du väljer vilken utlysning vi analyserar djupt",
  krav: "Utlysningens krav struktureras — vad som måste visas",
  bevis: "Varje krav får bevis ur bolagets sidor (källor)",
  bevissum: "Räknar: styrkt / lucka / felmatch / struktur",
  artefakt: "Tre dokument per omgång: kravmatris, ansökan, gap-lista",
  mail: "Resultatet levereras med länkar till dokumenten",
};

const FAS_TILL_LANE: Record<string, Lane> = {
  startad: "domän", skrapar: "crawl", matchar: "filtrera", valet: "anslag",
  hamtar_krav: "krav", kravsum: "krav", analyserar: "bevis",
  bevissum: "bevissum", dokumenterar: "artefakt", granskar: "artefakt",
  klar: "mail",
};

const STATUS_FÄRG: Record<string, string> = {
  styrkt_uppfyllt: "#2ecc71", okant: "#f1c40f",
  styrkt_ej_uppfyllt: "#e74c3c", strukturellt: "#9b7bff",
};

/* presentations-temat: mörk grön bas + ljusgröna ramar (som slajden) */
const T = {
  bg: "#0b0e0c",
  accent: "#6ff2a8",
  kant: "rgba(140,190,160,.28)",
  kantDim: "rgba(140,190,160,.14)",
  kantKlar: "rgba(140,190,160,.4)",
  text: "#cfe7d8",
  sub: "#77887d",
  dim: "#5f6f66",
  yta: "rgba(17,22,19,.92)",
} as const;

type VfData = { label: string; sub?: string };
type VfNode = Node<VfData, "vf">;

function VfNodeView({ data }: NodeProps<VfNode>) {
  return (
    <>
      <Handle type="target" position={Position.Left} style={{ opacity: 0 }} />
      <div>
        <div style={{ fontWeight: 600, fontSize: 12.5, lineHeight: 1.25, color: T.text }}>{data.label}</div>
        {data.sub && (
          <div style={{ marginTop: 3, fontSize: 11.5, color: T.sub, lineHeight: 1.25 }}>
            {data.sub}
          </div>
        )}
      </div>
      <Handle type="source" position={Position.Right} style={{ opacity: 0 }} />
    </>
  );
}

/** Bakgrunds-band ("grind") per fas: streckad kolumn bakom noderna. */
type BandData = { titel: string; syfte: string; status: "väntar" | "aktiv" | "klar"; bredd: number; höjd: number };
type BandNode = Node<BandData, "band">;

function BandNodeView({ data }: NodeProps<BandNode>) {
  return (
    <div
      style={{
        width: data.bredd, height: data.höjd,
        border: `1.5px dashed ${data.status === "aktiv" ? T.accent : "rgba(140,190,160,.22)"}`,
        borderRadius: 14,
        background: data.status === "aktiv"
          ? "rgba(111,242,168,.055)"
          : data.status === "klar" ? "rgba(120,190,150,.045)" : "transparent",
        padding: 14, pointerEvents: "none",
      }}
    >
      <div style={{
        fontSize: 11.5, fontWeight: 400, textTransform: "uppercase", letterSpacing: "0.18em",
        fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
        color: data.status === "aktiv" ? T.accent : data.status === "klar" ? "#a9bcae" : T.dim,
        textShadow: data.status === "aktiv" ? `0 0 12px ${T.accent}55` : "none",
      }}>
        {data.status === "klar" ? "✓ " : data.status === "aktiv" ? "▶ " : ""}{data.titel}
      </div>
      <div style={{
        marginTop: 4, fontSize: 10.5, fontWeight: 400,
        fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
        color: data.status === "aktiv" ? T.sub : T.dim, lineHeight: 1.3, maxWidth: 240,
        textTransform: "none", letterSpacing: "normal",
      }}>
        {data.syfte}
      </div>
    </div>
  );
}

const NODE_TYPES = { vf: VfNodeView, band: BandNodeView };

function buildFlow(job: JobState) {
  const items = job.items ?? [];
  const aktivLane: Lane = FAS_TILL_LANE[job.phase] ?? "domän";
  const noder: VfNode[] = [];
  const kanter: Edge[] = [];
  const laneRäkne = new Map<Lane, number>();
  // ryggbens-modell: en enda kant per filövergång (sista noden i förra
  // filen → första noden i nästa). Inom filen staplas noder kantfritt —
  // rent och läsbart även när parallella processer fyller på.
  const laneOrdn = Object.keys(KOLUMNER) as Lane[];
  const sistaIFil: Partial<Record<Lane, string>> = {};

  // vad varje band LEVERERAR till nästa steg — pedagogisk etikett på
  // riktnings-kanten ("resultatet av förra grinden")
  const utEtikett: Partial<Record<Lane, string>> = {
    domän: "1 sajt",
  };

  const lägg = (
    lane: Lane, id: string, label: string, sub: string | undefined,
    opts: { färg?: string; aktiv?: boolean; klar?: boolean; ghost?: boolean } = {},
  ) => {
    const i = laneRäkne.get(lane) ?? 0;
    laneRäkne.set(lane, i + 1);
    noder.push({
      id, type: "vf" as const,
      position: { x: KOLUMNER[lane], y: 74 + i * 112 },
      draggable: false,
      data: { label, sub },
      style: {
        width: 240, padding: "10px 12px",
        background: opts.ghost ? "rgba(17,22,19,.6)" : T.yta,
        border: `1.5px solid ${opts.aktiv ? T.accent : opts.klar ? T.kantKlar : T.kantDim}`,
        borderLeft: `4px solid ${opts.färg ?? (opts.aktiv ? T.accent : opts.klar ? "rgba(140,190,160,.5)" : T.kantDim)}`,
        borderRadius: 10, fontSize: 12.5, color: T.text,
        opacity: opts.ghost ? 0.55 : 1,
        boxShadow: opts.aktiv
          ? `0 0 16px ${T.accent}30` : "0 2px 12px rgba(0,0,0,.35)",
      },
    });
    if (i === 0) {
      // första noden i filen → ryggbens-kant från närmaste befolkade fil bakåt
      // (pedagogisk: ut-etiketten visar vad förra steget lämnade över,
      //  pilen visar riktningen "processen rör sig åt höger")
      const idx = laneOrdn.indexOf(lane);
      for (let j = idx - 1; j >= 0; j--) {
        const ofor = sistaIFil[laneOrdn[j]];
        if (ofor) {
          const färj = lane === aktivLane ? T.accent : "#56705f";
          kanter.push({
            id: `${ofor}→${id}`, source: ofor, target: id,
            label: utEtikett[laneOrdn[j]],
            animated: lane === aktivLane,
            labelStyle: {
              fontSize: 10.5, fontWeight: 500, fill: "#9fb3a6",
              fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
            },
            labelBgPadding: [6, 3] as [number, number],
            labelBgBorderRadius: 6,
            labelBgStyle: { fill: "#0f1311", fillOpacity: 0.95, stroke: T.kant },
            markerEnd: { type: MarkerType.ArrowClosed, color: färj, width: 16, height: 16 },
            style: {
              stroke: färj,
              strokeWidth: lane === aktivLane ? 2 : 1.2,
            },
          });
          break;
        }
      }
    }
    sistaIFil[lane] = id;
  };

  // 1. Domän
  lägg("domän", "domän", "🌐 mejl → domän", job.company ?? undefined,
       { klar: true, färg: "#2980b9" });

  // 2. Crawling — upp till 8 sid-noder + stubbe
  const sidor = items.filter(i => i.kind === "page");
  sidor.slice(0, 8).forEach((s, i) =>
    lägg("crawl", `sida-${i}`, `📄 ${s.title}`, (s.sub ?? "").slice(0, 60),
      { klar: true, aktiv: aktivLane === "crawl" && i === Math.min(sidor.length, 8) - 1 }));
  if (sidor.length > 8)
    lägg("crawl", "sida-över", `+ ${sidor.length - 8} sidor till`, undefined, { ghost: true, klar: true });
  if (!sidor.length)
    lägg("crawl", "sida-väntar", "väntar på första sidan …", undefined,
         { ghost: true, aktiv: aktivLane === "crawl" });

  utEtikett.crawl = sidor.length ? `${Math.min(sidor.length, 8)} sidor` : "0 sidor";

  // 3. Summering (bolagsprofil)
  lägg("summering", "profil",
       job.profil ? `📇 ${job.company}` : "📇 bolagsprofil",
       job.profil ? String(job.profil).slice(0, 70) : "sammanfattar …",
       { klar: Boolean(job.profil), aktiv: !job.profil && aktivLane === "crawl" });
  utEtikett.summering = "1 profil";

  // 4. Hitta anslag
  const matcher = items.filter(i => i.kind === "match");
  matcher.slice(0, 8).forEach((m, i) =>
    lägg("anslag", `match-${i}`, `🎯 ${(m.sub ?? "").split("%")[0]} % — ${m.title.slice(0, 36)}`,
         m.sub?.split("·").slice(1).join("·").slice(0, 55), { klar: true }));
  if (!matcher.length)
    lägg("anslag", "match-väntar", "matchar mot 303 omgångar …", undefined,
         { ghost: true, aktiv: aktivLane === "anslag" || aktivLane === "filtrera" });
  else if (matcher.length > 8)
    lägg("anslag", "match-över", `+ ${matcher.length - 8} till`, undefined, { ghost: true, klar: true });

  utEtikett.anslag = matcher.length ? `${Math.min(matcher.length, 8)} träffar` : "0 träffar";

  // 5. Filtrera & prioritera
  lägg("filtrera", "filtrera",
       matcher.length ? `303 → ${matcher.length} visade` : "embedding + AI-poäng",
       job.phase === "matchar" ? "bedömer …" : (job.kravsum?.length ? `${job.kravsum.length} valda för analys` : undefined),
       { klar: matcher.length > 0, aktiv: aktivLane === "filtrera" });
  utEtikett.filtrera = job.kravsum?.length
    ? `${job.kravsum.length} valda` : "1 vald";

  // 6. Krav per omgång
  const kravlistor = items.filter(i => i.kind === "kravlista");
  kravlistor.forEach((k, i) =>
    lägg("krav", `kravlist-${i}`, `📋 ${k.title}`, (k.sub ?? "").slice(0, 70), { klar: true }));
  const nGrupper = job.grupper?.length ?? 0;
  if (nGrupper)
    lägg("krav", "grupper", `🗂 ${nGrupper} unika kravgrupper`,
         `${job.grupper?.reduce((a, g) => a + g.forekomster.length, 0) ?? 0} råkrav dedublicerade`,
         { klar: true });
  if (!kravlistor.length)
    lägg("krav", "krav-väntar", "hämtar kraven …", undefined,
         { ghost: true, aktiv: aktivLane === "krav" });

  // 7. Beslutsprocesser — varje krav börjar som öppen fråga (spöknod)
  //    och morfar om till färgkodat svar när verdicten strömmar in.
  //    Samma node-id ⇒ mjuk övergång. Källa pending: job.kravsum[].krav_full
  const kravFull = (job.kravsum ?? []).flatMap((k) =>
    (k.krav_full ?? []).map((r, i) => ({ ...r, dnr: k.dnr, n: i + 1 })));
  utEtikett.krav = kravFull.length ? `${kravFull.length} krav` : undefined;
  // verdict-meddelanden har ordinal n (position i omgångens kravlista) —
  // robust mot att LLM:ets echo ibland hämtar annonserade id-strängar
  const svarMap = new Map(
    items.filter((i) => i.kind === "req" && typeof i.n === "number")
         .map((i) => [`${i.dnr}|${i.n}`, i]));
  const ikon: Record<string, string> = {
    styrkt_uppfyllt: "✅", okant: "❓", styrkt_ej_uppfyllt: "❌", strukturellt: "🔧",
  };
  const VISIBLA = 12;
  const slots = kravFull.slice(0, VISIBLA);
  const senastBesvaradeIdx = (() => {
    let b = -1;
    slots.forEach((k, i) => { if (svarMap.has(`${k.dnr}|${k.n}`)) b = i; });
    return b;
  })();
  slots.forEach((k, i) => {
    const s = svarMap.get(`${k.dnr}|${k.n}`);
    if (s) {
      lägg("bevis", `bevis-${i}`,
           `${ikon[s.status ?? ""] ?? "▸"} ${(k.text ?? "").slice(0, 46)}`,
           (s.sub ?? "").slice(0, 70),
           { färg: STATUS_FÄRG[s.status ?? ""] ?? "#95a5a6", klar: true,
             aktiv: aktivLane === "bevis" && i === senastBesvaradeIdx });
    } else {
      lägg("bevis", `bevis-${i}`,
           `💭 ${(k.text ?? "").slice(0, 46)}`,
           "letar bevis …",
           { ghost: true, aktiv: aktivLane === "bevis" });
    }
  });
  if (!slots.length)
    lägg("bevis", "req-väntar", "källkopplad faktasök per krav …", undefined,
         { ghost: true, aktiv: aktivLane === "bevis" });
  const besvarade = svarMap.size;
  const totalt = kravFull.length;
  lägg("bevis", "bevis-räknare",
       totalt ? `🧮 ${besvarade} av ${totalt} besvarade` : `${besvarade} besvarade`,
       totalt > VISIBLA ? `visar de ${VISIBLA} första av ${totalt}` : undefined,
       { ghost: totalt > 0 && besvarade < totalt,
         klar: totalt > 0 && besvarade >= totalt });

  utEtikett.bevis = besvarade ? `${besvarade} besvarade` : undefined;

  // 8. Bevissum-summering
  const res = job.results ?? [];
  if (res.length) {
    const s = res.reduce((a, r) => ({
      styrkt: a.styrkt + (r.stats.styrkt_uppfyllt ?? 0),
      okant: a.okant + (r.stats.okant ?? 0),
      ej: a.ej + (r.stats.styrkt_ej_uppfyllt ?? 0),
      struktur: a.struktur + (r.stats.strukturellt ?? 0),
    }), { styrkt: 0, okant: 0, ej: 0, struktur: 0 });
    lägg("bevissum", "bevissum",
         `✅ ${s.styrkt} · ❓ ${s.okant} · ❌ ${s.ej} · 🔧 ${s.struktur}`,
         `${res.length} omgång(ar) bevissökta`, { klar: true, färg: "#1a9850" });
  } else {
    lägg("bevissum", "bevissum-väntar", "bevissummering", undefined,
         { ghost: true, aktiv: aktivLane === "bevissum" });
  }

  // 9. Artefakter — kravmatris / ansökan / granskning per omgång
  const docs = items.filter(i => i.kind === "doc_done");
  const docIkon: Record<string, string> = { excel: "📊", ansokan: "📝", granskning: "🔍" };
  docs.slice(0, 9).forEach((d, i) =>
    lägg("artefakt", `doc-${i}`,
         `${docIkon[d.doc ?? ""] ?? "📦"} ${d.title.replace(/^[^ ]+ /, "").slice(0, 40)}`,
         (d.sub ?? "").slice(0, 55),
         { klar: true, färg: "#6c5ce7",
           aktiv: aktivLane === "artefakt" && i === docs.length - 1 }));
  if (!docs.length)
    lägg("artefakt", "doc-väntar", "kravmatris + ansökan + granskning", undefined,
         { ghost: true, aktiv: aktivLane === "artefakt" });

  utEtikett.artefakt = docs.length ? `${docs.length} dokument` : undefined;

  // 10. E-post
  lägg("mail", "mail",
       job.mail_skickat ? "📧 resultatmail skickat" : "📧 maila resultatet",
       job.mail_skickat ? "länkar levererade" : "går ut när allt är klart",
       { klar: Boolean(job.mail_skickat), ghost: !job.mail_skickat,
         aktiv: aktivLane === "mail" && !job.mail_skickat });

  // bakgrunds-band per fas — "grinden" som visar var i processen vi är
  const bandNoder: BandNode[] = laneOrdn.map((lane) => {
    const antal = laneRäkne.get(lane) ?? 0;
    const höjd = Math.max(antal * 112 + 132, 300);
    const idx = laneOrdn.indexOf(lane);
    const aktIdx = laneOrdn.indexOf(aktivLane);
    const status: BandData["status"] = idx < aktIdx ? "klar" : idx === aktIdx ? "aktiv" : "väntar";
    return {
      id: `band-${lane}`, type: "band" as const,
      position: { x: KOLUMNER[lane] - 54, y: 0 },
      draggable: false, selectable: false, focusable: false,
      zIndex: -1,
      data: { titel: LANE_TITEL[lane], syfte: LANE_SYFTE[lane], status, bredd: 348, höjd },
    };
  });

  return { noder: [...bandNoder, ...noder] as Node[], kanter, aktivLane, antalPerFil: Object.fromEntries(laneRäkne) };
}

function FlowInner({ title, job }: { title: string; job: JobState }) {
  const { noder, kanter, aktivLane } = useMemo(() => buildFlow(job), [job]);
  const { fitView, setCenter } = useReactFlow();
  const förraFilen = useRef<string | null>(null);
  // inbäddningsläge (?ren=1): bara grafen — ingen header, logg eller knappar
  const ren = new URLSearchParams(window.location.search).get("ren") === "1";

  // vid fasbyte: zooma mjukt till den aktiva grinden ("var är vi nu?")
  // — inte i inbäddningsläget, där hela flödet alltid ska synas
  useEffect(() => {
    if (ren) return;
    if (förraFilen.current === aktivLane) return;
    förraFilen.current = aktivLane;
    const x = KOLUMNER[aktivLane] + 160;
    const t = setTimeout(() => {
      setCenter(x, 380, { zoom: 0.92, duration: 750 });
    }, 120);
    return () => clearTimeout(t);
  }, [aktivLane, setCenter]);

  // en gång per nytt jobb: börja i översikt
  const jobStart = useRef<string>("");
  useEffect(() => {
    const nyckel = [
      job.items?.length ?? 0, job.phase,
      (job.items ?? []).slice(0, 1).map(i => i.title).join(),
    ].join(":");
    if (jobStart.current && jobStart.current !== nyckel &&
        (job.items?.length ?? 0) <= 2 && job.phase === "skrapar") {
      fitView({ duration: 500, padding: 0.1, minZoom: 0.25 });
    }
    jobStart.current = nyckel;
  }, [job, fitView]);

  // inbäddningsläge (?ren=1): bara grafen — ingen header, logg eller knappar

  return (
    <div className="flex min-h-full flex-col" style={{ background: T.bg }}>
      {!ren && (
        <div className="flex items-center justify-between gap-4 px-6 py-3"
             style={{ borderBottom: `1px solid ${T.kantDim}`, background: "rgba(11,14,12,.9)" }}>
          <div className="min-w-0">
          <p className="font-mono text-[11px] uppercase"
             style={{ color: T.accent, letterSpacing: "0.22em" }}>
            Autonom process — översiktsvy
          </p>
            <h1 className="truncate text-[17px]" style={{ color: "#e6efe9" }}>{title}</h1>
          </div>
          <div className="flex flex-wrap items-center justify-end gap-1.5">
            {(Object.keys(KOLUMNER) as Lane[]).map((l) => (
              <span key={l}
                className="rounded-full px-2 py-0.5 font-mono text-[10px] uppercase"
                style={{
                  letterSpacing: "0.08em",
                  border: `1px solid ${l === aktivLane ? T.accent : T.kantDim}`,
                  color: l === aktivLane ? T.accent : T.dim,
                  background: l === aktivLane ? "rgba(111,242,168,.08)" : "transparent",
                }}>
                {LANE_TITEL[l]}
              </span>
            ))}
          </div>
        </div>
      )}
      <div className={ren ? "relative" : "relative flex-1"}
           style={{
             height: ren ? "100vh" : "calc(100vh - 58px)",
             background: [
               "radial-gradient(1300px 520px at 50% 118%, rgba(60,160,110,.10), transparent 62%)",
               "repeating-linear-gradient(115deg, transparent 0 46px, rgba(120,190,150,.045) 46px 47px)",
               "repeating-linear-gradient(65deg, transparent 0 46px, rgba(120,190,150,.045) 46px 47px)",
               T.bg,
             ].join(", "),
           }}>
        <ReactFlow
          nodes={noder}
          edges={kanter}
          nodeTypes={NODE_TYPES}
          colorMode="dark"
          fitView
          fitViewOptions={{ padding: 0.1, minZoom: 0.25 }}
          minZoom={0.25}
          maxZoom={1.4}
          elementsSelectable={false}
          proOptions={{ hideAttribution: true }}
          style={{ background: "transparent" }}
        >
          <Background gap={46} size={1} color="rgba(120,190,150,.10)" />
          {!ren && <Controls showInteractive={false} position="bottom-right" />}
        </ReactFlow>
        {!ren && (
        <div className="pointer-events-none absolute left-4 top-3 w-[340px] rounded-xl px-3.5 py-2.5 backdrop-blur"
             style={{ background: "rgba(15,19,17,.88)", border: `1px solid ${T.kantDim}` }}>
          <p className="font-mono text-[10.5px] uppercase" style={{ color: T.dim, letterSpacing: "0.18em" }}>
            senaste händelser
          </p>
          <ul className="mt-1 space-y-0.5">
            {(job.log ?? []).slice(-4).map((r, i, a) => (
              <li key={i} className="truncate font-mono text-[11px]"
                  style={{ color: i === a.length - 1 ? "#9fc4ad" : T.dim }}>
                <span style={{ color: "#42524a" }}>$ </span>{r}
              </li>
            ))}
          </ul>
          <p className="mt-1.5 font-mono text-[10.5px]" style={{ color: T.dim }}>
            {job.items?.filter((i) => i.kind === "req").length ?? 0} krav bevissökta ·{" "}
            {job.items?.filter((i) => i.kind === "page").length ?? 0} sidor
          </p>
        </div>
        )}
        {!ren && (
          <button
            onClick={() => fitView({ duration: 550, padding: 0.08, minZoom: 0.22 })}
            className="absolute bottom-4 right-4 z-10 rounded-full px-3.5 py-1.5 font-mono text-[12px] hover:opacity-90"
            style={{ border: `1px solid ${T.kant}`, color: "#9fb3a6", background: "transparent" }}
          >⇱ passa in</button>
        )}
      </div>
    </div>
  );
}

export default function FlowDetail(props: { title: string; job: JobState }) {
  return (
    <ReactFlowProvider>
      <FlowInner {...props} />
    </ReactFlowProvider>
  );
}
