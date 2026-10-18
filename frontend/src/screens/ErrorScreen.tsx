import { Button } from "@/components/ui/button";

export default function ErrorScreen({ msg, onRestart }: { msg?: string; onRestart: () => void }) {
  return (
    <div className="flex min-h-full flex-col items-center justify-center px-6">
      <p className="text-[13px] font-semibold uppercase tracking-[0.14em] text-[color:var(--color-bad)]">
        Något gick fel
      </p>
      <h1 className="mt-3 text-[clamp(28px,5vw,44px)]">Hoppsan.</h1>
      <p className="mt-4 max-w-[560px] text-center text-[15.5px] leading-relaxed text-[color:var(--color-muted)]">
        {msg ?? "Okänt fel."}
      </p>
      <Button variant="outline" className="mt-8" onClick={onRestart}>Börja om</Button>
    </div>
  );
}
