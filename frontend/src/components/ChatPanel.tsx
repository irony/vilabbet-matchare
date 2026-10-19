import { useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  ThreadPrimitive,
  ComposerPrimitive,
  MessagePrimitive,
  useExternalStoreRuntime,
  type ThreadMessageLike,
  AssistantRuntimeProvider,
} from "@assistant-ui/react";
import { chatApi, type ChatMsg } from "@/lib/api";
import DictateButton from "@/components/DictateButton";

/** Konvertera vår ChatMsg → assistant-uis ThreadMessageLike.
 *  Verktygslistan bäddas in som en sista smal rad i assistent-texten. */
function tillThreadMessage(m: ChatMsg, idx: number): ThreadMessageLike {
  let text = m.innehåll;
  if (m.roll === "assistent" && m.verktyg?.length) {
    text += "\n\n— 🛠 " + m.verktyg.map((v) => v.verktyg).join(" · ");
  }
  return {
    id: `m${idx}`,
    role: m.roll === "användare" ? "user" : "assistant",
    createdAt: new Date(),
    content: [{ type: "text", text }],
    ...(m.roll === "assistent"
      ? { status: { type: "complete", reason: "stop" } }
      : {}),
  } as ThreadMessageLike;
}

const UserBubble = () => (
  <MessagePrimitive.Root className="flex justify-end px-3 py-1.5">
    <div className="max-w-[92%] rounded-xl bg-[color:var(--color-accent)] px-3 py-2 text-left text-[13px] leading-snug whitespace-pre-wrap text-white">
      <MessagePrimitive.Content />
    </div>
  </MessagePrimitive.Root>
);

const AssistantBubble = () => (
  <MessagePrimitive.Root className="flex justify-start px-3 py-1.5">
    <div className="max-w-[92%] rounded-xl bg-slate-100 px-3 py-2 text-[13px] leading-snug whitespace-pre-wrap text-[color:var(--color-ink)]">
      <MessagePrimitive.Content />
    </div>
  </MessagePrimitive.Root>
);

const EmptyHint = () => (
  <div className="space-y-2 p-3 text-[12.5px] text-[color:var(--color-muted)]">
    <p>Fråga agenten om gap-punkterna, eller be den fylla i dokumenten. Den kan:</p>
    <ul className="ml-4 list-disc space-y-1">
      <li>🔍 söka på svenska webben & skrapa sidor</li>
      <li>🏢 söka bolag (Bolagsverkets register) för konsortiekandidater</li>
      <li>📝 ändra i ansökan, kravmatrisen och gap-listan direkt</li>
    </ul>
  </div>
);

/** Chattpanel — assistant-ui (ThreadPrimitive) toppstyrd av vår externa
 *  meddelandelista (job.chat + POST /api/chat). Efter att svaret landat
 *  läsas jobbet om via React Query. */
export default function ChatPanel({
  jobId, initial, onÄndrade, autoÖppna = false,
}: {
  jobId: string;
  initial: ChatMsg[];
  onÄndrade: () => void;
  autoÖppna?: boolean;
}) {
  const qc = useQueryClient();
  const [meddelanden, setMeddelanden] = useState<ChatMsg[]>(initial);
  const [väntar, setVäntar] = useState(false);
  const [öppnat, setÖppnat] = useState(false);

  useEffect(() => { setMeddelanden(initial); }, [initial]);

  // proaktiv öppning när chatten är tom — agenten börjar med gap-frågan (EN i taget)
  useEffect(() => {
    if (!autoÖppna || öppnat || initial.length > 0) return;
    setÖppnat(true);
    setVäntar(true);
    fetch("/api/chat/open", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ job_id: jobId }),
    }).then(async (r) => {
      const d = await r.json();
      if (d.svar) {
        setMeddelanden((p) => p.length ? p : [{ roll: "assistent", innehåll: d.svar }]);
        qc.invalidateQueries({ queryKey: ["job", jobId] });
      }
    }).catch(() => {})
      .finally(() => setVäntar(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const runtimes = useMemo(() => ({
    messages: meddelanden,
    convertMessage: tillThreadMessage,
    isRunning: väntar,
    onNew: async (message: unknown) => {
      const content = (message as { content?: Array<{ type: string; text?: string }> }).content ?? [];
      const txt = content
        .filter((p) => p.type === "text")
        .map((p) => p.text ?? "")
        .join("\n")
        .trim();
      if (!txt) return;
      setMeddelanden((p) => [...p, { roll: "användare", innehåll: txt }]);
      setVäntar(true);
      try {
        const s = await chatApi(jobId, txt);
        setMeddelanden((p) => [...p, {
          roll: "assistent", innehåll: s.svar,
          verktyg: s.verktyg, ändrade: s.ändrade,
        }]);
        if (s.ändrade?.length) { onÄndrade(); qc.invalidateQueries({ queryKey: ["job", jobId] }); }
      } catch (e) {
        setMeddelanden((p) => [...p, { roll: "assistent", innehåll: `⚠️ något gick fel: ${e}` }]);
      } finally {
        setVäntar(false);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [meddelanden, väntar]);

  const runtime = useExternalStoreRuntime(runtimes);

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <ThreadPrimitive.Root className="flex h-full min-h-0 flex-col rounded-xl border border-[color:var(--color-ink-2)] bg-white">
        <div className="border-b border-[color:var(--color-ink-2)] px-3 py-2 text-[12.5px] font-semibold text-[color:var(--color-ink)]">
          💬 Agent (gemma-4) — en fråga i taget om gap & dokument
        </div>
        <ThreadPrimitive.Viewport className="min-h-0 flex-1 overflow-y-auto py-2">
          <ThreadPrimitive.If empty>
            <EmptyHint />
          </ThreadPrimitive.If>
          <ThreadPrimitive.Messages
            components={{ UserMessage: UserBubble, AssistantMessage: AssistantBubble }}
          />
          <ThreadPrimitive.If running>
            <div className="px-3 py-1.5 text-[12.5px] text-[color:var(--color-muted)]">
              ⏳ agenten arbetar…
            </div>
          </ThreadPrimitive.If>
        </ThreadPrimitive.Viewport>
        <ComposerPrimitive.Root className="relative flex items-end gap-2 border-t border-[color:var(--color-ink-2)] p-2">
          <ComposerPrimitive.Input
            placeholder="Svara på agentens fråga, eller ställ en egen…"
            className="min-h-9 max-h-36 min-w-0 flex-1 resize-y rounded-lg border border-[color:var(--color-ink-2)] bg-white px-3 py-2 text-[13px] outline-none focus:border-[color:var(--color-accent)]"
          />
          <DictateButton
            className="mb-0.5"
            onText={(t) => {
              const composer = runtime.thread.composer;
              const nu = composer.getState().text;
              composer.setText(nu ? `${nu.trimEnd()} ${t}` : t);
            }}
          />
          <ComposerPrimitive.Send className="mb-0.5 shrink-0 rounded-lg bg-[color:var(--color-accent)] px-3 py-2 text-[12.5px] font-semibold text-white transition disabled:opacity-40">
            Skicka ↵
          </ComposerPrimitive.Send>
        </ComposerPrimitive.Root>
      </ThreadPrimitive.Root>
    </AssistantRuntimeProvider>
  );
}
