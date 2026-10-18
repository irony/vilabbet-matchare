import { useEffect, useRef, useState } from "react";
import { Api, type BolagTraff } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/select";

export default function StartScreen({ onStart }: { onStart: (url: string, orgnr: string | null) => void }) {
  const [url, setUrl] = useState("");
  const [orgnr, setOrgnr] = useState("");
  const [traffar, setTraffar] = useState<BolagTraff[]>([]);
  const [confirm, setConfirm] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // domän → bolagsgissning → registerträffar (förslag före submit)
  interface Gissning { namn: string; hits: BolagTraff[] }
  const [gissning, setGissning] = useState<Gissning | null>(null);
  const [frågaVisad, setFrågaVisad] = useState(false);
  const [gissar, setGissar] = useState(false);
  const gissTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const u = url.trim();
    if (!u.includes(".") || u.length < 4 || confirm) { setGissning(null); setFrågaVisad(false); return; }
    if (gissTimer.current) clearTimeout(gissTimer.current);
    gissTimer.current = setTimeout(async () => {
      setGissar(true);
      try {
        const r = await fetch("/api/gissa_bolag", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url: u }),
        }).then((x) => x.json());
        const träffar = (r["träffar"] ?? []) as BolagTraff[];
        if (träffar.length) { setGissning({ namn: träffar[0].namn, hits: träffar }); setFrågaVisad(true); }
      } catch { /* gissning valfri */ }
      finally { setGissar(false); }
    }, 900);
    return () => { if (gissTimer.current) clearTimeout(gissTimer.current); };
  }, [url, confirm]);

  useEffect(() => {
    if (orgnr.trim().length < 2) { setTraffar([]); return; }
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      try {
        const r = await Api.bolag(orgnr.trim());
        setTraffar(r["träffar"] ?? []);
      } catch { setTraffar([]); }
    }, 250);
    return () => { if (timer.current) clearTimeout(timer.current); };
  }, [orgnr]);

  const go = () => { setBusy(true); onStart(url.trim(), orgnr.trim() || null); };

  return (
    <div className="mx-auto flex min-h-full w-full max-w-[800px] flex-col justify-center px-6 py-16">
      <p className="text-[13px] font-semibold uppercase tracking-[0.14em] text-[color:var(--color-accent)]">
        Vinnova-matcharen
      </p>
      <h1 className="mt-3 text-[clamp(30px,5vw,44px)] leading-[1.1]">
        Hej! Vilken webbplats hör bolaget till?
      </h1>
      <p className="mt-4 max-w-[640px] text-[16.5px] leading-relaxed text-[color:var(--color-muted)]">
        Vi skrapar sidan i bakgrunden, bygger en profil och matchar mot korpusets
        alla ansökningsomgångar — bara de som ligger framåt i tiden.
      </p>
      <div className="mt-8 flex flex-col gap-4">
        <Input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && url.trim() && go()}
          placeholder="t.ex. dittbolag.se"
          className="max-w-[560px] !text-[21px] !rounded-none !border-0 !border-b-2 !px-1.5 !py-2.5"
          autoFocus
          enterKeyHint="go"
        />
        {gissar && (
          <p className="flex items-center gap-2 text-[13px] text-[color:var(--color-muted)]">
            <Spinner className="size-4" /> Kollar upp vilket bolag som hör till domänen …
          </p>
        )}
        {frågaVisad && gissning && (
          <div className="max-w-[560px] rounded-xl border-[1.5px] border-[color:var(--color-accent)]/40 bg-[color:var(--color-accent-soft)] px-4 py-3">
            <p className="text-[14.5px]">
              Vi tror det är <b>{gissning.namn}</b>{" "}
              <span className="tabular-nums text-[color:var(--color-muted)]">({gissning.hits[0].orgnr})</span>.
              Är det här bolaget?
            </p>
            {gissning.hits.length > 1 && (
              <p className="mt-1 text-[12.5px] text-[color:var(--color-muted)]">
                andra träffar: {gissning.hits.slice(1).map((h) => `${h.namn} (${h.orgnr})`).join(", ")}
              </p>
            )}
            <div className="mt-2.5 flex gap-2.5">
              <Button size="sm" onClick={() => {
                setOrgnr(gissning.hits[0].orgnr);
                setConfirm(`⚖️ ${gissning.namn} — bekräftat från Bolagsverkets register`);
                setFrågaVisad(false);
              }}>Ja, bekräfta</Button>
              {gissning.hits.length > 1 && gissning.hits[1] && (
                <Button size="sm" variant="outline" onClick={() => {
                  setOrgnr(gissning.hits[1].orgnr);
                  setConfirm(`⚖️ ${gissning.hits[1].namn} — bekräftat från Bolagsverkets register`);
                  setFrågaVisad(false);
                }}>Nej, det är {gissning.hits[1].namn}</Button>
              )}
              <Button size="sm" variant="ghost" onClick={() => setFrågaVisad(false)}>
                Nej — söker själv
              </Button>
            </div>
          </div>
        )}
        <div className="relative max-w-[480px]">
          <Input
            value={orgnr}
            onChange={(e) => { setOrgnr(e.target.value); setConfirm(null); }}
            placeholder="bolagsnamn eller org.nr 556xxx-xxxx (autocomplete)"
            className="!text-[15px]"
            onKeyDown={(e) => e.key === "Enter" && url.trim() && go()}
          />
          {traffar.length > 0 && (
            <div className="absolute left-0 right-0 top-[calc(100%+5px)] z-20 overflow-hidden rounded-xl border-[1.5px] border-[color:var(--color-line)] bg-white shadow-xl">
              {traffar.map((t) => (
                <button
                  key={t.orgnr}
                  className="flex w-full cursor-pointer items-baseline gap-3 px-4 py-2.5 text-left text-[14px] hover:bg-[color:var(--color-accent-soft)]"
                  onClick={() => { setOrgnr(t.orgnr); setTraffar([]); setConfirm(`⚖️ ${t.namn} — direkt från Bolagsverkets register`); }}
                >
                  <b className="min-w-[105px] font-semibold tabular-nums">{t.orgnr}</b>
                  <span className="text-[color:var(--color-muted)]">{t.namn}</span>
                  <span className="ml-auto text-[12.5px] text-[color:var(--color-muted)]">
                    {t.form}{t.grundat_ar ? ` · ${t.grundat_ar}` : ""}{t.ort ? ` · ${t.ort}` : ""}
                  </span>
                </button>
              ))}
            </div>
          )}
          {confirm && <p className="mt-2 text-[13px] text-[color:var(--color-ok)]">{confirm}</p>}
        </div>
        <div>
          <Button onClick={go} disabled={!url.trim() || busy}>{busy ? "Startar …" : "Nästa ↵"}</Button>
        </div>
      </div>
      <p className="mt-6 text-[12.5px] text-[color:var(--color-muted)]">
        tryck <kbd className="rounded border border-[color:var(--color-line)] bg-white px-1.5 py-0.5">Enter</kbd> för att gå vidare
      </p>
    </div>
  );
}
