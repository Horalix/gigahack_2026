// Helpers for the start-to-email flow: meeting defaults, review triage, and
// honest timing (server timestamps where the service records them, browser
// observation only where it does not).

import type { Job, Lang, Meeting } from "../api";

export type Classification = Meeting["classification"];
export const CLASSIFICATIONS: Classification[] = ["Medical", "Executive", "Administrative"];

/** What the workspace should do as soon as it opens a new meeting. */
export type Intent = { kind: "record" } | { kind: "upload"; file: File };

const pad = (n: number) => String(n).padStart(2, "0");
export const localDate = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
export const localTime = (d: Date) => `${pad(d.getHours())}:${pad(d.getMinutes())}`;

export function browserTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "";
  } catch {
    return "";
  }
}

const LOCALES: Record<Lang, string> = { en: "en-GB", ro: "ro-RO", ru: "ru-RU" };

/** "27 Sept 2026, 14:05" in the interface language. */
export function readableDateTime(date: string, time: string, lang: Lang): string {
  if (!date) return "";
  const [y, m, d] = date.split("-").map(Number);
  const [hh, mm] = (time || "00:00").split(":").map(Number);
  const value = new Date(y, m - 1, d, hh, mm);
  const day = new Intl.DateTimeFormat(LOCALES[lang], { day: "numeric", month: "short", year: "numeric" }).format(value);
  return time ? `${day}, ${time}` : day;
}

/** "Wed 30 Sept 2026" for the date that relative deadlines are counted from. */
export function readableDay(date: string, lang: Lang): string {
  const [y, m, d] = date.split("-").map(Number);
  return new Intl.DateTimeFormat(LOCALES[lang], { weekday: "short", day: "numeric", month: "short", year: "numeric" }).format(new Date(y, m - 1, d));
}

const UNITS: Record<Lang, { s: string; min: string; h: string }> = {
  en: { s: "s", min: "min", h: "h" },
  ro: { s: "s", min: "min", h: "h" },
  ru: { s: "с", min: "мин", h: "ч" },
};

/** 0.8 s, 42 s, 1 min 12 s, 1 h 02 min (units in the interface language). */
export function duration(seconds: number, lang: Lang = "en"): string {
  const u = UNITS[lang],
    s = Math.max(0, seconds);
  if (s < 10) return `${s.toFixed(1)} ${u.s}`;
  if (s < 60) return `${Math.round(s)} ${u.s}`;
  if (s < 3600) return `${Math.floor(s / 60)} ${u.min} ${pad(Math.floor(s % 60))} ${u.s}`;
  return `${Math.floor(s / 3600)} ${u.h} ${pad(Math.floor((s % 3600) / 60))} ${u.min}`;
}

// --- Review triage ----------------------------------------------------------

const settled = (c: any) => ["accepted", "excluded"].includes(c.review);

/** Items the service held for a person: flagged by the service or carrying an open issue. */
export const needsAttention = (c: any) => !settled(c) && (c.review === "needs_review" || c.body.uncertainties.length > 0);

/** Items with nothing flagged that approval will accept as extracted. */
export const clearToAccept = (c: any) => !settled(c) && !needsAttention(c);

// --- Jobs -------------------------------------------------------------------

export const isActive = (job?: Job) => !!job && ["queued", "running"].includes(job.state);

/** The newest job, and the newest full analysis (not a transcript-only reanalysis). */
export function latestJobs(jobs: Job[] = []) {
  const sorted = [...jobs].sort((a, b) => b.created - a.created);
  return { latest: sorted[0], full: sorted.find((j) => !j.transcript_only) };
}

/** When a job finished, as recorded by the service in its final progress update. */
export const finishedAt = (job?: Job) => (job?.state === "complete" ? job.progress?.updated_at : undefined);

// --- Delivery time ------------------------------------------------------------
// The service records when a delivery was queued but not when the mail server
// accepted it. This page records the moment it first sees "sent", and only for
// deliveries it watched while still queued, so the time is accurate to one poll.

const SENT_KEY = "notavra-sent-observed";
const watchedQueued = new Set<string>();

function readSent(): Record<string, number> {
  try {
    return JSON.parse(sessionStorage.getItem(SENT_KEY) || "{}");
  } catch {
    return {};
  }
}

export function observeDelivery(delivery: { id: string; state: string }): number | undefined {
  const seen = readSent();
  if (seen[delivery.id]) return seen[delivery.id];
  if (delivery.state === "queued") watchedQueued.add(delivery.id);
  if (delivery.state === "sent" && watchedQueued.has(delivery.id)) {
    seen[delivery.id] = Date.now() / 1000;
    try {
      sessionStorage.setItem(SENT_KEY, JSON.stringify(seen));
    } catch {
      /* storage unavailable: the time is shown until the page reloads */
    }
    return seen[delivery.id];
  }
  return undefined;
}

// --- Per-viewer convenience -------------------------------------------------------

const TYPE_KEY = "notavra-start-type";

export function rememberedType(): Classification {
  try {
    const value = localStorage.getItem(TYPE_KEY) as Classification | null;
    if (value && CLASSIFICATIONS.includes(value)) return value;
  } catch {
    /* storage unavailable */
  }
  return "Medical";
}

export function rememberType(value: Classification): void {
  try {
    localStorage.setItem(TYPE_KEY, value);
  } catch {
    /* storage unavailable */
  }
}
