import type { JobState } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useState } from "react";

export default function BevisSumScreen({
  job, onNext, onBack,
}: { job: JobState; onNext: () => Promise<void> | void; onBack: () => void }) {
  const [busy, setBusy] = useState(false);
  return (
    <div className="mx-auto w-full max-w-[800px] px-6 py-14">
      <p className="text-[13px] font-semibold uppercase tracking-[0.14em] text-[color:var(--color-accent)]">
        Steg 2 av bevisarbetet
      </p>
      <h1 className="mt-3 text-[clamp(24px,4vw,34px)]">Bevisläget innan dokumenten</h1>
      {(job.results ?? []).map((r) => (
        <Card key={r.dnr} className="mt-4">
          <CardHeader>
            <CardTitle>{r.title}</CardTitle>
            <Badge variant="outline">{r.dnr}</Badge>
            {r.motor && r.motor.eligible != null && (
              <p className="text-[13.5px] text-[color:var(--color-muted)]">
                regelmotor: eligible={String(r.motor.eligible)}
              </p>
            )}
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2.5">
            <Badge variant="ok">✅ {r.stats.styrkt_uppfyllt ?? 0} styrkta</Badge>
            <Badge variant="warm">❓ {r.stats.okant ?? 0} luckor</Badge>
            <Badge variant="bad">❌ {r.stats.styrkt_ej_uppfyllt ?? 0} felmatch</Badge>
            <Badge>🔧 {r.stats.strukturellt ?? 0} strukturkrav</Badge>
          </CardContent>
        </Card>
      ))}
      <div className="mt-7 flex gap-3">
        <Button variant="outline" onClick={onBack}>← Tillbaka till valet</Button>
        <Button disabled={busy} onClick={async () => { setBusy(true); await onNext(); }}>
          {busy ? "Startar …" : "Ta fram dokumenten ↵"}
        </Button>
      </div>
      <p className="mt-4 text-[12.5px] text-[color:var(--color-muted)]">
        dokumenten är utkast för mänsklig granskning
      </p>
    </div>
  );
}
