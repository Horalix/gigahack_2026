// In-memory state for the clickable prototype. Everything resets on a full
// page reload. Each function here stands in for an API call the real app will
// make; the comments name the route it would map to.

import { groupFor, participants, patients, sampleActions, sampleSegments, SAMPLE_DURATION_MS, SAMPLE_SPEAKERS, SAMPLE_SUMMARY, seedMeetings, ORG } from "./fixtures";
import type { Action, JobStage, Meeting, MeetingType, Patient, SourceMedia } from "./types";

interface UndoEntry {
  segmentId: string;
  text: string;
  origin: "asr" | "human_edit";
}

export const db = $state({
  patients,
  meetings: seedMeetings(),
  undo: {} as Record<string, UndoEntry[]>,
});

export function getMeeting(id: string): Meeting | undefined {
  return db.meetings.find((m) => m.id === id);
}

export function getPatient(id: string): Patient | undefined {
  return db.patients.find((p) => p.id === id);
}

export function participantName(id: string | null): string | null {
  return id ? (participants.find((p) => p.id === id)?.displayName ?? null) : null;
}

export function speakerLabel(meeting: Meeting, clusterId: string | null): { name: string; known: boolean } {
  if (!clusterId) return { name: "Unknown speaker", known: false };
  const person = participantName(meeting.speakers[clusterId] ?? null);
  if (person) return { name: person, known: true };
  return { name: `Speaker ${Number(clusterId.replace(/\D/g, "")) || "?"}`, known: false };
}

// --- Patient search: GET /api/patients?q=&cursor= (PBI-006) -----------------

function searchKey(value: string): string {
  // Diacritic-insensitive, so "turcanu" finds "Țurcanu" and "stefan" finds "Ștefan".
  return value.normalize("NFD").replace(/\p{M}/gu, "").toLocaleLowerCase();
}

export interface PatientPage {
  items: Patient[];
  total: number;
  offset: number;
  hasMore: boolean;
}

export async function searchPatients(query: string, offset: number, pageSize = 25): Promise<PatientPage> {
  // Simulated network delay, so loading and stale-response handling are visible.
  await new Promise((r) => setTimeout(r, 150 + Math.random() * 350));
  const q = searchKey(query.trim());
  const matches = db.patients
    .filter((p) => !q || searchKey(p.displayName).includes(q) || searchKey(p.reference ?? "").includes(q))
    .sort((a, b) => searchKey(a.displayName).localeCompare(searchKey(b.displayName)) || a.id.localeCompare(b.id));
  return {
    items: matches.slice(offset, offset + pageSize),
    total: matches.length,
    offset,
    hasMore: offset + pageSize < matches.length,
  };
}

export function meetingsForPatient(patientId: string): Meeting[] {
  return db.meetings.filter((m) => m.patientIds.includes(patientId));
}

// --- Create + process: POST /api/meetings, /audio, /jobs --------------------

export interface NewMeetingInput {
  title: string;
  recordedAt: string;
  meetingType: MeetingType;
  outputLanguage: "ro" | "ru" | "en";
  patientIds: string[];
  source: SourceMedia;
}

export function createMeeting(input: NewMeetingInput): string {
  const id = `mtg-${Date.now().toString(36)}`;
  const now = new Date().toISOString();
  // The prototype has no ASR, so every new meeting gets the sample transcript.
  const segments = sampleSegments(id);
  const meeting: Meeting = {
    id,
    organizationId: ORG,
    title: input.title,
    recordedAt: input.recordedAt,
    timeZone: "Europe/Chisinau",
    meetingType: input.meetingType,
    outputLanguage: input.outputLanguage,
    patientLinkIds: [],
    participantIds: participants.map((p) => p.id),
    status: "processing",
    transcriptRevision: 1,
    createdAt: now,
    updatedAt: now,
    patientIds: input.patientIds,
    speakers: { ...SAMPLE_SPEAKERS },
    source: { ...input.source, durationMs: input.source.durationMs || SAMPLE_DURATION_MS },
    job: { id: `${id}-job`, meetingId: id, state: "queued", stage: "decode", profileId: "laptop8", errorCode: null, createdAt: now, updatedAt: now },
    segments,
    actions: sampleActions(id, input.recordedAt, segments),
    summary: SAMPLE_SUMMARY,
    minutesStale: false,
    delivery: null,
  };
  db.meetings.unshift(meeting);
  return id;
}

