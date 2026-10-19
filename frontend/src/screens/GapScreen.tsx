import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { chatApi, type JobState } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import DictateButton from "@/components/DictateButton";
import Markdown from "@/components/Markdown";

/** Fokusläge för granskningen: en gap-punkt i taget, stort och rent.
 *  Under varje punkt agentens fråga — svaret chatas direkt in till
 *  agenten som uppdaterar ansökan. Används t.ex. inbäddat i presentationer. */
export default function GapScreen({ job, jobId }: { job: JobState; jobId: string }) {
  const qc = useQueryClient();
  const punkter = Object.values(job.granskning ?? {}).flatMap((g) => g.punkter ?? []);
  const [i, setI] = useState(0);
  const [utkast, setUtkast] = useState("");
  type Svarat = { text: string; svar?: string; väntar?: boolean };
  const [svaratpå, setSvaratpå] = useState<Record<number, Svarat>>({});
  const p = punkter[Math.min(i, punkter.length - 1)];
  const om = p ? svaratpå[p.nr] : undefined;

  const skicka = async () => {
    if (!p) return;
    const text = utkast.trim();
    if (!text || om?.väntar) return;
    setSvaratpå((s) => ({ ...s, [p.nr]: { text, väntar: true } }));
    setUtkast("");
    try {
      const r = await chatApi(
        jobId,
        `Fråga ${p.nr} (${p.kategori}, ${p.allvar}): ${p.beskrivning}\n\nMitt svar: ${text}`,
      );
      setSvaratpå((s) => ({ ...s, [p.nr]: { text, svar: r.svar } }));
      qc.invalidateQueries({ queryKey: ["job", jobId] });
    } catch {
      setSvaratpå((s) => ({ ...s, [p.nr]: { text, svar: "⚠️ något gick fel — försök igen" } }));
    }
  };

  if (!p) {
    return (
      <div className="mx-auto flex min-h-full w-full max-w-[860px] flex-col justify-center px-8 py-14">
        <p className="text-[clamp(18px,2.4vw,26px)] text-[color:var(--color-muted)]">
          Granskningen har inga gap-punkter.
        </p>
      </div>
    );
  }

  const variant =
    p.allvar === "blockerare" ? "bad" : p.allvar === "viktigt" ? "warm" : "default";

  return (
    <div className="mx-auto flex min-h-full w-full max-w-[860px] flex-col justify-center px-8 py-14">
      <div className="flex items-center gap-2.5">
        <Badge variant="accent">{p.kategori}</Badge>
        <Badge variant={variant}>{p.allvar}</Badge>
        {p.krav_id && <Badge variant="outline">{p.krav_id}</Badge>}
        <span className="ml-auto font-mono text-[13px] tabular-nums text-[color:var(--color-muted)]">
          {i + 1} / {punkter.length}
        </span>
      </div>

      {p.avsnitt && (
        <p className="mt-5 text-[15px] italic text-[color:var(--color-muted)]">{p.avsnitt}</p>
      )}
      <p className="mt-3 font-[family-name:var(--font-display)] text-[clamp(24px,3.2vw,36px)] leading-[1.2]">
        {p.beskrivning}
      </p>
      {p.atgard && (
        <p className="mt-4 max-w-[640px] text-[clamp(15px,1.8vw,18px)] leading-relaxed text-[color:var(--color-muted)]">
          {p.atgard}
        </p>
      )}

      {p.stöd && (p.stöd.förslag || p.stöd.personer?.length || p.stöd.organisationer?.length || p.stöd.fynd?.length) && (
        <div className="mt-6 rounded-xl border-[1.5px] border-[color:var(--color-ok)]/30 bg-[color:var(--color-ok-soft)] px-5 py-4">
          <p className="text-[12.5px] font-semibold uppercase tracking-[0.1em] text-[color:var(--color-ok)]">
            💡 Gap-stöd från bolagets egna sidor
          </p>
          {p.stöd.förslag && (
            <p className="mt-2 text-[15px] leading-relaxed">{p.stöd.förslag}</p>
          )}
          {p.stöd.personer && p.stöd.personer.length > 0 && (
            <p className="mt-2 text-[14px] text-[color:var(--color-muted)]">
              Personer: {p.stöd.personer.join(", ")}
            </p>
          )}
          {p.stöd.organisationer && p.stöd.organisationer.length > 0 && (
            <p className="mt-1.5 text-[14px] text-[color:var(--color-muted)]">
              Organisationer: {p.stöd.organisationer.join(", ")}
            </p>
          )}
          {p.stöd.fynd?.map((f, idx) => (
            <p key={idx} className="mt-2 border-l-2 border-[color:var(--color-ok)]/40 pl-3 text-[13.5px] italic text-[color:var(--color-muted)]">
              ”{f.citat}” {f.sida && <span className="not-italic">— {f.sida}</span>}
            </p>
          ))}
        </div>
      )}

      <div className="mt-7 border-t border-[color:var(--color-line)] pt-5">
        <p className="font-[family-name:var(--font-display)] text-[clamp(19px,2.4vw,26px)] leading-snug">
          {p.fråga ?? "Hur fyller vi i den här punkten?"}
        </p>
        <div className="mt-3 flex items-center gap-2.5">
          <Input
            value={utkast}
            onChange={(e) => setUtkast(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && void skicka()}
            placeholder={om ? "Uppdatera ert svar …" : "Svar …"}
            className="flex-1 !text-[16px]"
            autoFocus
          />
          <DictateButton onText={(t) => setUtkast((v) => (v ? `${v.trimEnd()} ${t}` : t))} />
          <Button onClick={() => void skicka()} disabled={!utkast.trim() || !!om?.väntar}>
            {om?.väntar ? "Arbetar …" : "Skicka ↵"}
          </Button>
        </div>
        {om?.svar && (
          <Markdown
            text={om.svar}
            className="mt-2.5 max-w-[640px] space-y-2 text-[13.5px] leading-relaxed text-[color:var(--color-muted)]"
          />
        )}
      </div>

      <div className="mt-6 flex gap-3">
        <Button variant="outline" onClick={() => setI((v) => Math.max(0, v - 1))} disabled={i === 0}>
          ← Föregående
        </Button>
        <Button
          variant="outline"
          onClick={() => setI((v) => Math.min(punkter.length - 1, v + 1))}
          disabled={i >= punkter.length - 1}
        >
          Nästa →
        </Button>
      </div>
    </div>
  );
}
