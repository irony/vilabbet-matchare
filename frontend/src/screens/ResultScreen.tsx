import { useState } from "react";
import type { JobState } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import ChatPanel from "@/components/ChatPanel";
import { dlUrl, redigerUrl } from "@/lib/api";

type DokKind = "excel" | "ansokan" | "granskning";

const DOK_IKON: Record<DokKind, string> = {
  excel: "📊", ansokan: "📝", granskning: "🔍",
};
const DOK_NAMN: Record<DokKind, string> = {
  excel: "Kravmatris", ansokan: "Ansökan", granskning: "Gap-lista",
};

export default function ResultScreen({
  job, jobId, onFeedback, onRestart,
}: { job: JobState; jobId: string; onFeedback: () => void; onRestart: () => void }) {
  const [visaMd, setVisaMd] = useState<string | null>(null);
  // ?dok=1 — visa dokumentkolumnen direkt (används vid inbäddning i slides)
  const [dokDöcka, setDokDöcka] = useState(
    () => new URLSearchParams(window.location.search).get("dok") === "1",
  );
  const ansokningar = job.docs?.ansokningar ?? [];
  const harGranskning = Object.values(job.granskning ?? {}).some((g) => (g.punkter ?? []).length > 0);
  const agentHarÄndrat = (job.chat ?? []).some((m) => (m.ändrade ?? []).length > 0);
  const visaDok = dokDöcka || agentHarÄndrat;

  return (
    <div className="mx-auto w-full max-w-[1240px] px-6 py-14">
      <p className="text-[13px] font-semibold uppercase tracking-[0.14em] text-[color:var(--color-accent)]">Färdigt</p>
      <h1 className="mt-3 text-[clamp(22px,3.4vw,30px)]">
        Dokument för {job.company} — samtala vidare med agenten om gap-listan
      </h1>
      {ansokningar.map((a) => {
        const r = (job.results ?? []).find((x) => x.dnr === a.dnr);
        return (
          <div key={a.dnr} className="mt-4 flex flex-wrap items-center gap-2.5">
            <span className="text-[15px] font-medium">{a.title}</span>
            <Badge variant="outline">{a.dnr}</Badge>
            {r && (
              <>
                <Badge variant="ok">✅ {r.stats.styrkt_uppfyllt ?? 0} styrkta</Badge>
                <Badge variant="warm">❓ {r.stats.okant ?? 0} luckor</Badge>
                <Badge variant="bad">❌ {r.stats.styrkt_ej_uppfyllt ?? 0} felmatch</Badge>
                <Badge>🔧 {r.stats.strukturellt ?? 0} strukturkrav</Badge>
              </>
            )}
            <button
              onClick={() => setDokDöcka(!dokDöcka)}
              className="ml-auto text-[12.5px] font-medium text-[color:var(--color-accent)] underline-offset-2 hover:underline"
            >{visaDok ? "Dölj dokumenten" : "Visa dokumenten"}</button>
          </div>
        );
      })}

      <div className={visaDok ? "mt-5 grid h-[68vh] gap-3 md:grid-cols-[minmax(0,1fr)_312px]" : "mt-5 h-[68vh]"}>
        {harGranskning ? (
          <ChatPanel
            jobId={jobId}
            initial={job.chat ?? []}
            onÄndrade={() => setDokDöcka(true)}
            autoÖppna
          />
        ) : (
          <Card className="flex items-center justify-center p-8 text-[14px] text-[color:var(--color-muted)]">
            Granskningen saknar gap-punkter — dokumenten finns redo via
            "Visa dokumenten".
          </Card>
        )}

        {visaDok && (
          <div className="min-h-0 space-y-3 overflow-y-auto">
            {ansokningar.map((a) => {
              const r = (job.results ?? []).find((x) => x.dnr === a.dnr);
              void r;
              return (
                <Card key={a.dnr} className="p-3.5">
                  <div className="text-[11.5px] font-semibold uppercase tracking-[0.1em] text-[color:var(--color-muted)]">
                    📄 {a.dnr}
                  </div>
                  {(Object.keys(DOK_IKON) as DokKind[]).map((kind) => (
                    <div key={kind} className="mt-2.5 border-t border-[color:var(--color-line)] pt-2.5 first:border-0 first:pt-0">
                      <div className="text-[13px] font-medium text-[color:var(--color-ink)]">
                        {DOK_IKON[kind]} {DOK_NAMN[kind]}
                      </div>
                      <div className="mt-1.5 flex flex-col gap-1">
                        <a
                          href={redigerUrl(jobId, kind, a.dnr)}
                          target="_blank" rel="noopener"
                          className="text-[12px] font-medium text-[color:var(--color-accent)] underline-offset-2 hover:underline"
                        >Öppna i Eurooffice ↗</a>
                        <a
                          href={dlUrl(jobId, kind, a.dnr)}
                          download={kind === "ansokan" ? a.filnamn_md.replace(/\.md$/, ".docx")
                                    : kind === "excel" ? a.filnamn_xlsx
                                    : `granskning_${job.company}_${a.dnr}.xlsx`}
                          className="text-[12px] text-[color:var(--color-ink)] underline underline-offset-2"
                        >⤓ Ladda ner</a>
                        {kind === "ansokan" && (
                          <button
                            onClick={() => setVisaMd(visaMd === a.dnr ? null : a.dnr)}
                            className="self-start text-[11.5px] text-[color:var(--color-accent)] underline-offset-2 hover:underline"
                          >{visaMd === a.dnr ? "Dölj i sidan" : "Visa i sidan"}</button>
                        )}
                      </div>
                    </div>
                  ))}
                  {visaMd === a.dnr && (
                    <div className="mt-2 max-h-[50vh] overflow-y-auto rounded-lg bg-slate-50 p-3">
                      <pre className="whitespace-pre-wrap font-[inherit] text-[11.5px] leading-relaxed">{a.md}</pre>
                    </div>
                  )}
                </Card>
              );
            })}
          </div>
        )}
      </div>

      <div className="mt-6 flex gap-3">
        {harGranskning && <Button onClick={onFeedback}>🔍 Visa granskningsformuläret ↵</Button>}
        <Button variant="outline" onClick={onRestart}>Börja om</Button>
      </div>
    </div>
  );
}
