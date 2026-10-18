import { useEffect, useRef, useState } from "react";
import type { Item } from "@/lib/api";
import { cn } from "@/lib/utils";

const STATUS_CLASS: Record<string, string> = {
  styrkt_uppfyllt: "border-l-4 border-[color:var(--color-ok)]",
  okant: "border-l-4 border-[#c9beb0]",
  styrkt_ej_uppfyllt: "border-l-4 border-[color:var(--color-bad)]",
  strukturellt: "border-l-4 border-[#a8a29e]",
};

/** Flygande beviskort — köar nya items 1/900ms så himlen ser levande ut. */
export default function FlySky({ items }: { items: Item[] }) {
  const [cards, setCards] = useState<(Item & { key: number; x: number; dur: number; delay: number })[]>([]);
  const queueRef = useRef<Item[]>([]);
  const seenRef = useRef(0);
  const keyRef = useRef(0);

  useEffect(() => {
    const fresh = items.slice(seenRef.current);
    if (fresh.length) {
      seenRef.current = items.length;
      queueRef.current.push(...fresh);
    }
  }, [items]);

  useEffect(() => {
    const timer = setInterval(() => {
      setCards((old) => {
        const it = queueRef.current.shift();
        if (!it) return old;
        const key = ++keyRef.current;
        const x = 4 + Math.random() * 78;
        const dur = 14 + Math.random() * 8;
        const delay = -Math.random() * 2;
        const max = 14;
        const next = [...old, { ...it, key, x, dur, delay }];
        return next.length > max ? next.slice(next.length - max) : next;
      });
    }, 900);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="pointer-events-none fixed inset-0 overflow-hidden" aria-hidden>
      <style>{`
        @keyframes flyup { from { transform: translateY(108vh) } to { transform: translateY(-20vh) } }
      `}</style>
      {cards.map((c) => (
        <div
          key={c.key}
          className={cn(
            "absolute w-[290px] rounded-2xl border border-[color:var(--color-line)] bg-white/92 p-3.5 shadow-lg backdrop-blur-sm",
            STATUS_CLASS[c.status ?? ""] ?? "border-l-4 border-[color:var(--color-accent)]/30"
          )}
          style={{ left: `${c.x}%`, animation: `flyup ${c.dur}s linear ${c.delay}s both` }}
        >
          <div className="text-[13px] font-medium leading-snug">{c.title}</div>
          {c.sub && <div className="mt-1 text-[11.5px] text-[color:var(--color-muted)] line-clamp-2">{c.sub}</div>}
        </div>
      ))}
    </div>
  );
}
