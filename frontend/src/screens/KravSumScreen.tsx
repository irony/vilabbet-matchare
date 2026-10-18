import type { JobState } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useState } from "react";

export default function KravSumScreen({
  job, onNext, onBack, count,
}: { job: JobState; onNext: () => Promise<void> | void; onBack: () => void; count: number }) {
  const [busy, setBusy] = useState(false);
  return (
    <div className="mx-auto w-full max-w-[800px] px-6 py-14">
      <p className="text-[13px] font-semibold uppercase tracking-[0.14em] text-[color:var(--color-accent)]">
        Steg 1 av bevisarbetet
      </p>
      <h1 className="mt-3 text-[clamp(24px,4vw,34px)]">Kraven vi har identifierat</h1>
      {(job.kravsum ?? []).map((k) => (
        <Card key={k.dnr} className="mt-4">
          <CardHeader>
            <div className="flex items-baseline gap-3">
              <CardTitle>{k.title}</CardTitle>
              <span className="ml-auto text-[19px] font-bold tabular-nums">
                {Math.round((k.similarity ?? 0) * 100)}%
              </span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              <Badge variant="outline">{k.dnr}</Badge>
              <Badge variant="outline">stänger {String(k.closing_date ?? "").slice(0, 10)}</Badge>
              <Badge variant="accent">{k.n_relevanta} relevanta krav av {k.n_krav_totalt} i korpuset</Badge>
            </div>
            {k.varfor && <p className="text-[13px] text-[color:var(--color-muted)]">{k.varfor}</p>}
          </CardHeader>
          <CardContent>
            <ul>
              {k.krav_preview.map((r, i) => (
                <li key={i} className="text-[14px] leading-6 before:mr-2 before:text-[color:var(--color-accent)] before:content-['▸']">
                  {r.text}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ))}
      <div className="mt-7 flex gap-3">
        <Button variant="outline" onClick={onBack}>← Ändra val</Button>
        <Button disabled={busy} onClick={async () => { setBusy(true); await onNext(); }}>
          {busy ? "Startar bevissök …" : `Gå vidare — leta bevis (${count} omgångar) ↵`}
        </Button>
      </div>
      <p className="mt-4 text-[12.5px] text-[color:var(--color-muted)]">
        bevissökningen tar 1–2 minuter per omgång
      </p>
    </div>
  );
}
