import { useEffect, useRef, useState } from "react";
import { chatApi, type ChatMsg } from "@/lib/api";
import { Button } from "@/components/ui/button";

/** Chattpanel i redigerläget — agent (gemma-4) med verktyg mot jobbets
 *  dokument, webbsök och bolagsregistret. */
export default function ChatPanel({
  jobId, initial, onÄndrade,
}: {
  jobId: string;
  initial: ChatMsg[];
  onÄndrade: () => void;
}) {
  const [meddelanden, setMeddelanden] = useState<ChatMsg[]>(initial);
  const [text, setText] = useState("");
  const [väntar, setVäntar] = useState(false);
  const slutRef = useRef<HTMLDivElement>(null);

  useEffect(() => { setMeddelanden(initial); }, [initial]);
  useEffect(() => {
    slutRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [meddelanden, väntar]);

  async function skicka() {
    const m = text.trim();
    if (!m || väntar) return;
    setText("");
    setMeddelanden((p) => [...p, { roll: "användare", innehåll: m }]);
    setVäntar(true);
    try {
      const s = await chatApi(jobId, m);
      setMeddelanden((p) => [...p, {
        roll: "assistent", innehåll: s.svar,
        verktyg: s.verktyg, ändrade: s.ändrade,
      }]);
      if (s.ändrade?.length) onÄndrade();
    } catch (e) {
      setMeddelanden((p) => [...p, {
        roll: "assistent", innehåll: `⚠️ något gick fel: ${e}`,
      }]);
    } finally {
      setVäntar(false);
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col rounded-xl border border-[color:var(--color-ink-2)] bg-white">
      <div className="border-b border-[color:var(--color-ink-2)] px-3 py-2 text-[12.5px] font-semibold text-[color:var(--color-ink)]">
        💬 Agent (gemma-4) — chatt om gap & dokument
      </div>
      <div className="min-h-0 flex-1 space-y-2.5 overflow-y-auto p-3">
        {meddelanden.length === 0 && (
          <div className="mt-4 space-y-2 text-[12.5px] text-[color:var(--color-muted)]">
            <p>Fråga agenten om gap-punkterna, eller be den fylla i dokumenten. Den kan:</p>
            <ul className="ml-4 list-disc space-y-1">
              <li>🔍 söka på svenska webben & skrapa sidor</li>
              <li>🏢 söka bolag (Bolagsverkets register) för konsortiekandidater</li>
              <li>📝 ändra i ansökan, kravmatrisen och gap-listan direkt</li>
            </ul>
          </div>
        )}
        {meddelanden.map((m, i) => (
          <div key={i} className={m.roll === "användare" ? "text-right" : ""}>
            <div className={
              "inline-block max-w-[92%] rounded-xl px-3 py-2 text-left text-[13px] leading-snug whitespace-pre-wrap " +
              (m.roll === "användare"
                ? "bg-[color:var(--color-accent)] text-white"
                : "bg-slate-100 text-[color:var(--color-ink)]")
            }>
              {m.innehåll}
              {!!m.verktyg?.length && (
                <div className="mt-1 border-t border-black/10 pt-1 text-[11px] opacity-70">
                  🛠 {m.verktyg.map((v) => v.verktyg).join(" · ")}
                </div>
              )}
            </div>
          </div>
        ))}
        {väntar && <div className="text-[12.5px] text-[color:var(--color-muted)]">⏳ agenten arbetar…</div>}
        <div ref={slutRef} />
      </div>
      <form
        className="flex gap-2 border-t border-[color:var(--color-ink-2)] p-2"
        onSubmit={(e) => { e.preventDefault(); skicka(); }}
      >
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="t.ex. 'hitta en andra svensk partner till konsortiet'"
          className="min-w-0 flex-1 rounded-lg border border-[color:var(--color-ink-2)] px-3 py-2 text-[13px] outline-none focus:border-[color:var(--color-accent)]"
        />
        <Button type="submit" size="sm" disabled={väntar || !text.trim()}>Skicka ↵</Button>
      </form>
    </div>
  );
}
