import type { Language, Meeting, MeetingType } from "./types";

export function formatMs(ms: number): string {
  const total = Math.floor(ms / 1000);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = String(total % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${s}` : `${m}:${s}`;
}

export function formatDateTime(isoString: string, timeZone = "Europe/Chisinau"): string {
  return new Intl.DateTimeFormat("en-GB", { timeZone, dateStyle: "medium", timeStyle: "short" }).format(
    new Date(isoString),
  );
}

/** Date-only YYYY-MM-DD, shown without shifting across time zones. */
export function formatDay(day: string): string {
  const [y, m, d] = day.split("-").map(Number);
  return new Intl.DateTimeFormat("en-GB", { timeZone: "UTC", weekday: "short", day: "numeric", month: "short", year: "numeric" }).format(
    new Date(Date.UTC(y, m - 1, d)),
  );
}

export function formatBytes(bytes: number | null): string {
  if (bytes == null) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(0)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
}

export const LANGUAGE_LABEL: Record<Language, string> = {
  ro: "RO",
  ru: "RU",
  en: "EN",
  mul: "Mixed",
  und: "?",
};

export const MEETING_TYPE_LABEL: Record<MeetingType, string> = {
  medical: "Medical",
  executive: "Executive",
  administrative: "Administrative",
};

export type Tone = "neutral" | "accent" | "success" | "attention" | "danger";

export function meetingStatus(meeting: Meeting): { label: string; tone: Tone } {
  if (meeting.delivery) return { label: "Sent", tone: "success" };
  switch (meeting.status) {
    case "draft":
      return { label: "Draft", tone: "neutral" };
    case "processing":
      return { label: "Processing", tone: "accent" };
    case "transcript_ready":
    case "needs_review":
      return { label: "Needs review", tone: "attention" };
    case "ready":
      return { label: "Ready to send", tone: "accent" };
    case "failed":
      return { label: "Failed", tone: "danger" };
    case "archived":
      return { label: "Archived", tone: "neutral" };
  }
}

/** Where a meeting should open, based on how far along it is. */
export function meetingHref(meeting: Meeting): string {
  if (meeting.delivery) return `/meetings/${meeting.id}/sent`;
  if (meeting.job.stage !== "complete" || meeting.status === "failed") return `/meetings/${meeting.id}`;
  if (meeting.status === "ready") return `/meetings/${meeting.id}/minutes`;
  return `/meetings/${meeting.id}/review`;
}

/** Turn a datetime-local value into RFC 3339 with the Chisinau offset in force at that moment. */
export function chisinauIso(localValue: string): string {
  const guess = new Date(`${localValue}:00Z`);
  const offset =
    new Intl.DateTimeFormat("en-US", { timeZone: "Europe/Chisinau", timeZoneName: "longOffset" })
      .formatToParts(guess)
      .find((p) => p.type === "timeZoneName")
      ?.value.replace("GMT", "") || "+00:00";
  return `${localValue}:00${offset === "" ? "+00:00" : offset}`;
}

export function nowLocalInput(): string {
  const parts = new Intl.DateTimeFormat("sv-SE", {
    timeZone: "Europe/Chisinau",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date());
  return parts.replace(" ", "T");
}
