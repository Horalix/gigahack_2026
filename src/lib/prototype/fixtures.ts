// Fictional data for the clickable prototype. No real people, patients or
// recordings: names are generic combinations and the transcript is written for
// the demo. It deliberately exercises the hard cases from the challenge:
// sentence-level RO/RU/EN switching, medical vocabulary, an owner who is only
// named indirectly, a relative deadline, a missing owner, a proposal that was
// rejected, and a speaker who is not identified.

import type {
  Action,
  Evidence,
  Meeting,
  MeetingType,
  Participant,
  Patient,
  RecipientGroup,
  Segment,
} from "./types";

export const ORG = "org-demo";

// --- Patients ---------------------------------------------------------------

const FIRST = [
  "Ion", "Maria", "Andrei", "Elena", "Vasile", "Ana", "Mihai", "Natalia", "Ștefan", "Ioana",
  "Dumitru", "Tatiana", "Nicolae", "Svetlana", "Alexandru", "Irina", "Victor", "Ludmila",
  "Gheorghe", "Cristina",
];
const LAST = [
  "Rusu", "Ciobanu", "Popa", "Țurcanu", "Munteanu", "Lungu", "Cojocaru", "Moraru", "Ceban",
  "Bălan", "Rotaru", "Sîrbu", "Căpățînă", "Guțu", "Ursu",
];
const CYRILLIC = [
  "Иван Петров", "Ольга Смирнова", "Сергей Кузнецов", "Наталья Попова",
  "Алексей Морозов", "Елена Волкова", "Дмитрий Соколов", "Татьяна Лебедева",
];

function makePatients(): Patient[] {
  const names: string[] = [];
  for (let i = 0; i < 56; i++) names.push(`${FIRST[i % FIRST.length]} ${LAST[(i * 7) % LAST.length]}`);
  names.push(...CYRILLIC);
  names.push("Maria Rusu"); // a deliberate duplicate name; the reference tells them apart

  return names.map((displayName, i) => {
    const n = String(i + 1).padStart(4, "0");
    return {
      id: `pat-${n}`,
      organizationId: ORG,
      displayName,
      reference: i % 9 === 4 ? null : `MP-2026-${n}`,
      status: "active",
      createdAt: "2026-09-01T08:00:00+03:00",
      updatedAt: "2026-09-01T08:00:00+03:00",
    };
  });
}

export const patients: Patient[] = makePatients();

// --- People in the meetings ------------------------------------------------

export const participants: Participant[] = [
  { id: "p-rusu", displayName: "Dr. A. Rusu", role: "Chief Medical Officer" },
  { id: "p-ivanov", displayName: "Dr. M. Ivanov", role: "Head of Surgery" },
  { id: "p-ciobanu", displayName: "Dr. E. Ciobanu", role: "Head of Cardiology" },
  { id: "p-popa", displayName: "S. Popa", role: "IT & Clinical Systems" },
  { id: "p-lungu", displayName: "V. Lungu", role: "Administrative Director" },
];

// --- Where minutes go ------------------------------------------------------

export const recipientGroups: RecipientGroup[] = [
  {
    id: "med-board",
    label: "Medical Board",
    meetingType: "medical",
    to: [
      { name: "Dr. A. Rusu", address: "cmo@medpark.local" },
      { name: "Dr. M. Ivanov", address: "surgery.head@medpark.local" },
      { name: "Dr. E. Ciobanu", address: "cardiology.head@medpark.local" },
    ],
    cc: [{ name: "Medical Board Secretariat", address: "med.secretariat@medpark.local" }],
  },
  {
    id: "exec-board",
    label: "Executive Board",
    meetingType: "executive",
    to: [
      { name: "CEO Office", address: "ceo@medpark.local" },
      { name: "CFO Office", address: "cfo@medpark.local" },
      { name: "COO Office", address: "coo@medpark.local" },
    ],
    cc: [],
  },
  {
    id: "admin-ops",
    label: "Administrative & Operations",
    meetingType: "administrative",
    to: [
      { name: "V. Lungu", address: "admin.director@medpark.local" },
      { name: "Facilities", address: "facilities@medpark.local" },
      { name: "Procurement", address: "procurement@medpark.local" },
    ],
    cc: [{ name: "HR Department", address: "hr@medpark.local" }],
  },
];

