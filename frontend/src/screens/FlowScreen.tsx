import { useMemo } from "react";
import {
  Background, Controls, Handle, Position, ReactFlow,
  type Edge, type Node, type NodeProps,
} from "@xyflow/react";
import type { JobState } from "@/lib/api";

/** Interaktiv process-visualisering: domän → crawl → summering → anslag →
  filtrera → krav → beslutsprocesser → bevissum → artefakter → mail.
  Konsumerar job["items"]-strömmen (redan strukturerad i demo_core). */

const KOLUMNER = {
  domän: 0, crawl: 280, summering: 560, anslag: 840, filtrera: 1120,
  krav: 1400, bevis: 1680, bevissum: 1960, artefakt: 2240, mail: 2520,
} as const;
type Lane = keyof typeof KOLUMNER;

const LANE_TITEL: Record<Lane, string> = {
  domän: "Domän", crawl: "Crawling", summering: "Summering",
  anslag: "Hitta anslag", filtrera: "Filtrera & prioritera",
  krav: "Krav per omgång", bevis: "Beslutsprocesser",
  bevissum: "Bevissum", artefakt: "Artefakter", mail: "E-post",
};

const FAS_TILL_LANE: Record<string, Lane> = {
  startad: "domän", skrapar: "crawl", matchar: "filtrera", valet: "anslag",
  hamtar_krav: "krav", kravsum: "krav", analyserar: "bevis",
  bevissum: "bevissum", dokumenterar: "artefakt", granskar: "artefakt",
  klar: "mail",
};

const STATUS_FÄRG: Record<string, string> = {
  styrkt_uppfyllt: "#1a9850", okant: "#d4a017",
  styrkt_ej_uppfyllt: "#c0392b", strukturellt: "#6c5ce7",
};

type VfData = { label: string; sub?: string };
type VfNode = Node<VfData, "vf">;

function VfNodeView({ data }: NodeProps<VfNode>) {
  return (
    <>
      <Handle type="target" position={Position.Left} style={{ opacity: 0 }} />
      <div>
        <div style={{ fontWeight: 600, fontSize: 12.5, lineHeight: 1.25 }}>{data.label}</div>
        {data.sub && (
          <div style={{ marginTop: 3, fontSize: 11.5, color: "var(--color-muted)", lineHeight: 1.25 }}>
            {data.sub}
          </div>
        )}
      </div>
      <Handle type="source" position={Position.Right} style={{ opacity: 0 }} />
    </>
  );
}

const NODE_TYPES = { vf: VfNodeView };

