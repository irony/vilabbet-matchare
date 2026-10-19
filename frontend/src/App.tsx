import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Api, type JobState } from "@/lib/api";
import StartScreen from "@/screens/StartScreen";
import WorkingScreen from "@/screens/WorkingScreen";
import SummaryScreen from "@/screens/SummaryScreen";
import PickScreen from "@/screens/PickScreen";
import KravSumScreen from "@/screens/KravSumScreen";
import AnalysisScreen from "@/screens/AnalysisScreen";
import FlowScreen from "@/screens/FlowScreen";
import BevisSumScreen from "@/screens/BevisSumScreen";
import ResultScreen from "@/screens/ResultScreen";
import FeedbackScreen from "@/screens/FeedbackScreen";
import FocusScreen from "@/screens/FocusScreen";
import GapScreen from "@/screens/GapScreen";
import EuroScreen from "@/screens/EuroScreen";
import ErrorScreen from "@/screens/ErrorScreen";

/** Lokal steg-maskin: fas från servern + användarens grind-val. */
type Stage =
  | "start" | "working" | "summary" | "pick" | "kravsum"
  | "analysis" | "bevissum" | "result" | "feedback" | "fokus" | "gap" | "euro" | "error";

const PROG: Record<Stage, number> = {
  start: 4, working: 25, summary: 40, pick: 46, kravsum: 55,
  analysis: 72, bevissum: 85, result: 95, feedback: 100, fokus: 100, gap: 100, euro: 100, error: 0,
};