export function groupFor(type: MeetingType): RecipientGroup {
  return recipientGroups.find((g) => g.meetingType === type)!;
}

// --- The sample meeting ----------------------------------------------------

type SegmentSeed = [startMs: number, endMs: number, lang: Segment["language"], speaker: string | null, text: string];

const SEGMENTS: SegmentSeed[] = [
  [0, 7400, "ro", "SPEAKER_01", "Bună ziua, colegi. Începem consiliul medical: pe agendă avem protocolul de CT cu contrast și lista de așteptare pentru RMN."],
  [7400, 15800, "mul", "SPEAKER_02", "Pentru protocolul de contrast propun screening de creatinină la toți pacienții peste 60 de ani — basically a mandatory eGFR check before the scan."],
  [15800, 22900, "ru", "SPEAKER_03", "Согласна, но нужно учитывать пациентов с сахарным диабетом: у них риск контраст-индуцированной нефропатии выше."],
  [22900, 30100, "mul", "SPEAKER_02", "Da, corect. Pentru pacienții diabetici — отдельный протокол гидратации до и после процедуры."],
  [30100, 38600, "ro", "SPEAKER_01", "Bine. Decizia: introducem screeningul obligatoriu de eGFR înainte de orice CT cu contrast, începând de luni."],
  [38600, 45200, "en", "SPEAKER_04", "I can update the order set in the hospital information system, but I need the final wording from cardiology first."],
  [45200, 52800, "ro", "SPEAKER_01", "Doamna doctor Ciobanu, puteți trimite formularea finală până vineri?"],
  [52800, 58100, "ru", "SPEAKER_03", "Да, до пятницы пришлю."],
  [58100, 66900, "ro", "SPEAKER_01", "Al doilea punct: lista de așteptare RMN. Avem 140 de pacienți, iar timpul mediu de așteptare este de 23 de zile."],
  [66900, 75400, "mul", "SPEAKER_02", "Propun să extindem programul RMN seara, până la ora 22 — but we need extra staffing for the evening shift."],
  [75400, 82000, "ru", "SPEAKER_05", "Это надо согласовать с администрацией и с бюджетом, не уверен, что это реально в этом месяце."],
  [82000, 90300, "ro", "SPEAKER_01", "Azi nu luăm decizia privind extinderea programului. Cineva trebuie să pregătească o estimare de cost până la sfârșitul lunii."],
  [90300, 97800, "en", "SPEAKER_04", "And the proposal to outsource MRI reads to an external clinic — I think we should drop it, patient data cannot leave the hospital."],
  [97800, 104000, "ro", "SPEAKER_01", "De acord, respingem externalizarea. Totul rămâne intern."],
  [104000, 110500, "mul", "SPEAKER_01", "Mulțumesc tuturor, ședința s-a încheiat. Спасибо."],
];

/** Speaker clusters from diarization, mapped to people where the system could tell. */
export const SAMPLE_SPEAKERS: Record<string, string | null> = {
  SPEAKER_01: "p-rusu",
  SPEAKER_02: "p-ivanov",
  SPEAKER_03: "p-ciobanu",
  SPEAKER_04: "p-popa",
  SPEAKER_05: null, // not identified
};

export const SAMPLE_DURATION_MS = 110500;

export const SAMPLE_SUMMARY =
  "The medical board adopted mandatory eGFR screening before every contrast-enhanced CT, starting Monday. " +
  "Cardiology will send the final protocol wording by Friday so IT can update the order set. " +
  "Extending MRI hours to 22:00 was discussed but not decided: a cost estimate is due by the end of the month and has no owner yet. " +
  "Outsourcing MRI reads to an external clinic was rejected because patient data must stay in the hospital.";

