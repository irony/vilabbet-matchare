import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Api, chatApi, type JobState } from "@/lib/api";
import DictateButton from "@/components/DictateButton";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

/** Fokusläge: en fråga i stort typsnitt — inget annat. Agentens senaste
 *  fråga visas stort, användaren svarar (skriv eller diktera), nästa
 *  fråga rullar in. Används t.ex. inbäddat i presentationer. */
export default function FocusScreen({ jobId }: { jobId: string }) {
  const qc = useQueryClient();
  const { data: job } = useQuery<JobState>({
    queryKey: ["job", jobId, "fokus"],
    queryFn: () => Api.job(jobId),
    refetchInterval: 2000,
  });
  const [svar, setSvar] = useState("");
  const [väntar, setVäntar] = useState(false);
  const [öppnat, setÖppnat] = useState(false);

  const chat = job?.chat ?? [];
  const sista = chat[chat.length - 1];
  const fråga =
    sista?.roll === "assistent" ? sista.innehåll.replace(/\*\*/g, "") : null;

  // proaktiv öppning när chatten är tom — agenten ställer första frågan
  useEffect(() => {
    if (öppnat || !job || chat.length > 0) return;
    setÖppnat(true);
    setVäntar(true);
    fetch("/api/chat/open", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ job_id: jobId }),
    })
      .then(async (r) => {
        const d = await r.json();
        if (d.svar) qc.invalidateQueries({ queryKey: ["job", jobId, "fokus"] });
      })
      .catch(() => {})
      .finally(() => setVäntar(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job]);

  const skicka = async () => {
    const text = svar.trim();
    if (!text || väntar) return;
    setSvar("");
    setVäntar(true);
    try {
      await chatApi(jobId, text);
      qc.invalidateQueries({ queryKey: ["job", jobId, "fokus"] });
      qc.invalidateQueries({ queryKey: ["job", jobId] });
    } finally {
      setVäntar(false);
    }
  };

  return (
    <div className="mx-auto flex min-h-full w-full max-w-[860px] flex-col justify-center px-8 py-14">
      <div className="min-h-[38vh]">
        {fråga ? (
          <p className="font-[family-name:var(--font-display)] text-[clamp(26px,3.6vw,40px)] leading-[1.2]">
            {fråga}
          </p>
        ) : (
          <p className="text-[clamp(18px,2.4vw,26px)] text-[color:var(--color-muted)]">
            agenten tänker …
          </p>
        )}
      </div>
      <div className="flex items-center gap-3">
        <Input
          value={svar}
          onChange={(e) => setSvar(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && void skicka()}
          placeholder="Svara …"
          className="flex-1 !text-[19px] !rounded-none !border-0 !border-b-2 !px-1.5 !py-2.5"
          autoFocus
          enterKeyHint="send"
        />
        <DictateButton onText={(t) => setSvar((v) => (v ? `${v.trimEnd()} ${t}` : t))} />
        <Button onClick={() => void skicka()} disabled={väntar || !svar.trim()}>
          {väntar ? "Arbetar …" : "Skicka ↵"}
        </Button>
      </div>
    </div>
  );
}
