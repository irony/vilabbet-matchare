import type { JobState } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

function fmtTkr(tkr?: number | null) {
  if (tkr == null) return null;
  return tkr >= 1000 ? `${(tkr / 1000).toFixed(1).replace(".", ",")} mkr` : `${tkr} tkr`;
}

export default function SummaryScreen({
  job, onNext, onRestart,
}: { job: JobState; onNext: () => void; onRestart: () => void }) {
  const f = job.nyckelfakta ?? {};
  const chips: [string, string][] = [];
  if (f.namn && f.register_driven) chips.push(["Namn (registret)", f.namn]);
  if (f.orgnr) chips.push(["Org.nr", f.orgnr]);
  if (f.form) chips.push(["Bolagsform", f.form]);
  if (f.grundat) chips.push(["Grundat", String(f.grundat)]);
  if (f.antal_anstallda != null) chips.push(["Anställda", String(f.antal_anstallda)]);
  if (f.omsattning_tkr) chips.push(["Omsättning", fmtTkr(f.omsattning_tkr)!]);
  if (f.ort) chips.push(["Ort", f.ort]);
  if (f.likvidation === true) chips.push(["⚠️ Juridisk status", "i likvidation/rekonstruktion"]);
  else if (f.register_driven) chips.push(["Juridisk status", "aktiv"]);
  const kalla = f.register_driven
    ? `underlag: er webbplats + ${f.kalla} (Bolagsverkets officiella register)`
    : "underlag: er webbplats";

  return (
    <div className="mx-auto flex min-h-full w-full max-w-[860px] flex-col justify-center px-6 py-14">
      <p className="text-[13px] font-semibold uppercase tracking-[0.14em] text-[color:var(--color-accent)]">Sammanfattning</p>
      <h1 className="mt-3 text-[clamp(26px,4vw,38px)]">Vad vi lärde oss om {job.company}</h1>
      <div className="mt-6 flex flex-wrap gap-3">
        {chips.length
          ? chips.map(([k, v]) => (
              <Card key={k} className="px-4 py-3">
                <div className="text-[15px] font-semibold">{v}</div>
                <div className="text-[11.5px] uppercase tracking-wide text-[color:var(--color-muted)]">{k}</div>
              </Card>
            ))
          : (
            <Card className="px-4 py-3">
              <div className="text-[15px] font-semibold">📄</div>
              <div className="text-[12.5px] text-[color:var(--color-muted)]">
                bolagsregistret gav ingen träff — vi baserar på webbplatsen
              </div>
            </Card>
          )}
      </div>
      <Card className="mt-7">
        <CardHeader><CardTitle>{job.company}</CardTitle></CardHeader>
        <CardContent>
          <p className="whitespace-pre-wrap text-[14.5px] leading-relaxed">{job.profil}</p>
        </CardContent>
      </Card>
      <div className="mt-7 flex gap-3">
        <Button onClick={onNext}>Stämmer — visa mina utlysningar ↵</Button>
        <Button variant="outline" onClick={onRestart}>Börja om</Button>
      </div>
      {job.phase === "matchar" && (
        <p className="mt-4 flex items-center gap-2 text-[12.5px] text-[color:var(--color-muted)]">
          <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-[color:var(--color-accent)] border-t-transparent" />
          Medan du läser: AI:n matchar er profil mot 303 öppna utlysningar i
          bakgrunden — träfflistan är redo när du klickar vidare.
        </p>
      )}
      <p className="mt-5 text-[12.5px] text-[color:var(--color-muted)]">{kalla}</p>
    </div>
  );
}