export function sampleSegments(meetingId: string): Segment[] {
  return SEGMENTS.map(([startMs, endMs, language, speakerClusterId, text], i) => ({
    id: `${meetingId}-s${String(i + 1).padStart(2, "0")}`,
    meetingId,
    transcriptRevision: 1,
    startMs,
    endMs,
    text,
    language,
    speakerClusterId,
    origin: "asr",
  }));
}

// Dates are resolved against the meeting's own local date, the way the real
// pipeline must resolve "vineri" or "до конца месяца".
// PROTOTYPE: due dates are date-only strings (YYYY-MM-DD).
function localDate(recordedAt: string): Date {
  const [y, m, d] = recordedAt.slice(0, 10).split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d));
}
function iso(date: Date): string {
  return date.toISOString().slice(0, 10);
}
function nextWeekday(recordedAt: string, weekday: number): string {
  const date = localDate(recordedAt);
  const diff = (weekday - date.getUTCDay() + 7) % 7 || 7;
  date.setUTCDate(date.getUTCDate() + diff);
  return iso(date);
}
function endOfMonth(recordedAt: string): string {
  const date = localDate(recordedAt);
  return iso(new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + 1, 0)));
}

export function sampleActions(meetingId: string, recordedAt: string, segments: Segment[]): Action[] {
  const seg = (n: number) => segments[n - 1];
  // Evidence quotes must be exact substrings of the cited segment.
  const ev = (n: number, quote?: string): Evidence => {
    const s = seg(n);
    const q = quote ?? s.text;
    if (!s.text.includes(q)) throw new Error(`Fixture quote not found in segment ${n}: ${q}`);
    return { segmentId: s.id, transcriptRevision: s.transcriptRevision, quote: q, startMs: s.startMs, endMs: s.endMs };
  };
  const base = { meetingId, revision: 1, resolvedByReviewer: false };

  return [
    {
      ...base,
      id: `${meetingId}-a1`,
      kind: "decision",
      text: "Introduce mandatory eGFR screening before every contrast-enhanced CT.",
      ownerParticipantId: null,
      dueAt: nextWeekday(recordedAt, 1),
      originalDateExpression: "începând de luni",
      status: "confirmed",
      taskEvidence: [ev(5)],
      ownerEvidence: [],
      dateEvidence: [ev(5, "începând de luni")],
    },
    {
      ...base,
      id: `${meetingId}-a2`,
      kind: "action",
      text: "Send the final wording of the contrast protocol to IT.",
      ownerParticipantId: "p-ciobanu",
      dueAt: nextWeekday(recordedAt, 5),
      originalDateExpression: "până vineri",
      status: "confirmed",
      taskEvidence: [ev(7)],
      ownerEvidence: [ev(7, "Doamna doctor Ciobanu"), ev(8)],
      dateEvidence: [ev(7, "până vineri"), ev(8, "до пятницы")],
    },
    {
      ...base,
      id: `${meetingId}-a3`,
      kind: "action",
      text: "Update the order set in the hospital information system with the new screening step.",
      ownerParticipantId: "p-popa",
      dueAt: null,
      originalDateExpression: null,
      status: "unresolved",
      taskEvidence: [ev(6)],
      ownerEvidence: [ev(6, "I can update the order set in the hospital information system")],
      dateEvidence: [],
    },
    {
      ...base,
      id: `${meetingId}-a4`,
      kind: "action",
      text: "Prepare a cost estimate for extending MRI hours to 22:00.",
      ownerParticipantId: null,
      dueAt: endOfMonth(recordedAt),
      originalDateExpression: "până la sfârșitul lunii",
      status: "unresolved",
      taskEvidence: [ev(12, "Cineva trebuie să pregătească o estimare de cost până la sfârșitul lunii.")],
      ownerEvidence: [],
      dateEvidence: [ev(12, "până la sfârșitul lunii")],
    },
    {
      ...base,
      id: `${meetingId}-a5`,
      kind: "action",
      text: "Separate hydration protocol for diabetic patients before and after the procedure.",
      ownerParticipantId: null,
      dueAt: null,
      originalDateExpression: null,
      status: "proposed",
      taskEvidence: [ev(4, "отдельный протокол гидратации до и после процедуры")],
      ownerEvidence: [],
      dateEvidence: [],
    },
    {
      ...base,
      id: `${meetingId}-a6`,
      kind: "action",
      text: "Outsource MRI reads to an external clinic.",
      ownerParticipantId: null,
      dueAt: null,
      originalDateExpression: null,
      status: "rejected",
      taskEvidence: [ev(13, "the proposal to outsource MRI reads to an external clinic"), ev(14, "respingem externalizarea")],
      ownerEvidence: [],
      dateEvidence: [],
    },
  ];
}

