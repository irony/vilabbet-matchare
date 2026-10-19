import { useEffect, useRef, useState } from "react";
import { startaDiktering } from "@/lib/diktera";
import { cn } from "@/lib/utils";

/**
 * Liten rec-knapp bredvid inputfält: klicka och prata i stället för att
 * skriva. Färdiga yttranden läggs till via onText; partiell text visas
 * kursiverat under knappen medan man pratar.
 */
export default function DictateButton({
  onText,
  transform,
  className,
}: {
  onText: (text: string) => void;
  /** t.ex. tillAdress för mejl/url-fält */
  transform?: (text: string) => string;
  className?: string;
}) {
  const [lyssnar, setLyssnar] = useState(false);
  const [fel, setFel] = useState(false);
  const [partial, setPartial] = useState("");
  const stoppaRef = useRef<(() => void) | null>(null);

  useEffect(() => () => stoppaRef.current?.(), []);

  const klicka = async () => {
    if (stoppaRef.current) {
      stoppaRef.current();
      stoppaRef.current = null;
      setLyssnar(false);
      setPartial("");
      return;
    }
    setFel(false);
    try {
      stoppaRef.current = await startaDiktering({
        onPartial: setPartial,
        onFinal: (t) => onText(transform ? transform(t) : t),
        onStatus: (s) => {
          if (s === "fel") {
            setFel(true);
            setLyssnar(false);
            stoppaRef.current = null;
          }
        },
      });
      setLyssnar(true);
    } catch {
      setFel(true);
    }
  };

  return (
    <span className={cn("relative inline-flex items-center", className)}>
      <button
        type="button"
        onClick={() => void klicka()}
        title={lyssnar ? "Stoppa dikteringen" : "Diktera — prata i stället för att skriva"}
        aria-label={lyssnar ? "Stoppa dikteringen" : "Diktera"}
        className={cn(
          "flex size-8 shrink-0 items-center justify-center rounded-full border text-[15px] transition",
          lyssnar
            ? "animate-pulse border-red-400 bg-red-50 text-red-500"
            : fel
              ? "border-red-300 bg-red-50 text-red-400"
              : "border-[color:var(--color-line)] bg-white text-[color:var(--color-muted)] hover:border-[color:var(--color-accent)] hover:text-[color:var(--color-accent)]",
        )}
      >
        {lyssnar ? "⏹" : "🎙"}
      </button>
      {partial && (
        <span className="absolute left-0 top-[calc(100%+4px)] z-30 max-w-[320px] truncate whitespace-nowrap rounded-md border border-[color:var(--color-line)] bg-white px-2 py-1 text-[12px] italic text-[color:var(--color-muted)] shadow-md">
          {partial}…
        </span>
      )}
      {fel && !lyssnar && (
        <span className="absolute left-0 top-[calc(100%+4px)] z-30 whitespace-nowrap rounded-md border border-red-200 bg-red-50 px-2 py-1 text-[12px] text-red-500 shadow-md">
          mikrofonen svarar inte
        </span>
      )}
    </span>
  );
}
