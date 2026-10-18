import { useState } from "react";
import type { JobState } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { dlUrl } from "@/lib/api";
import { cn } from "@/lib/utils";

export default function ResultScreen({
  job, jobId, onFeedback, onRestart,
}: { job: JobState; jobId: string; onFeedback: () => void; onRestart: () => void }) {
  const [visaMd, setVisaMd] = useState<string | null>(null);
  const ansokningar = job.docs?.ansokningar ?? [];
  const harGranskning = Object.values(job.granskning ?? {}).some((g) => (g.punkter ?? []).length > 0);

  return (
    <div className="mx-auto w-full max-w-[880px] px-6 py-14">
      <p className="text-[13px] font-semibold uppercase tracking-[0.14em] text-[color:var(--color-accent)]">Färdigt</p>
      <h1 className="mt-3 text-[clamp(24px,4vw,34px)]">
        Dokument för {job.company} — en kravmatris och en ansökningshandling per ansökan
      </h1>
      {ansokningar.map((a) => {
        const r = (job.results ?? []).find((x) => x.dnr === a.dnr);
        return (
          <div key={a.dnr} className="mt-7">
            <h2 className="text-[20px]">
              {a.title} <Badge variant="outline" className="ml-2 align-middle">{a.dnr}</Badge>
            </h2>
            {r && (
              <div className="mt-3 flex flex-wrap gap-2.5">
                <Badge variant="ok">✅ {r.stats.styrkt_uppfyllt ?? 0} styrkta</Badge>
                <Badge variant="warm">❓ {r.stats.okant ?? 0} luckor</Badge>
                <Badge variant="bad">❌ {r.stats.styrkt_ej_uppfyllt ?? 0} felmatch</Badge>
                <Badge>🔧 {r.stats.strukturellt ?? 0} strukturkrav</Badge>
              </div>
            )}
            <div className="mt-3 grid gap-3 md:grid-cols-3">
              <a href={dlUrl(jobId, "excel", a.dnr)} download={a.filnamn_xlsx} className="no-underline">
                <Card className="h-full cursor-pointer p-4 transition hover:border-[color:var(--color-accent)]">
                  <div className="text-[15px] font-semibold text-[color:var(--color-ink)]">📊 Kravmatris (Excel)</div>
                  <div className="mt-1 text-[12.5px] text-[color:var(--color-muted)]">{a.dnr} — bevisstatus per krav</div>
                </Card>
              </a>
              <Card className={cn("flex h-full flex-col justify-between p-4 transition hover:border-[color:var(--color-accent)]",
                visaMd === a.dnr && "border-[color:var(--color-accent)]")}>
                <a href={dlUrl(jobId, "ansokan", a.dnr)} download={a.filnamn_md} className="no-underline">
                  <div className="text-[15px] font-semibold text-[color:var(--color-ink)]">📝 Ansökningshandling</div>
                  <div className="mt-1 text-[12.5px] text-[color:var(--color-muted)]">utkast som .md — klicka för att ladda ner</div>
                </a>
                <button
                  onClick={() => setVisaMd(visaMd === a.dnr ? null : a.dnr)}
                  className="mt-2 self-start text-[12px] font-medium text-[color:var(--color-accent)] underline-offset-2 hover:underline"
                >{visaMd === a.dnr ? "Dölj utkastet" : "Visa utkastet i sidan"}</button>
              </Card>
              <a href={dlUrl(jobId, "granskning", a.dnr)} download={`granskning_${job.company}_${a.dnr}.xlsx`} className="no-underline">
                <Card className="h-full cursor-pointer p-4 transition hover:border-[color:var(--color-accent)]">
                  <div className="text-[15px] font-semibold text-[color:var(--color-ink)]">🔍 Granskning (Excel)</div>
                  <div className="mt-1 text-[12.5px] text-[color:var(--color-muted)]">ifyllbart granskningsformulär</div>
                </Card>
              </a>
            </div>
            {visaMd === a.dnr && (
              <Card className="mt-3 max-h-[70vh] overflow-y-auto p-6">
                <pre className="whitespace-pre-wrap font-[inherit] text-[13.5px] leading-relaxed">{a.md}</pre>
              </Card>
            )}
          </div>
        );
      })}
      <div className="mt-8 flex gap-3">
        {harGranskning && <Button onClick={onFeedback}>🔍 Visa granskningen ↵</Button>}
        <Button variant="outline" onClick={onRestart}>Börja om</Button>
      </div>
    </div>
  );
}
