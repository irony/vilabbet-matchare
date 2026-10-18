import { useState } from "react";
import type { JobState } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import ChatPanel from "@/components/ChatPanel";
import { dlUrl, redigerUrl } from "@/lib/api";

type DokKind = "excel" | "ansokan" | "granskning";

const DOK_ETIKETT: Record<DokKind, string> = {
  excel: "📊 Kravmatris", ansokan: "📝 Ansökan", granskning: "🔍 Gap-lista",
};

/** Split-vy: Eurooffice-editor till vänster, agent-chatt till höger. */
function RedigerLäge({ job, jobId }: { job: JobState; jobId: string }) {
  const ansokningar = job.docs?.ansokningar ?? [];
  const [kind, setKind] = useState<DokKind>("ansokan");
  const [dnr, setDnr] = useState<string | undefined>(ansokningar[0]?.dnr);
  const [frameKey, setFrameKey] = useState(0);
  const [upplyst, setUpplyst] = useState(false);
  if (!dnr) return null;
  const url = redigerUrl(jobId, kind, dnr);
  return (
    <div className="mt-6">
      <div className="flex flex-wrap items-center gap-1.5">
        {(ansokningar.flatMap((a) => (Object.keys(DOK_ETIKETT) as DokKind[]).map((k) => ({ k, a })))).map(({ k, a }) => (
          <button
            key={`${k}:${a.dnr}`}
            onClick={() => { setKind(k); setDnr(a.dnr); setFrameKey((x) => x + 1); setUpplyst(false); }}
            className={
              "rounded-lg border px-2.5 py-1 text-[12px] font-medium transition " +
              (k === kind && a.dnr === dnr
                ? "border-[color:var(--color-accent)] bg-[color:var(--color-accent)] text-white"
                : "border-[color:var(--color-ink-2)] bg-white text-[color:var(--color-ink)] hover:border-[color:var(--color-accent)]")
            }
          >{DOK_ETIKETT[k]} {a.dnr}</button>
        ))}
        <button
          onClick={() => { setFrameKey((x) => x + 1); setUpplyst(false); }}
          className="ml-auto rounded-lg border border-[color:var(--color-ink-2)] px-2.5 py-1 text-[12px] font-medium hover:border-[color:var(--color-accent)]"
        >↻ ladda om editorn</button>
        {upplyst && (
          <span className="w-full text-[11.5px] text-amber-700">
            💾 Agenten ändrade dokumentet — redigeraren laddades om med ny version.
          </span>
        )}
      </div>
      <div className="mt-3 grid h-[70vh] gap-3 md:grid-cols-[minmax(0,3fr)_minmax(280px,2fr)]">
        <iframe
          key={frameKey}
          src={`${url}${url.includes("?") ? "&" : "?"}_k=${frameKey}`}
          className="h-full w-full rounded-xl border border-[color:var(--color-ink-2)] bg-white"
          title="Eurooffice-redigeraren"
        />
        <ChatPanel
          jobId={jobId}
          initial={job.chat ?? []}
          onÄndrade={() => { setFrameKey((x) => x + 1); setUpplyst(true); }}
        />
      </div>
    </div>
  );
}

function DokCard({
  jobId, dnr, ikon, titel, sub, kind, dlNamn, extra,
}: {
  jobId: string; dnr: string; ikon: string; titel: string; sub: string;
  kind: DokKind; dlNamn: string; extra?: React.ReactNode;
}) {
  return (
    <Card className="flex h-full flex-col justify-between p-4">
      <div>
        <div className="text-[15px] font-semibold text-[color:var(--color-ink)]">{ikon} {titel}</div>
        <div className="mt-1 text-[12.5px] text-[color:var(--color-muted)]">{sub}</div>
      </div>
      <div className="mt-3 flex flex-col gap-1.5">
        <Button
          size="sm"
          onClick={() => window.open(redigerUrl(jobId, kind, dnr), "_blank", "noopener")}
        >Öppna i Eurooffice ↗</Button>
        <a href={dlUrl(jobId, kind, dnr)} download={dlNamn} className="no-underline">
          <Button size="sm" variant="outline" className="w-full">⤓ Ladda ner</Button>
        </a>
        {extra}
      </div>
    </Card>
  );
}

export default function ResultScreen({
  job, jobId, onFeedback, onRestart,
}: { job: JobState; jobId: string; onFeedback: () => void; onRestart: () => void }) {
  const [visaMd, setVisaMd] = useState<string | null>(null);
  const [redl, setRedl] = useState(false);
  const ansokningar = job.docs?.ansokningar ?? [];
  const harGranskning = Object.values(job.granskning ?? {}).some((g) => (g.punkter ?? []).length > 0);

  return (
    <div className={redl
      ? "mx-auto w-full max-w-[1280px] px-6 py-14"
      : "mx-auto w-full max-w-[880px] px-6 py-14"}>
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
              <DokCard
                jobId={jobId} dnr={a.dnr} kind="excel" ikon="📊"
                titel="Kravmatris (Excel)" sub={`${a.dnr} — bevisstatus per krav`}
                dlNamn={a.filnamn_xlsx}
              />
              <DokCard
                jobId={jobId} dnr={a.dnr} kind="ansokan" ikon="📝"
                titel="Ansökningshandling" sub="redigerbart utkast i Eurooffice"
                dlNamn={a.filnamn_md.replace(/\.md$/, ".docx")}
                extra={
                  <button
                    onClick={() => setVisaMd(visaMd === a.dnr ? null : a.dnr)}
                    className="self-start text-[12px] font-medium text-[color:var(--color-accent)] underline-offset-2 hover:underline"
                  >{visaMd === a.dnr ? "Dölj utkastet i sidan" : "Visa utkastet i sidan"}</button>
                }
              />
              <DokCard
                jobId={jobId} dnr={a.dnr} kind="granskning" ikon="🔍"
                titel="Granskning (Excel)" sub="ifyllbart granskningsformulär"
                dlNamn={`granskning_${job.company}_${a.dnr}.xlsx`}
              />
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
        <Button variant={redl ? "default" : "outline"} onClick={() => setRedl(!redl)}>
          💬 Redigera med agent — Eurooffice + chatt
        </Button>
        <Button variant="outline" onClick={onRestart}>Börja om</Button>
      </div>
      {redl && ansokningar.length > 0 && <RedigerLäge job={job} jobId={jobId} />}
    </div>
  );
}
