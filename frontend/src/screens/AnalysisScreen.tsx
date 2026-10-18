import { useEffect, useMemo, useRef, useState } from "react";
import type { JobState, KravStatus } from "@/lib/api";
import FlySky from "@/components/FlySky";
import { Spinner } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";

const GLYPH: Record<KravStatus | "pending", string> = {
  styrkt_uppfyllt: "✅", okant: "⚪", styrkt_ej_uppfyllt: "⚠️",
  strukturellt: "📋", pending: "",
};
const RANK: Record<string, number> = {
  styrkt_ej_uppfyllt: 4, okant: 3, strukturellt: 2, styrkt_uppfyllt: 1, pending: 0,
};

export default function AnalysisScreen({ title, job }: { title: string; job: JobState | null }) {
  const [statusv, setStatusv] = useState<Record<string, string>>({});
  const [docsDone, setDocsDone] = useState<Record<string, boolean>>({});
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const seenRef = useRef(0);

  // req/doc_done-items → statuskarta (kumulativ)
  useEffect(() => {
    const items = job?.items ?? [];
    const fresh = items.slice(seenRef.current);
    if (!fresh.length) return;
    seenRef.current = items.length;
    setStatusv((old) => {
      let changed = false;
      const next = { ...old };
      for (const it of fresh) {
        if (it.kind === "req" && it.dnr && it.id) { next[`${it.dnr}:${it.id}`] = it.status ?? "pending"; changed = true; }
      }
      return changed ? next : old;
    });
    setDocsDone((old) => {
      let changed = false;
      const next = { ...old };
      for (const it of fresh) {
        if (it.kind === "doc_done" && it.dnr && it.doc) { next[`${it.dnr}:${it.doc}`] = true; changed = true; }
      }
      return changed ? next : old;
    });
  }, [job?.items]);

  const grupper = job?.grupper ?? [];
  const ämnen = useMemo(() => {
    const m: Record<string, typeof grupper> = {};
    for (const g of grupper) (m[g.amne] ??= []).push(g);
    return Object.entries(m);
  }, [grupper]);

  let totalt = 0, gunna = 0;
  grupper.forEach((g) => g.forekomster.forEach((f) => {
    totalt++;
    if (statusv[`${f.dnr}:${f.id}`]) gunna++;
  }));

  const visSkelett = job && (job.phase === "dokumenterar" || job.phase === "granskar");
  const dnrs = (job?.results ?? []).map((r) => r.dnr);

  return (
    <div className="relative min-h-full">
      <FlySky items={job?.items ?? []} />
      <div className="relative z-10 mx-auto w-full max-w-[860px] px-6 py-10">
        <Spinner className="size-6" />
        <h1 className="mt-4 text-[clamp(24px,4vw,34px)]">{title}</h1>
        {totalt > 0 && (
          <p className="mt-3 text-[13px] text-[color:var(--color-muted)]">
            {gunna < totalt ? `Letar bevis — ${gunna}/${totalt} krav prövade …` : `Alla ${totalt} krav prövade`}
          </p>
        )}
        <div className="mt-2 max-h-[26vh] overflow-hidden text-[12.5px] leading-6 text-[color:var(--color-muted)]">
          {(job?.log ?? []).slice(-4).map((l, i) => <div key={i}>· {l}</div>)}
        </div>

        {ämnen.map(([amne, gs]) => (
          <div key={amne} className="mt-5">
            <div className="text-[12px] font-bold uppercase tracking-[0.12em] text-[color:var(--color-accent)]">
              {amne}
            </div>
            <div className="mt-2 space-y-1.5">
              {gs.map((g, i) => {
                const stater = g.forekomster.map((f) => statusv[`${f.dnr}:${f.id}`] ?? "pending");
                const varsta = stater.reduce((a, b) => (RANK[b] > RANK[a] ? b : a), "pending");
                const n = g.forekomster.length;
                const k = `${g.amne}-${i}`;
                const expandera = open[k];
                return (
                  <div key={k}>
                    <button
                      onClick={() => n > 1 && setOpen((o) => ({ ...o, [k]: !o[k] }))}
                      className={cn(
                        "flex w-full cursor-pointer items-start gap-3 rounded-xl border-l-4 bg-white px-4 py-2.5 text-left shadow-sm ring-1 ring-[color:var(--color-line)]/60",
                        varsta === "styrkt_uppfyllt" && "border-[color:var(--color-ok)]",
                        varsta === "styrkt_ej_uppfyllt" && "border-[color:var(--color-bad)]",
                        varsta === "okant" && "border-[#c9beb0]",
                        varsta === "strukturellt" && "border-[#a8a29e]",
                        varsta === "pending" && "border-[#e3ddd0]"
                      )}
                      title={n > 1 ? "klicka för att se varianterna" : g.forekomster[0].id}
                    >
                      <span className="mt-0.5 w-5 shrink-0 text-center">
                        {varsta === "pending" ? <Spinner className="size-3.5" /> : GLYPH[varsta as KravStatus]}
                      </span>
                      <span className="flex-1 text-[13.5px] leading-snug">{g.text}</span>
                      {n > 1 && <Badge variant="warm" className="shrink-0">×{n}</Badge>}
                      <span className="flex shrink-0 flex-wrap gap-1">
                        {[...new Set(g.dnrs)].map((d) => (
                          <span key={d} className="rounded-full bg-[#efe2f4] px-2 py-0.5 text-[10.5px] font-semibold text-[#4a2c57]">
                            {d}
                          </span>
                        ))}
                      </span>
                    </button>
                    {expandera && n > 1 && (
                      <div className="ml-8 mt-1 space-y-1">
                        {g.forekomster.map((f, j) => (
                          <div key={`${f.dnr}-${f.id}-${j}`} className="flex items-start gap-2.5 rounded-lg bg-white px-3 py-1.5 text-[12.5px] ring-1 ring-[color:var(--color-line)]/50">
                            <span className="w-4 text-center">
                              {statusv[`${f.dnr}:${f.id}`] ? GLYPH[statusv[`${f.dnr}:${f.id}`] as KravStatus] : <Spinner className="size-3" />}
                            </span>
                            <span className="rounded-full bg-[#efe2f4] px-1.5 text-[10px] font-semibold text-[#4a2c57]">{f.dnr}</span>
                            <span className="text-[color:var(--color-ink)]/80">{f.text}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ))}

        {visSkelett && dnrs.length > 0 && (
          <div className="mt-8 space-y-2">
            {dnrs.map((d) =>
              ["excel", "ansokan", "granskning"].map((doc) => {
                const id = `${d}:${doc}`;
                const klar = docsDone[id];
                return (
                  <div key={id} className="flex items-center gap-3 rounded-xl border border-[color:var(--color-line)] bg-white px-4 py-3">
                    {klar ? <span>✓</span> : <Spinner className="size-4" />}
                    <span className="text-[13.5px] font-medium">
                      {doc === "excel" ? "📊 Kravmatris (Excel)" : doc === "ansokan" ? "📝 Ansökningshandling" : "🔍 Granskning"} — {d}
                    </span>
                    <span className="ml-auto text-[12px] text-[color:var(--color-muted)]">
                      {klar ? "klar" : "arbetar …"}
                    </span>
                  </div>
                );
              })
            )}
          </div>
        )}
      </div>
    </div>
  );
}