export default function App() {
  // inbäddningsläge för slides: ?vy=<skärm> tvingar en skärm, &ren=1 döljer chrome
  const [forced] = useState<Stage | null>(() => {
    const v = new URLSearchParams(window.location.search).get("vy");
    const ok: Stage[] = ["start", "working", "summary", "pick", "kravsum",
      "analysis", "bevissum", "result", "feedback", "fokus", "gap", "euro", "error"];
    return ok.includes(v as Stage) ? (v as Stage) : null;
  });
  const [ren] = useState(
    () => new URLSearchParams(window.location.search).get("ren") === "1",
  );
  const [stage, setStage] = useState<Stage>(forced ?? "start");
  const [workTitle, setWorkTitle] = useState(forced === "analysis" ? "Bevisarbetet" : "Letar …");
  const [visVy, setVisVy] = useState<"flöde" | "logg">("logg"); // vit klassisk sida som standard — översiktsvyn är en opt-in
  const [selection, setSelection] = useState<Set<string>>(new Set());
  const jobRef = useRef<string | null>(null);

  const [jobId, setJobId] = useState<string | null>(null);
  // återuppta jobb från ?jobb= (t.ex. länk ur resultatmail när fliken stängts)
  const [resumed, setResumed] = useState(false);
  useEffect(() => {
    const p = new URLSearchParams(window.location.search).get("jobb");
    if (p && /^[a-f0-9]{8,}$/i.test(p)) { setJobId(p); setResumed(true); }
  }, []);

  const { data: job } = useQuery<JobState>({
    queryKey: ["job", jobId],
    queryFn: () => Api.job(jobId!),
    enabled: !!jobId,
    refetchInterval: (q) => {
      const ph = q.state.data?.phase;
      return ph === "klar" || ph === "fel" ? false : 1500;
    },
    refetchIntervalInBackground: true,
  });

  // meddela föräldrafönstret (presentationssliderna) vilket jobb som kör —
  // så kan övriga steg följa samma företag
  useEffect(() => {
    if (jobId && window.parent !== window) {
      window.parent.postMessage({ typ: "vilabbet-jobb", id: jobId }, "*");
    }
  }, [jobId]);

  // fas → automatskärm (fastsändringer baserade på serverns state)
  useEffect(() => {
    if (!job || forced) return;
    const p = job.phase;
    if (p === "fel") { setStage("error"); return; }
    setStage((s) => {
      // återupptaget jobb: mappa serverfas direkt till skärm vid första svar
      if (resumed && s === "start") {
        setResumed(false);
        if (p === "matchar" && job.nyckelfakta) return "summary";
        if (p === "valet") return "summary";
        if (p === "kravsum") return "kravsum";
        if (p === "analyserar") { setWorkTitle("Letar bevis i er textmassa…"); return "analysis"; }
        if (p === "bevissum") return "bevissum";
        if (p === "dokumenterar") { setWorkTitle("Skriver dokumenten…"); return "analysis"; }
        if (p === "granskar") { setWorkTitle("Granskar med färska ögon…"); return "analysis"; }
        if (p === "klar") return "result";
        return "working";
      }
      if (s === "working") {
        // sammanfattningen visas så fort nyckelfaktan (och profilen) är
        // klara — matchningen rullar vidare i bakgrunden utan mer vänta
        if (job.nyckelfakta && (p === "skrapar" || p === "matchar"))
          return "summary";
        if (p === "valet") return "summary";
        if (p === "kravsum") return "kravsum";
        if (p === "skrapar") setWorkTitle("Skrapar din webbplats…");
        if (p === "matchar") setWorkTitle("Matchar mot 303 omgångar…");
        if (p === "hamtar_krav") setWorkTitle("Hämtar de identifierade kraven…");
      }
      if (s === "pick" && p === "kravsum") return "kravsum";
      if (s === "analysis") {
        if (p === "bevissum") return "bevissum";
        if (p === "klar") return "result";
        if (p === "analyserar") setWorkTitle("Letar bevis i er textmassa…");
        if (p === "dokumenterar") setWorkTitle("Skriver dokumenten…");
        if (p === "granskar") setWorkTitle("Granskar med färska ögon…");
      }
      return s;
    });
  }, [job]);

  // handlers
  const start = async (url: string, orgnr: string | null, email: string | null) => {
    setStage("working"); setWorkTitle("Skrapar din webbplats…");
    jobRef.current = null; setSelection(new Set());
    try {
      const r = await Api.start(url, orgnr, email);
      jobRef.current = r.job_id; setJobId(r.job_id);
    } catch (e) { setStage("error"); throw e; }
  };
  const confirmSummary = () => setStage("pick");
  const confirmSelection = async (dnrs: string[]) => {
    setStage("working"); setWorkTitle("Hämtar de identifierade kraven…");
    await Api.select(jobId!, dnrs);
  };
  const goAnalysis = async () => {
    setStage("analysis"); setWorkTitle("Letar bevis i er textmassa…");
    await Api.analysera(jobId!);
  };
  const goDocs = async () => {
    setStage("analysis"); setWorkTitle("Skriver dokumenten…");
    await Api.fortsatt(jobId!);
  };
  const restart = () => {
    setJobId(null); jobRef.current = null;
    setStage("start");
  };

  const shared = { job: job ?? null, selection, setSelection, jobId: jobId! };
  const prog = PROG[stage];

  return (
    <div className="min-h-full">
      {!ren && (
        <div className="fixed inset-x-0 top-0 z-50 h-[3px] bg-transparent">
          <div
            className="h-full bg-[color:var(--color-accent)] transition-[width] duration-500"
            style={{ width: `${prog}%` }}
          />
        </div>
      )}
      {stage === "start" && <StartScreen onStart={start} />}
      {(stage === "working" || stage === "analysis") && job && visVy === "flöde" && (
        <FlowScreen title={workTitle} job={job} />
      )}
      {(stage === "working" || stage === "analysis") && (!job || visVy === "logg") && stage === "working" && (
        <WorkingScreen title={workTitle} log={job?.log ?? []} items={job?.items ?? []} />
      )}
      {(stage === "working" || stage === "analysis") && (!job || visVy === "logg") && stage === "analysis" && (
        <AnalysisScreen title={workTitle} job={job ?? null} />
      )}
      {(stage === "working" || stage === "analysis") && !ren && (
        <button
          onClick={() => setVisVy(v => v === "flöde" ? "logg" : "flöde")}
          className="fixed bottom-4 left-4 z-50 rounded-full border border-[color:var(--color-line)] bg-white/90 px-3.5 py-1.5 text-[12.5px] shadow-sm backdrop-blur hover:bg-white"
        >{visVy === "flöde" ? "≣ visa logg" : "⤢ översiktsvy"}</button>
      )}
      {stage === "summary" && job && <SummaryScreen job={job} onNext={confirmSummary} onRestart={restart} />}
      {stage === "pick" && job && <PickScreen job={job} selection={selection} setSelection={setSelection} onNext={confirmSelection} />}
      {stage === "kravsum" && job && <KravSumScreen job={job} onNext={goAnalysis} onBack={() => setStage("pick")} count={selection.size} />}
      {stage === "bevissum" && job && <BevisSumScreen job={job} onNext={goDocs} onBack={() => setStage("pick")} />}
      {stage === "result" && job && <ResultScreen job={job} jobId={jobId!} onFeedback={() => setStage("feedback")} onRestart={restart} />}
      {stage === "feedback" && job && <FeedbackScreen job={job} jobId={jobId!} onBack={() => setStage("result")} />}
      {stage === "fokus" && jobId && <FocusScreen jobId={jobId} />}
      {stage === "gap" && job && jobId && <GapScreen job={job} jobId={jobId} />}
      {stage === "euro" && jobId && <EuroScreen jobId={jobId} />}
      {stage === "error" && <ErrorScreen msg={job?.error ?? undefined} onRestart={restart} />}
    </div>
  );
}
