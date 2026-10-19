import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Api } from "@/lib/api";
import { cn } from "@/lib/utils";

/** Eurooffice-läge: bred vy med ett av dokumenten öppet direkt i editorn
 *  (kravmatris-Excel först) och flikar för att växla mellan dokumenten.
 *  Används t.ex. inbäddat i presentationer. */

const TYPER = [
  { kind: "excel", etikett: "📊 Kravmatris" },
  { kind: "ansokan", etikett: "📝 Ansökan" },
  { kind: "granskning", etikett: "🔍 Gap-lista" },
] as const;
type Kind = (typeof TYPER)[number]["kind"];

export default function EuroScreen({ jobId }: { jobId: string }) {
  const { data: job } = useQuery({
    queryKey: ["job", jobId, "euro"],
    queryFn: () => Api.job(jobId),
    refetchInterval: 5000,
  });
  const [kind, setKind] = useState<Kind>("excel");
  const dnr = (job?.docs?.ansokningar ?? [])[0]?.dnr;

  return (
    <div className="mx-auto flex h-full w-full max-w-[1500px] flex-col px-4 py-4">
      <div className="flex items-center gap-2">
        {TYPER.map((t) => (
          <button
            key={t.kind}
            type="button"
            onClick={() => setKind(t.kind)}
            className={cn(
              "rounded-full border-[1.5px] px-4 py-1.5 text-[13.5px] font-medium transition",
              kind === t.kind
                ? "border-[color:var(--color-accent)] bg-[color:var(--color-accent-soft)] text-[color:var(--color-accent)]"
                : "border-[color:var(--color-line)] bg-white text-[color:var(--color-muted)] hover:border-[color:var(--color-accent)]",
            )}
          >
            {t.etikett}
            {dnr && kind === t.kind ? ` · ${dnr}` : ""}
          </button>
        ))}
      </div>
      <div className="mt-3 min-h-0 flex-1">
        {dnr ? (
          <iframe
            key={`${kind}-${dnr}`}
            src={`/r/${jobId}/${kind}/${dnr}`}
            title={`Eurooffice — ${kind}`}
            className="h-[calc(100vh-92px)] w-full rounded-xl border-[1.5px] border-[color:var(--color-line)] bg-white"
          />
        ) : (
          <p className="mt-8 text-center text-[15px] text-[color:var(--color-muted)]">
            Dokumenten byggs i {job?.company ?? "jobbet"} …
          </p>
        )}
      </div>
    </div>
  );
}