// --- Seed meetings shown on the dashboard ----------------------------------

function seedMeeting(input: {
  id: string;
  title: string;
  recordedAt: string;
  meetingType: MeetingType;
  status: Meeting["status"];
  patientIds?: string[];
  withContent?: boolean;
  delivered?: boolean;
  failedCode?: string;
}): Meeting {
  const segments = input.withContent === false ? [] : sampleSegments(input.id);
  const actions = input.withContent === false ? [] : sampleActions(input.id, input.recordedAt, segments);
  const failed = input.status === "failed";
  const done = input.status === "ready" || input.status === "needs_review";
  return {
    id: input.id,
    organizationId: ORG,
    title: input.title,
    recordedAt: input.recordedAt,
    timeZone: "Europe/Chisinau",
    meetingType: input.meetingType,
    outputLanguage: "en",
    patientLinkIds: [],
    participantIds: participants.map((p) => p.id),
    status: input.status,
    transcriptRevision: 1,
    createdAt: input.recordedAt,
    updatedAt: input.recordedAt,
    patientIds: input.patientIds ?? [],
    speakers: { ...SAMPLE_SPEAKERS },
    source: { kind: "upload", label: "meeting-recording.m4a", sizeBytes: 14_200_000, durationMs: SAMPLE_DURATION_MS },
    job: {
      id: `${input.id}-job`,
      meetingId: input.id,
      state: failed ? "failed" : input.status === "ready" ? "ready" : done ? "needs_review" : "queued",
      stage: failed ? "decode" : done ? "complete" : "decode",
      profileId: "laptop8",
      errorCode: input.failedCode ?? null,
      createdAt: input.recordedAt,
      updatedAt: input.recordedAt,
    },
    segments,
    actions,
    summary: input.withContent === false ? "" : SAMPLE_SUMMARY,
    minutesStale: false,
    delivery: input.delivered
      ? { status: "sent_simulated", groupId: groupFor(input.meetingType).id, sentAt: input.recordedAt, snapshotRevision: 1 }
      : null,
  };
}

export function seedMeetings(): Meeting[] {
  return [
    seedMeeting({
      id: "mtg-demo-1",
      title: "Consiliul medical: protocol CT cu contrast",
      recordedAt: "2026-09-25T10:00:00+03:00",
      meetingType: "medical",
      status: "needs_review",
    }),
    seedMeeting({
      id: "mtg-demo-2",
      title: "Consult multidisciplinar: follow-up",
      recordedAt: "2026-09-23T14:30:00+03:00",
      meetingType: "medical",
      status: "ready",
      patientIds: ["pat-0001", "pat-0012"],
      delivered: true,
    }),
    seedMeeting({
      id: "mtg-demo-3",
      title: "Ședința executivă: buget echipamente Q4",
      recordedAt: "2026-09-22T09:00:00+03:00",
      meetingType: "executive",
      status: "ready",
      delivered: true,
    }),
    seedMeeting({
      id: "mtg-demo-4",
      title: "Program gărzi octombrie",
      recordedAt: "2026-09-21T16:00:00+03:00",
      meetingType: "administrative",
      status: "failed",
      withContent: false,
      failedCode: "AUDIO_TRACK_MISSING",
    }),
  ];
}
