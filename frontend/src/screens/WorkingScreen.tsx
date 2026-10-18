import type { Item } from "@/lib/api";
import FlySky from "@/components/FlySky";
import { Spinner } from "@/components/ui/select";

export default function WorkingScreen({ title, log, items }: { title: string; log: string[]; items: Item[] }) {
  return (
    <div className="relative flex min-h-full items-center justify-center">
      <FlySky items={items} />
      <div className="relative z-10 w-full max-w-[560px] rounded-2xl border-[1.5px] border-[color:var(--color-line)] bg-[color:var(--color-background)]/90 p-8 text-center backdrop-blur">
        <Spinner className="mx-auto size-7" />
        <h1 className="mt-5 text-[clamp(24px,4vw,34px)]">{title}</h1>
        <div className="mt-5 max-h-44 overflow-hidden text-left text-[13px] leading-6 text-[color:var(--color-muted)]">
          {log.slice(-8).map((l, i) => <div key={i}>· {l}</div>)}
        </div>
      </div>
    </div>
  );
}
