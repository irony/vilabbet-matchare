import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Api, type JobState } from "@/lib/api";
import StartScreen from "@/screens/StartScreen";
import WorkingScreen from "@/screens/WorkingScreen";
import SummaryScreen from "@/screens/SummaryScreen";
import PickScreen from "@/screens/PickScreen";
import KravSumScreen from "@/screens/KravSumScreen";
import AnalysisScreen from "@/screens/AnalysisScreen";
import BevisSumScreen from "@/screens/BevisSumScreen";
import ResultScreen from "@/screens/ResultScreen";
import FeedbackScreen from "@/screens/FeedbackScreen";
import ErrorScreen from "@/screens/ErrorScreen";

/** Lokal steg-maskin: fas från servern + användarens grind-val. */
type Stage =
  | "start" | "working" | "summary" | "pick" | "kravsum"
  | "analysis" | "bevissum" | "result" | "feedback" | "error";

const PROG: Record<Stage, number> = {
  start: 4, working: 25, summary: 40, pick: 46, kravsum: 55,
  analysis: 72, bevissum: 85, result: 95, feedback: 100, error: 0,
};

export default function App() {
  const [stage, setStage] = useState<Stage>("start");
  const [workTitle, setWorkTitle] = useState("Letar …");
  const [selection, setSelection] = useState<Set<string>>(new Set());
  const jobRef = useRef<string | null>(null);

  const [jobId, setJobId] = useState<string | null>(null);

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

  // fas → automatskärm (fastsändringer baserade på serverns state)
  useEffect(() => {
    if (!job) return;
    const p = job.phase;
    if (p === "fel") { setStage("error"); return; }
    setStage((s) => {
      if (s === "working") {
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
  const start = async (url: string, orgnr: string | null) => {
    setStage("working"); setWorkTitle("Skrapar din webbplats…");
    jobRef.current = null; setSelection(new Set());
    try {
      const r = await Api.start(url, orgnr);
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
      <div className="fixed inset-x-0 top-0 z-50 h-[3px] bg-transparent">
        <div
          className="h-full bg-[color:var(--color-accent)] transition-[width] duration-500"
          style={{ width: `${prog}%` }}
        />
      </div>
      {stage === "start" && <StartScreen onStart={start} />}
      {stage === "working" && <WorkingScreen title={workTitle} log={job?.log ?? []} items={job?.items ?? []} />}
      {stage === "summary" && job && <SummaryScreen job={job} onNext={confirmSummary} onRestart={restart} />}
      {stage === "pick" && job && <PickScreen job={job} selection={selection} setSelection={setSelection} onNext={confirmSelection} />}
      {stage === "kravsum" && job && <KravSumScreen job={job} onNext={goAnalysis} onBack={() => setStage("pick")} count={selection.size} />}
      {stage === "analysis" && <AnalysisScreen title={workTitle} job={job ?? null} />}
      {stage === "bevissum" && job && <BevisSumScreen job={job} onNext={goDocs} onBack={() => setStage("pick")} />}
      {stage === "result" && job && <ResultScreen job={job} jobId={jobId!} onFeedback={() => setStage("feedback")} onRestart={restart} />}
      {stage === "feedback" && job && <FeedbackScreen job={job} jobId={jobId!} onBack={() => setStage("result")} />}
      {stage === "error" && <ErrorScreen msg={job?.error ?? undefined} onRestart={restart} />}
    </div>
  );
}
