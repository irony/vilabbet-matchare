import { useState } from "react";
import type { JobState } from "@/lib/api";
import { Api, dlUrl } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";

const ALLVAR: Record<string, [string, "bad" | "warm" | "ok"]> = {
  blockerare: ["blockerare", "bad"],
  viktigt: ["viktigt", "warm"],
  "förslag": ["förslag", "ok"],
};
const KAT: Record<string, string> = {
  formalia: "Formalia", "formulärfråga": "Formulärfråga", krav: "Krav",
  bristande_bevis: "Bristande bevis", svagt_argument: "Svagt argument",
  motsägelse: "Motsägelse",
};
const STATUS_VAL = ["Ej påbörjad", "Pågår", "Löst", "Behöver ej"];

interface Fyllning { status: string; ansvarig: string; kommentar: string }

export default function FeedbackScreen({
  job, jobId, onBack,
}: { job: JobState; jobId: string; onBack: () => void }) {
  const [svar, setSvar] = useState<Record<string, Record<number, Fyllning>>>({});
  const [hint, setHint] = useState("status sparas på servern; hämta hem Excelfilen efter att du sparat för ifylld version");
  const [saving, setSaving] = useState(false);
  const g = job.granskning ?? {};

  const set = (dnr: string, nr: number, upd: Partial<Fyllning>) =>
    setSvar((old) => {
      const bef = old[dnr]?.[nr];
      return {
        ...old,
        [dnr]: { ...(old[dnr] ?? {}), [nr]: { status: bef?.status ?? "Ej påbörjad", ansvarig: bef?.ansvarig ?? "", kommentar: bef?.kommentar ?? "", ...upd } },
      };
    });

  const spara = async () => {
    setSaving(true);
    try {
      const dnrs: Record<string, { kommentar: string; punkter: Record<string, Fyllning> }> = {};
      Object.entries(svar).forEach(([dnr, punkter]) => {
        dnrs[dnr] = { kommentar: "", punkter: Object.fromEntries(commentsClean(punkter)) };
      });
      const r = await Api.feedback(jobId, dnrs);
      setHint(`✓ sparat (${r.svar} svar) — hämta hem granskning-Excels nu om du vill se ifylld version`);
    } catch (e) {
      setHint(`Kunde inte spara: ${e instanceof Error ? e.message : e}`);
    } finally { setSaving(false); }
  };

  return (
    <div className="mx-auto w-full max-w-[900px] px-6 py-14">
      <p className="text-[13px] font-semibold uppercase tracking-[0.14em] text-[color:var(--color-accent)]">
        Sista steget
      </p>
      <h1 className="mt-3 text-[clamp(24px,4vw,34px)]">Granskning med färska ögon</h1>
      <p className="mt-3 max-w-[720px] text-[15px] leading-relaxed text-[color:var(--color-muted)]">
        Utkasten lästes om mot utlysningen — bolagsblint, som en extern granskare.
        Fyll i status per punkt eller hämta hem alla punkter som ifyllbart Excel-ark.
      </p>
      {Object.entries(g).map(([dnr, gr]) => {
        if (!gr.punkter?.length) return null;
        const a = (job.docs?.ansokningar ?? []).find((x) => x.dnr === dnr);
        const ant = gr.antal ?? {};
        return (
          <div key={dnr} className="mt-8">
            <h2 className="text-[21px]">{a?.title ?? dnr} <Badge variant="outline" className="ml-2 align-middle">{dnr}</Badge></h2>
            <div className="mt-2 flex flex-wrap gap-2.5">
              <Badge variant="bad">🛑 {ant.blockerare ?? 0} blockerare</Badge>
              <Badge variant="warm">⚠️ {ant.viktigt ?? 0} viktiga</Badge>
              <Badge variant="ok">💡 {ant["förslag"] ?? 0} förslag</Badge>
            </div>
            <p className="mt-3 max-w-[760px] text-[14.5px] text-[color:var(--color-muted)]">{gr.sammanfattning}</p>
            <p className="mt-2 text-[14px]">
              <a className="text-[color:var(--color-accent)] underline underline-offset-2"
                 href={dlUrl(jobId, "granskning", dnr)} download={`granskning_${job.company}_${dnr}.xlsx`}>
                📊 Hämta gransknings-Excel ({dnr})
              </a>
            </p>
            {gr.punkter.map((p) => {
              const [atxt, avar] = ALLVAR[p.allvar] ?? ["?", "default" as const];
              const fy = svar[dnr]?.[p.nr];
              return (
                <Card key={p.nr} className="mt-3 p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="accent">{KAT[p.kategori] ?? p.kategori}</Badge>
                    <Badge variant={avar}>{atxt}</Badge>
                    {p.krav_id && <Badge>{p.krav_id}</Badge>}
                    <span className="text-[12.5px] italic text-[color:var(--color-muted)]">{p.avsnitt}</span>
                  </div>
                  <p className="mt-2.5 text-[13.5px] leading-snug">
                    <b>Brist:</b> {p.beskrivning}<br />
                    <b>Åtgärd:</b> {p.atgard}
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2.5">
                    <Select value={fy?.status ?? "Ej påbörjad"} onChange={(e) => set(dnr, p.nr, { status: e.target.value })}>
                      {STATUS_VAL.map((o) => <option key={o}>{o}</option>)}
                    </Select>
                    <Input placeholder="Ansvarig" className="max-w-[170px] !py-1.5 !text-[12.5px]"
                           value={fy?.ansvarig ?? ""} onChange={(e) => set(dnr, p.nr, { ansvarig: e.target.value })} />
                    <Input placeholder="Kommentar" className="flex-1 !py-1.5 !text-[12.5px]"
                           value={fy?.kommentar ?? ""} onChange={(e) => set(dnr, p.nr, { kommentar: e.target.value })} />
                  </div>
                </Card>
              );
            })}
          </div>
        );
      })}
      <div className="mt-8 flex gap-3">
        <Button onClick={spara} disabled={saving}>{saving ? "Sparar …" : "Spara formuläret ✓"}</Button>
        <Button variant="outline" onClick={onBack}>← Tillbaka till dokumenten</Button>
      </div>
      <p className="mt-4 text-[12.5px] text-[color:var(--color-muted)]">{hint}</p>
    </div>
  );
}

function commentsClean(punkter: Record<number, Fyllning>): [string, Fyllning][] {
  return Object.entries(punkter).map(([nr, f]) => [nr, f]);
}
