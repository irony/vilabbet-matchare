import { useState } from "react";
import type { JobState, MatchItem } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

const FIT: Record<string, [string, "ok" | "warm" | "bad" | "default"]> = {
  bra: ["passar bra", "ok"],
  mojlig: ["kan passa", "warm"],
  dalig: ["passar troligen ej", "bad"],
  ej_bedombar: ["ej bedömbar", "default"],
};

export default function PickScreen({
  job, selection, setSelection, onNext,
}: {
  job: JobState;
  selection: Set<string>;
  setSelection: (s: Set<string>) => void;
  onNext: (dnrs: string[]) => Promise<void> | void;
}) {
  const [busy, setBusy] = useState(false);
  const toggle = (m: MatchItem) => {
    const next = new Set(selection);
    if (next.has(m.dnr)) next.delete(m.dnr);
    else if (next.size < 3) next.add(m.dnr);
    setSelection(next);
  };
  return (
    <div className="mx-auto w-full max-w-[900px] px-6 py-14">
      <p className="text-[13px] font-semibold uppercase tracking-[0.14em] text-[color:var(--color-accent)]">
        Matchning för {job.company}{job.orgnr ? ` · org.nr ${job.orgnr}` : ""}
      </p>
      <h1 className="mt-3 text-[clamp(24px,4vw,34px)]">Dessa ligger framåt i tiden — vilka låter roliga?</h1>
      <p className="mt-2 text-[15px] text-[color:var(--color-muted)]">
        Kryssa för upp till tre omgångar så analyserar vi kraven och letar bevis i din textmassa.
      </p>
      {!job.matches?.length && (
        <div className="mt-6 flex items-center gap-3 rounded-2xl border border-dashed border-[color:var(--color-line)] bg-white/60 px-5 py-6 text-[14.5px] text-[color:var(--color-muted)]">
          <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-[color:var(--color-accent)] border-t-transparent" />
          Matchningen mot de 303 öppna utlysningarna kör fortfarande i
          bakgrunden — träffarna landar här automatiskt om några sekunder.
        </div>
      )}
      <div className="mt-6 grid gap-3 md:grid-cols-2">
        {(job.matches ?? []).map((m) => {
          const poang = Math.round(m.matchpoang ?? (m.similarity ?? 0) * 100);
          const selad = selection.has(m.dnr);
          const [fitTxt, fitVariant] = FIT[m.passform ?? ""] ?? [];
          return (
            <Card
              key={m.dnr}
              onClick={() => toggle(m)}
              className={cn(
                "relative cursor-pointer p-4 transition hover:border-[color:var(--color-accent)]",
                selad && "border-[color:var(--color-accent)] ring-2 ring-[color:var(--color-accent)]/25",
                m.passform === "dalig" && "opacity-60"
              )}
            >
              <div className="absolute right-4 top-3.5 text-[19px] font-bold tabular-nums">
                {poang}<span className="text-[12px] text-[color:var(--color-muted)]">%</span>
              </div>
              <div className="pr-14 text-[15px] font-semibold leading-snug">{m.title}</div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                <Badge variant={m.can_apply_now ? "ok" : "default"}>{m.can_apply_now ? "öppen nu" : (m.state ?? "")}</Badge>
                <Badge variant="outline">stänger {String(m.closing_date ?? "").slice(0, 10)}</Badge>
                <Badge variant="outline">{m.funder}</Badge>
                {fitTxt && <Badge variant={fitVariant}>{fitTxt}</Badge>}
              </div>
              {m.varfor && <p className="mt-2.5 text-[13px] leading-snug text-[#374151]">{m.varfor}</p>}
            </Card>
          );
        })}
      </div>
      <div className="mt-7">
        <Button
          disabled={selection.size === 0 || busy}
          onClick={async () => { setBusy(true); await onNext([...selection]); }}
        >
          {busy ? "Hämtar kraven …" : "Analysera valda ↵"}
        </Button>
        <span className="ml-4 text-[13px] text-[color:var(--color-muted)]">{selection.size} valda (max 3)</span>
      </div>
    </div>
  );
}
