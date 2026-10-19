/** Typer speglade mot demo_server:s publika job-state (public_view). */

export type Fas =
  | "startad" | "skrapar" | "matchar" | "valet" | "hamtar_krav" | "kravsum"
  | "analyserar" | "bevissum" | "dokumenterar" | "granskar" | "klar" | "fel";

export interface NyckelFakta {
  orgnr?: string | null;
  namn?: string | null;
  grundat?: number | null;
  antal_anstallda?: number | null;
  omsattning_tkr?: number | null;
  balans_tkr?: number | null;
  ort?: string | null;
  form?: string | null;
  likvidation?: boolean | null;
  kalla?: string | null;
  register_driven?: boolean;
}

export interface MatchItem {
  dnr: string;
  title: string;
  funder?: string | null;
  closing_date?: string | null;
  state?: string | null;
  can_apply_now?: boolean;
  similarity?: number;
  matchpoang?: number;
  passform?: "bra" | "mojlig" | "dalig" | "ej_bedombar" | null;
  varfor?: string | null;
}

export interface KravSumItem {
  dnr: string;
  title: string;
  funder?: string | null;
  closing_date?: string | null;
  state?: string | null;
  similarity?: number;
  varfor?: string | null;
  n_krav_totalt: number;
  n_relevanta: number;
  krav_preview: { type: string; text: string }[];
  krav_full: { id: string; type: string; text: string }[];
}

export interface KravGrupp {
  text: string;
  amne: string;
  dnrs: string[];
  forekomster: { dnr: string; id: string; type?: string; text: string }[];
}

export type KravStatus = "styrkt_uppfyllt" | "styrkt_ej_uppfyllt" | "okant" | "strukturellt";

export interface AnalysResultat {
  dnr: string;
  title: string;
  funder?: string | null;
  closing_date?: string | null;
  state?: string | null;
  stats: Partial<Record<KravStatus, number>>;
  motor?: { eligible?: boolean | null; explanation?: string } | null;
}

export interface DokAnsokan {
  dnr: string;
  title: string;
  filnamn_md: string;
  filnamn_xlsx: string;
  md: string;
}

export interface GranskningsPunkt {
  nr: number;
  kategori: string;
  allvar: "blockerare" | "viktigt" | "förslag";
  krav_id?: string | null;
  avsnitt?: string;
  beskrivning: string;
  atgard: string;
  fråga?: string;
  stöd?: {
    fynd?: { sida?: string; citat?: string; kommentar?: string }[];
    personer?: string[];
    organisationer?: string[];
    förslag?: string;
  };
}

export interface Granskning {
  sammanfattning: string;
  punkter: GranskningsPunkt[];
  antal: Partial<Record<string, number>>;
  filnamn_xlsx?: string;
}

export interface Item {
  kind: string;
  title: string;
  sub?: string;
  status?: KravStatus;
  dnr?: string;
  id?: string;
  n?: number;   // ordinal i omgångens kravlista (req-items)
  doc?: string;
}

export interface ChatMsg {
  roll: "användare" | "assistent";
  innehåll: string;
  verktyg?: { verktyg: string; args: Record<string, unknown> }[];
  ändrade?: { kind: string; dnr: string; info: string }[];
}

export interface ChatSvar {
  svar: string;
  verktyg: { verktyg: string; args: Record<string, unknown> }[];
  ändrade: { kind: string; dnr: string; info: string }[];
}

export function chatApi(jobId: string, meddelande: string): Promise<ChatSvar> {
  return fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ job_id: jobId, meddelande }),
  }).then(async (r) => {
    if (!r.ok) throw new Error(String(r.status));
    return r.json() as Promise<ChatSvar>;
  });
}

export interface JobState {
  phase: Fas;
  step?: string;
  log: string[];
  items: Item[];
  done: boolean;
  mail_skickat?: boolean;
  error: string | null;
  company?: string;
  orgnr?: string | null;
  profil?: string;
  nyckelfakta?: NyckelFakta;
  matches?: MatchItem[];
  kravsum?: KravSumItem[];
  grupper?: KravGrupp[];
  results?: AnalysResultat[];
  docs?: { ansokningar: DokAnsokan[] };
  granskning?: Record<string, Granskning>;
  feedback?: Record<string, unknown>;
  chat?: ChatMsg[];
}

export interface BolagTraff {
  orgnr: string;
  namn: string;
  form?: string;
  grundat_ar?: number | null;
  ort?: string;
}

/* API-hjälpare */
async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`/api${path}`, init);
  if (!r.ok) {
    let msg = `${r.status}`;
    try { msg = (await r.json()).detail || msg; } catch { /* body saknas */ }
    throw new Error(msg);
  }
  return r.json() as Promise<T>;
}

export interface FrånMailSvar {
  ok: boolean;
  privat_domän?: boolean;
  domän?: string;
  namn_gissning?: string | null;
  träffar?: BolagTraff[];
  url?: string;
}

export const Api = {
  start: (url: string, orgnr?: string | null, email?: string | null) =>
    api<{ job_id: string }>("/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, orgnr, email }),
    }),
  // förvärm crawl-cachen så fort användaren valt sitt bolag — fire & forget
  prefetch: (url: string) => {
    fetch(`/api/prefetch`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    }).catch(() => {});
  },
  frånMail: (email: string) =>
    api<FrånMailSvar>("/från_mail", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    }),
  job: (jobId: string) => api<JobState>(`/job/${jobId}`),
  select: (jobId: string, dnrs: string[]) =>
    api<{ ok: boolean }>(`/select`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ job_id: jobId, dnrs }),
    }),
  analysera: (jobId: string) =>
    api<{ ok: boolean }>(`/analysera`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ job_id: jobId }),
    }),
  fortsatt: (jobId: string) =>
    api<{ ok: boolean }>(`/fortsatt`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ job_id: jobId }),
    }),
  bolag: (q: string) =>
    api<{ träffar: BolagTraff[] }>(`/bolag?q=${encodeURIComponent(q)}`),
  feedback: (jobId: string, dnrs: Record<string, {
    kommentar: string; punkter: Record<string, {
      status: string; ansvarig: string; kommentar: string;
    }>;
  }>) =>
    api<{ ok: boolean; svar: number }>(`/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ job_id: jobId, dnrs }),
    }),
};

export function redigerUrl(jobId: string, kind: "excel" | "ansokan" | "granskning", dnr: string) {
  return `/r/${jobId}/${kind}/${dnr}`;
}

export function dlUrl(jobId: string, kind: "excel" | "ansokan" | "granskning", dnr: string) {
  const ext = kind === "ansokan" ? "docx" : (kind === "granskning" || kind === "excel" ? "xlsx" : "md");
  return `/api/download/${jobId}/${kind}/${dnr}.${ext}`;
}