export const STAGES: { stage: JobStage; label: string; detail: string }[] = [
  { stage: "decode", label: "Preparing audio", detail: "Decoding the recording locally and extracting the speech track." },
  { stage: "transcribe", label: "Transcribing", detail: "Recognising Romanian, Russian and English speech, keeping each in its original language." },
  { stage: "extract", label: "Finding decisions", detail: "The local model proposes decisions, owners and deadlines, each tied to a quote." },
  { stage: "validate", label: "Checking evidence", detail: "Every item must match a real quote; anything unproven stays unresolved." },
  { stage: "render", label: "Drafting minutes", detail: "Building the minutes document from the checked items." },
];

/** Advance a job one stage. Returns true once processing has finished. */
export function tickJob(id: string): boolean {
  const m = getMeeting(id);
  if (!m) return true;
  const job = m.job;
  if (job.state === "failed" || job.state === "ready" || job.state === "needs_review") return true;
  job.updatedAt = new Date().toISOString();
  if (job.state === "queued") {
    job.state = "running";
    job.stage = "decode";
    return false;
  }
  const order = STAGES.map((s) => s.stage);
  const next = order.indexOf(job.stage) + 1;
  if (next < order.length) {
    job.stage = order[next];
    return false;
  }
  job.stage = "complete";
  const open = m.actions.some((a) => a.status === "unresolved" || a.status === "proposed");
  job.state = open ? "needs_review" : "ready";
  m.status = open ? "needs_review" : "ready";
  return true;
}

export function retryJob(id: string): void {
  const m = getMeeting(id);
  if (!m) return;
  // Retrying the failed demo meeting "recovers" it with the sample content.
  if (!m.segments.length) {
    m.segments = sampleSegments(id);
    m.actions = sampleActions(id, m.recordedAt, m.segments);
    m.summary = SAMPLE_SUMMARY;
  }
  m.status = "processing";
  m.job.state = "queued";
  m.job.stage = "decode";
  m.job.errorCode = null;
}

// --- Transcript review: PATCH /api/meetings/{id}/review (PBI-013/014) ---------

export function editSegment(meetingId: string, segmentId: string, text: string): void {
  const m = getMeeting(meetingId);
  const s = m?.segments.find((x) => x.id === segmentId);
  if (!m || !s || s.text === text) return;
  // Push through the reactive proxy. `(db.undo[id] ??= []).push(...)` would push
  // into the raw array the expression returns, and the UI would never see it.
  if (!db.undo[meetingId]) db.undo[meetingId] = [];
  db.undo[meetingId].push({ segmentId, text: s.text, origin: s.origin });
  s.text = text;
  s.origin = "human_edit";
  m.transcriptRevision += 1;
  s.transcriptRevision = m.transcriptRevision;
  // Minutes were drafted from the earlier text, so they are out of date now.
  m.minutesStale = true;
}

export function undoLastEdit(meetingId: string): void {
  const entry = db.undo[meetingId]?.pop();
  const m = getMeeting(meetingId);
  const s = m?.segments.find((x) => x.id === entry?.segmentId);
  if (!entry || !m || !s) return;
  s.text = entry.text;
  s.origin = entry.origin;
  m.transcriptRevision += 1;
  m.minutesStale = true;
}

export function canUndo(meetingId: string): boolean {
  return (db.undo[meetingId]?.length ?? 0) > 0;
}

export function regenerateMinutes(meetingId: string): void {
  const m = getMeeting(meetingId);
  if (m) m.minutesStale = false;
}

// --- Minutes review ---------------------------------------------------------

function refreshStatus(action: Action): void {
  if (action.status !== "unresolved") return;
  const needsOwner = action.kind === "action";
  if ((!needsOwner || action.ownerParticipantId) && action.dueAt) action.status = "confirmed";
}

export function assignOwner(meetingId: string, actionId: string, participantId: string | null): void {
  const a = getMeeting(meetingId)?.actions.find((x) => x.id === actionId);
  if (!a) return;
  a.ownerParticipantId = participantId;
  a.ownerEvidence = [];
  a.resolvedByReviewer = true;
  refreshStatus(a);
}

export function setDueDate(meetingId: string, actionId: string, day: string | null): void {
  const a = getMeeting(meetingId)?.actions.find((x) => x.id === actionId);
  if (!a) return;
  a.dueAt = day || null;
  a.resolvedByReviewer = true;
  refreshStatus(a);
}

// --- Delivery (Affan's SMTP work, simulated here) ------------------------------

export function sendMinutes(meetingId: string): void {
  const m = getMeeting(meetingId);
  if (!m) return;
  m.status = "ready";
  m.delivery = {
    status: "sent_simulated",
    groupId: groupFor(m.meetingType).id,
    sentAt: new Date().toISOString(),
    snapshotRevision: m.transcriptRevision,
  };
}