function buildFlow(job: JobState) {
  const items = job.items ?? [];
  const aktivLane: Lane = FAS_TILL_LANE[job.phase] ?? "domän";
  const noder: VfNode[] = [];
  const kanter: Edge[] = [];
  let föregående: string | null = null;
  const laneRäkne = new Map<Lane, number>();

  const lägg = (
    lane: Lane, id: string, label: string, sub: string | undefined,
    opts: { färg?: string; aktiv?: boolean; klar?: boolean; ghost?: boolean } = {},
  ) => {
    const i = laneRäkne.get(lane) ?? 0;
    laneRäkne.set(lane, i + 1);
    noder.push({
      id, type: "vf" as const,
      position: { x: KOLUMNER[lane], y: 30 + i * 112 },
      draggable: false,
      data: { label, sub },
      style: {
        width: 240, padding: "10px 12px",
        background: opts.ghost ? "rgba(255,255,255,.55)" : "white",
        border: `1.5px solid ${opts.aktiv ? "var(--color-accent)" : opts.klar ? "#c6d3e0" : "var(--color-line)"}`,
        borderLeft: `5px solid ${opts.färg ?? (opts.aktiv ? "var(--color-accent)" : opts.klar ? "#9db9d5" : "var(--color-line)")}`,
        borderRadius: 12, fontSize: 12.5,
        opacity: opts.ghost ? 0.65 : 1,
        boxShadow: opts.aktiv
          ? "0 0 0 3px rgba(74, 111, 165, .18)" : "0 2px 10px rgba(20, 30, 50, .05)",
      },
    });
    if (föregående) {
      kanter.push({
        id: `${föregående}→${id}`, source: föregående, target: id,
        animated: lane === aktivLane,
        style: {
          stroke: lane === aktivLane ? "var(--color-accent)" : "#b9c6d6",
          strokeWidth: lane === aktivLane ? 2 : 1.4,
        },
      });
    }
    föregående = id;
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

  // 3. Summering (bolagsprofil)
  lägg("summering", "profil",
       job.profil ? `📇 ${job.company}` : "📇 bolagsprofil",
       job.profil ? String(job.profil).slice(0, 70) : "sammanfattar …",
       { klar: Boolean(job.profil), aktiv: !job.profil && aktivLane === "crawl" });

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

  // 5. Filtrera & prioritera
  lägg("filtrera", "filtrera",
       matcher.length ? `303 → ${matcher.length} visade` : "embedding + AI-poäng",
       job.phase === "matchar" ? "bedömer …" : (job.kravsum?.length ? `${job.kravsum.length} valda för analys` : undefined),
       { klar: matcher.length > 0, aktiv: aktivLane === "filtrera" });

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

  // 7. Beslutsprocesser — en beslutsknut per krav, färg per verdict
  const reqs = items.filter(i => i.kind === "req");
  const ikon: Record<string, string> = {
    styrkt_uppfyllt: "✅", okant: "❓", styrkt_ej_uppfyllt: "❌", strukturellt: "🔧",
  };
  reqs.slice(0, 14).forEach((r, i) =>
    lägg("bevis", `req-${i}`, `${ikon[r.status ?? ""] ?? "▸"} ${(r.title ?? "").slice(0, 46)}`,
         (r.sub ?? "").slice(0, 70),
         { färg: STATUS_FÄRG[r.status ?? ""] ?? "#95a5a6", klar: true,
           aktiv: aktivLane === "bevis" && i === Math.min(reqs.length, 14) - 1 }));
  if (reqs.length > 14)
    lägg("bevis", "req-över", `+ ${reqs.length - 14} krav prövade till`, undefined, { ghost: true, klar: true });
  if (!reqs.length)
    lägg("bevis", "req-väntar", "källkopplad faktasök per krav …", undefined,
         { ghost: true, aktiv: aktivLane === "bevis" });

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

  // 10. E-post
  lägg("mail", "mail",
       job.mail_skickat ? "📧 resultatmail skickat" : "📧 maila resultatet",
       job.mail_skickat ? "länkar levererade" : "går ut när allt är klart",
       { klar: Boolean(job.mail_skickat), ghost: !job.mail_skickat,
         aktiv: aktivLane === "mail" && !job.mail_skickat });

  return { noder, kanter, aktivLane };
}

export default function FlowScreen({ title, job }: { title: string; job: JobState }) {
  const { noder, kanter, aktivLane } = useMemo(() => buildFlow(job), [job]);
  return (
    <div className="flex min-h-full flex-col">
      <div className="flex items-center justify-between gap-4 border-b border-[color:var(--color-line)] bg-white/85 px-6 py-3 backdrop-blur">
        <div className="min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[color:var(--color-accent)]">
            Autonom process — live
          </p>
          <h1 className="truncate text-[17px]">{title}</h1>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-1.5">
          {(Object.keys(KOLUMNER) as Lane[]).map((l) => (
            <span key={l}
              className={`rounded-full px-2 py-0.5 text-[10.5px] uppercase tracking-wide ${
                l === aktivLane
                  ? "bg-[color:var(--color-accent)] text-white"
                  : "bg-[color:var(--color-line)]/60 text-[color:var(--color-muted)]"}`}>
              {LANE_TITEL[l]}
            </span>
          ))}
        </div>
      </div>
      <div className="relative flex-1" style={{ height: "calc(100vh - 58px)" }}>
        <ReactFlow
          nodes={noder}
          edges={kanter}
          nodeTypes={NODE_TYPES}
          fitView
          fitViewOptions={{ padding: 0.08, minZoom: 0.3 }}
          minZoom={0.25}
          maxZoom={1.4}
          elementsSelectable={false}
          proOptions={{ hideAttribution: true }}
        >
          <Background gap={26} size={1.2} color="#e3e9f0" />
          <Controls showInteractive={false} position="bottom-right" />
        </ReactFlow>
        <div className="pointer-events-none absolute left-4 top-3 w-[340px] rounded-xl bg-white/90 px-3.5 py-2.5 shadow-sm ring-1 ring-black/5 backdrop-blur">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-[color:var(--color-muted)]">senaste händelser</p>
          <ul className="mt-1 space-y-0.5">
            {(job.log ?? []).slice(-4).map((r, i) => (
              <li key={i} className="truncate text-[12px] text-[color:var(--color-muted)]">{r}</li>
            ))}
          </ul>
          <p className="mt-1.5 text-[11px] text-[color:var(--color-muted)]">
            {job.items?.filter((i) => i.kind === "req").length ?? 0} krav bevissökta ·{" "}
            {job.items?.filter((i) => i.kind === "page").length ?? 0} sidor
          </p>
        </div>
      </div>
    </div>
  );
}
