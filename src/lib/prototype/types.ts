// Shapes for the clickable prototype.
//
// Field names follow contracts/meeting.schema.json (contract 1.0) so these pages
// can move onto the real API with little renaming. Anything marked PROTOTYPE is
// not in the contract: it is a UI-side assumption to raise with the backend
// owner before relying on it.

export type Language = "ro" | "ru" | "en" | "und" | "mul";

export type MeetingType = "medical" | "executive" | "administrative";

export type MeetingStatus =
  | "draft"
  | "processing"
  | "transcript_ready"
  | "needs_review"
  | "ready"
  | "failed"
  | "archived";

export type JobState = "queued" | "running" | "needs_review" | "ready" | "failed" | "cancelled";
export type JobStage = "decode" | "transcribe" | "extract" | "validate" | "render" | "complete";

export type ActionStatus = "proposed" | "confirmed" | "rejected" | "cancelled" | "unresolved";

export interface Patient {
  id: string;
  organizationId: string;
  displayName: string;
  reference: string | null;
  status: "active" | "inactive";
  createdAt: string;
  updatedAt: string;
}

export interface Participant {
  id: string;
  displayName: string;
  role: string;
}

export interface Segment {
  id: string;
  meetingId: string;
  transcriptRevision: number;
  startMs: number;
  endMs: number;
  text: string;
  language: Language;
  speakerClusterId: string | null;
  origin: "asr" | "human_edit";
}

export interface Evidence {
  segmentId: string;
  transcriptRevision: number;
  quote: string;
  startMs: number;
  endMs: number;
}

export interface Action {
  id: string;
  meetingId: string;
  revision: number;
  text: string;
  ownerParticipantId: string | null;
  dueAt: string | null;
  originalDateExpression: string | null;
  status: ActionStatus;
  taskEvidence: Evidence[];
  ownerEvidence: Evidence[];
  dateEvidence: Evidence[];
  /** PROTOTYPE: the contract has no decision/action split. */
  kind: "decision" | "action";
  /** PROTOTYPE: a reviewer filled in owner or date by hand, so there is no transcript evidence for it. */
  resolvedByReviewer: boolean;
}

export interface Job {
  id: string;
  meetingId: string;
  state: JobState;
  stage: JobStage;
  profileId: string;
  errorCode: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface SourceMedia {
  kind: "upload" | "recording";
  label: string;
  sizeBytes: number | null;
  durationMs: number;
}

export interface Delivery {
  /** PROTOTYPE: nothing is actually sent from the prototype. */
  status: "sent_simulated";
  groupId: string;
  sentAt: string;
  snapshotRevision: number;
}

export interface Meeting {
  id: string;
  organizationId: string;
  title: string;
  recordedAt: string;
  timeZone: string;
  meetingType: MeetingType;
  outputLanguage: "ro" | "ru" | "en";
  patientLinkIds: string[];
  participantIds: string[];
  status: MeetingStatus;
  transcriptRevision: number;
  createdAt: string;
  updatedAt: string;
  // The fields below are embedded for the prototype; the real API returns
  // segments, actions, jobs and artifacts as separate records.
  /** PROTOTYPE: patient IDs directly, instead of patient-link records. */
  patientIds: string[];
  /** PROTOTYPE: speaker cluster to participant mapping (PBI-019/020 territory). */
  speakers: Record<string, string | null>;
  source: SourceMedia | null;
  job: Job;
  segments: Segment[];
  actions: Action[];
  summary: string;
  /** PROTOTYPE: minutes were generated from an older transcript revision. */
  minutesStale: boolean;
  delivery: Delivery | null;
}

export interface RecipientGroup {
  id: string;
  label: string;
  meetingType: MeetingType;
  to: { name: string; address: string }[];
  cc: { name: string; address: string }[];
}
