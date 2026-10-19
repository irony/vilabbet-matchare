import { useEffect, useRef, useState } from "react";
import { Api, type BolagTraff } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/select";
import DictateButton from "@/components/DictateButton";
import { tillAdress } from "@/lib/diktera";

interface Gissning { namn: string; hits: BolagTraff[] }

const MAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

export default function StartScreen({
  onStart,
}: { onStart: (url: string, orgnr: string | null, email: string | null) => void }) {
  // inbäddningsläge (?ren=1): kort copy, inga steg-chips
  const ren = new URLSearchParams(window.location.search).get("ren") === "1";
  // mejl först — domänen avslöjar bolaget; privat domän → fråga om webbadress
  const [mode, setMode] = useState<"email" | "url">("email");
  const [email, setEmail] = useState("");
  const [mailDomän, setMailDomän] = useState<string | null>(null);
  const [url, setUrl] = useState("");
  const [orgnr, setOrgnr] = useState("");
  const [traffar, setTraffar] = useState<BolagTraff[]>([]);
  const [confirm, setConfirm] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [gissning, setGissning] = useState<Gissning | null>(null);
  const [frågaVisad, setFrågaVisad] = useState(false);
  const [gissar, setGissar] = useState(false);
  const [privvarning, setPrivvarning] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const gissTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // mejlflöde: mejl → /api/från_mail → gissning | fallback till url-läge
  useEffect(() => {
    const m = email.trim().toLowerCase();
    if (!MAIL_RE.test(m) || confirm) return;
    if (gissTimer.current) clearTimeout(gissTimer.current);
    gissTimer.current = setTimeout(async () => {
      setGissar(true);
      try {
        const r = await Api.frånMail(m);
        setGissar(false);
        if (!r.ok) {
          setPrivvarning(`@${r.domän} är en privat mejldomän —`);
          setMode("url");
          return;
        }
        setMailDomän(r.domän ?? null);
        const träffar = (r.träffar ?? []) as BolagTraff[];
        if (träffar.length) {
          setGissning({ namn: träffar[0].namn, hits: träffar });
          setFrågaVisad(true);
        } else {
          // domänen sa inget om bolaget — fråga ändå efter webbadress för säkerhets skull
          setMailDomän(r.domän ?? null);
          setFrågaVisad(false);
        }
      } catch {
        setGissar(false);
      }
    }, 800);
    return () => { if (gissTimer.current) clearTimeout(gissTimer.current); };
  }, [email, confirm]);

  // url-läge: domän → gissa_bolag → träffar
  useEffect(() => {
    const u = url.trim();
    if (mode !== "url" || !u.includes(".") || u.length < 4 || confirm) {
      if (mode === "url") { setGissning(null); setFrågaVisad(false); }
      return;
    }
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
  }, [url, mode, confirm]);

  // orgnr-autocomplete (register)
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

  const välj = (t: BolagTraff) => {
    setOrgnr(t.orgnr);
    setTraffar([]);
    setConfirm(`⚖️ ${t.namn} — bekräftat från Bolagsverkets register`);
    setFrågaVisad(false);
    // förvärm: starta sid-crawlen redan här, medan användaren trycker Nästa
    if (domän) Api.prefetch(domän);
  };

  const domän = mode === "email" ? (mailDomän ?? "") : url.trim().replace(/^https?:\/\//, "").replace(/^www\./, "");
  const redo = mode === "url" ? Boolean(url.trim()) : Boolean(mailDomän);
  const go = () => {
    setBusy(true);
    onStart(
      domän,
      orgnr.trim() || null,
      MAIL_RE.test(email.trim()) ? email.trim().toLowerCase() : null,
    );
  };

  return (
    <div className="mx-auto flex min-h-full w-full max-w-[800px] flex-col justify-center px-6 py-16">
      <p className="text-[13px] font-semibold uppercase tracking-[0.14em] text-[color:var(--color-accent)]">
        Vinnova-matcharen
      </p>
      <h1 className="mt-3 text-[clamp(30px,5vw,44px)] leading-[1.1]">
        Vi skriver er ansökan om innovationsstöd — automatiskt
      </h1>
      <p className="mt-4 max-w-[640px] text-[16.5px] leading-relaxed text-[color:var(--color-muted)]">
        {ren
          ? "Skriv in din arbetsmail — vi hittar bolaget, matchar det mot 303 öppna utlysningar och skriver ett ordentligt utkast. Ni granskar och skickar in."
          : "Åtminstone ett ordentligt utkast. Ni skriver in din arbetsmail — så hittar vi bolaget, matchar det mot alla 303 öppna utlysningar från Vinnova, Formas m.fl., kollar varje krav mot er webbplats och tar fram kravmatris, ansökningsutkast och en granskning med färska ögon. Ni granskar, kompletterar — och skickar in."}
      </p>
      {!ren && (
        <div className="mt-5 flex flex-wrap gap-2">
          {["1 · Hitta rätt utlysning", "2 · Beviskolla kraven", "3 · Klart utkast + granskning"].map((s) => (
            <span key={s} className="rounded-full border border-[color:var(--color-line)] bg-white px-3.5 py-1.5 text-[13px] text-[color:var(--color-muted)]">
              {s}
            </span>
          ))}
        </div>
      )}
      <div className="mt-8 flex flex-col gap-4">
        {mode === "email" && (
          <div className="flex max-w-[560px] items-center gap-2">
            <Input
              value={email}
              onChange={(e) => { setEmail(e.target.value); setConfirm(null); setFrågaVisad(false); setMailDomän(null); }}
              onKeyDown={(e) => e.key === "Enter" && redo && go()}
              placeholder="du@dittbolag.se"
              type="email"
              className="flex-1 !text-[21px] !rounded-none !border-0 !border-b-2 !px-1.5 !py-2.5"
              autoFocus
              enterKeyHint="go"
            />
            <DictateButton onText={(t) => setEmail(t)} transform={tillAdress} />
          </div>
        )}
        {privvarning && (
          <p className="text-[13px] text-[color:var(--color-warm)]">
            {privvarning} vilken webbplats hör bolaget till?
          </p>
        )}
        {mode === "url" && (
          <div className="flex max-w-[560px] items-center gap-2">
            <Input
              value={url}
              onChange={(e) => { setUrl(e.target.value); setConfirm(null); }}
              onKeyDown={(e) => e.key === "Enter" && url.trim() && go()}
              placeholder="t.ex. dittbolag.se"
              className="flex-1 !text-[21px] !rounded-none !border-0 !border-b-2 !px-1.5 !py-2.5"
              autoFocus
              enterKeyHint="go"
            />
            <DictateButton onText={(t) => setUrl(t)} transform={tillAdress} />
          </div>
        )}
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
            <div className="mt-2.5 flex flex-wrap gap-2.5">
              <Button size="sm" onClick={() => välj(gissning.hits[0])}>Ja, bekräfta</Button>
              {gissning.hits.length > 1 && gissning.hits[1] && (
                <Button size="sm" variant="outline" onClick={() => välj(gissning.hits[1])}>
                  Nej, det är {gissning.hits[1].namn}
                </Button>
              )}
              <Button size="sm" variant="ghost" onClick={() => setFrågaVisad(false)}>
                Nej — söker själv
              </Button>
            </div>
          </div>
        )}
        <div className="relative max-w-[480px]">
          <div className="flex items-center gap-2">
            <Input
              value={orgnr}
              onChange={(e) => { setOrgnr(e.target.value); setConfirm(null); }}
              placeholder="bolagsnamn eller org.nr 556xxx-xxxx (autocomplete)"
              className="flex-1 !text-[15px]"
              onKeyDown={(e) => e.key === "Enter" && redo && go()}
            />
            <DictateButton onText={(t) => setOrgnr((v) => (v ? `${v.trimEnd()} ${t}` : t))} />
          </div>
          {traffar.length > 0 && (
            <div className="absolute left-0 right-0 top-[calc(100%+5px)] z-20 overflow-hidden rounded-xl border-[1.5px] border-[color:var(--color-line)] bg-white shadow-xl">
              {traffar.map((t) => (
                <button
                  key={t.orgnr}
                  className="flex w-full cursor-pointer items-baseline gap-3 px-4 py-2.5 text-left text-[14px] hover:bg-[color:var(--color-accent-soft)]"
                  onClick={() => välj(t)}
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
        <div className="flex items-center gap-3">
          <Button onClick={go} disabled={!redo || busy}>{busy ? "Startar …" : "Nästa ↵"}</Button>
          {mode === "email" && (
            <button
              className="text-[13px] text-[color:var(--color-muted)] underline underline-offset-2 hover:text-[color:var(--color-ink)]"
              onClick={() => { setMode("url"); setPrivvarning(null); }}
            >
              jag vill ange webbadressen själv
            </button>
          )}
        </div>
      </div>
      <p className="mt-6 text-[12.5px] text-[color:var(--color-muted)]">
        tryck <kbd className="rounded border border-[color:var(--color-line)] bg-white px-1.5 py-0.5">Enter</kbd> för att gå vidare
      </p>
    </div>
  );
}
