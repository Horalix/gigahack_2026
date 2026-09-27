// In-browser stand-in for the Notavra REST API (/api/v1/*), so the ported UI
// runs with no service behind it. It answers the same paths with the same
// shapes and the same error codes, so errors.ts produces the real messages.
//
// State lives in sessionStorage for the tab; audio lives in memory only, so a
// reload keeps meetings but drops uploaded/recorded sound. Replacing this
// module with fetch() is all that is needed to use a real backend.

import { pcm16ToWav, placeholderWav, probeDuration, sha256Hex } from "./audio";
import { ALLOWED_DOMAINS, ALTERNATIVES, BOUNDARY_REVIEW, CANDIDATES, GLOSSARY, GROUPS, PEOPLE, RATE, SCRIPT, SCRIPT_SECONDS, TEMPLATES } from "./fixtures";
import { renderMinutes } from "./render";

export class MockError extends Error {
  constructor(public code: string, public status = 400) {
    super(code);
  }
}

type Obj = Record<string, any>;

interface DB {
  accounts: Obj[];
  session: string | null;
  meetings: Obj[];
  assets: Obj[];
  recordings: Obj[];
  jobs: Obj[];
  segments: Obj[];
  segmentHistory: Obj[];
  candidates: Obj[];
  snapshots: Obj[];
  deliveries: Obj[];
  checks: Record<string, Obj>;
  groups: Obj[];
  templates: Obj[];
  glossary: { version: number; terms: string[] };
}

const STORE_KEY = "notavra-demo-db-v2";
const ASSET_SECONDS = 114; // the demo asset runs past the transcript, so one gap is flagged
const now = () => Date.now() / 1000;
const uid = (prefix: string) => `${prefix}-${Math.random().toString(36).slice(2, 10)}`;
const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value));

// Kept in memory only: object URLs and raw PCM do not survive a reload.
const audioUrls = new Map<string, string>();
const pcm = new Map<string, ArrayBuffer[]>();
const exportUrls = new Map<string, string>();
const placeholders = new Set<string>(); // assets playing the stand-in tone

// --- Seed ---------------------------------------------------------------

function buildSegments(meetingId: string, assetId: string, seconds: number, speakers: boolean): Obj[] {
  const scale = seconds / ASSET_SECONDS;
  return SCRIPT.map(([start, end, speaker, text], i) => ({
    id: uid("seg"),
    meeting_id: meetingId,
    asset_id: assetId,
    start: Math.round(start * scale * RATE),
    end: Math.round(end * scale * RATE),
    text,
    speaker: speakers ? speaker : null,
    revision: 1,
    raw: JSON.stringify(BOUNDARY_REVIEW.has(i) ? { boundary_review: true } : {}),
    alternatives: JSON.stringify(ALTERNATIVES[i] ?? []),
  }));
}

function buildCandidates(meetingId: string, segments: Obj[]): Obj[] {
  return CANDIDATES.map((seed) => {
    const body = {
      subject: seed.subject,
      category: seed.category,
      kind: seed.kind,
      text: seed.text,
      owner: seed.owner,
      due: seed.due,
      condition: seed.condition,
      value: seed.value,
      uncertainties: seed.uncertainties,
    };
    const evidence = seed.refs
      .filter(([index]) => segments[index])
      .map(([index, field, quote]) => ({
        id: uid("ev"),
        field,
        quote: quote ?? segments[index].text,
        revision: segments[index].revision,
        segment_id: segments[index].id,
      }));
    return {
      id: uid("itm"),
      meeting_id: meetingId,
      review: seed.review,
      body,
      evidence,
      history: [{ id: uid("hist"), review: seed.review, body: JSON.stringify(body) }],
    };
  });
}

function buildChecks(assetId: string, seconds: number): Obj {
  const s = (x: number) => Math.round((x * seconds) / ASSET_SECONDS * RATE);
  return {
    asset_id: assetId,
    items: [
      {
        kind: "speech_without_transcript",
        start: s(110.6),
        end: s(113.4),
        inserted_segment_id: null,
        hypotheses: [
          { text: "Mulțumesc tuturor, ședința s-a încheiat. Спасибо. Vă rog să trimiteți procesul-verbal până mâine.", attempt: "initial", source_start: s(104), source_end: s(114) },
          { text: "…trimiteți procesul-verbal până mâine.", attempt: "short_retry", source_start: s(110.4), source_end: s(113.6) },
        ],
      },
      { kind: "empty_second_recognizer", start: s(75.4), end: s(82) },
    ],
  };
}

function seed(): DB {
  const t0 = now() - 20 * 3600;
  const meetingId = "mtg-demo-board";
  const assetId = "ast-demo-board";
  const jobId = "job-demo-board";
  const segments = buildSegments(meetingId, assetId, ASSET_SECONDS, true);
  return {
    accounts: [],
    session: null,
    meetings: [
      {
        id: meetingId, title: "Consiliul medical: protocol CT cu contrast", date: "2026-09-25", timezone: "Europe/Chisinau",
        language: "ro", classification: "Medical", revision: 3, status: "awaiting_review", created: t0,
        time: "14:00", notes: "Agenda: eGFR screening before contrast CT, contrast protocol wording, MRI evening hours.\nDraft order set to be circulated before the meeting.",
        participants: [...PEOPLE], transcript_pending_assets: [],
      },
      {
        id: "mtg-demo-exec", title: "Ședința executivă: buget echipamente Q4", date: "2026-09-29", timezone: "Europe/Chisinau",
        language: "en", classification: "Executive", revision: 1, status: "draft", created: t0 + 900,
        time: "09:30", notes: "",
        participants: ["CEO Office", "CFO Office", "COO Office"], transcript_pending_assets: [],
      },
    ],
    assets: [
      { id: assetId, meeting_id: meetingId, hash: "demo-placeholder", sample_rate: RATE, samples: ASSET_SECONDS * RATE, channels: 1, original: "consiliu-medical.m4a" },
    ],
    recordings: [],
    jobs: [
      {
        id: jobId, meeting_id: meetingId, asset_id: assetId, state: "complete", stage: "extract", error: null, attempt: 1, cancel: 0,
        created: t0 + 60, transcript_only: false, sim: null,
        progress: { stage: "extract", phase: "stage_complete", completed: CANDIDATES.length, total: CANDIDATES.length, unit: "items", elapsed_seconds: 412, eta_seconds: null, eta_scope: "stage", updated_at: t0 + 480 },
      },
    ],
    segments,
    segmentHistory: [],
    candidates: buildCandidates(meetingId, segments),
    snapshots: [],
    deliveries: [],
    checks: { [jobId]: buildChecks(assetId, ASSET_SECONDS) },
    groups: clone(GROUPS),
    templates: clone(TEMPLATES),
    glossary: { version: 1, terms: [...GLOSSARY] },
  };
}

function load(): DB {
  try {
    const raw = sessionStorage.getItem(STORE_KEY);
    if (raw) return JSON.parse(raw);
  } catch {
    /* storage unavailable: start fresh */
  }
  return seed();
}

let db: DB = load();

function save(): void {
  try {
    sessionStorage.setItem(STORE_KEY, JSON.stringify(db));
  } catch {
    /* storage unavailable: state lasts until reload */
  }
}

/** Discard all demo data and start over (keeps nothing, including the account). */
export function resetDemo(): void {
  db = seed();
  save();
  audioUrls.clear();
  placeholders.clear();
  pcm.clear();
  exportUrls.clear();
}

// --- Audio and export URLs used directly by <audio>/<a> -----------------

export function assetAudioUrl(assetId: string): string | undefined {
  const asset = db.assets.find((a) => a.id === assetId);
  if (!asset) return undefined;
  let url = audioUrls.get(assetId);
  if (!url) {
    url = URL.createObjectURL(placeholderWav(asset.samples / asset.sample_rate));
    audioUrls.set(assetId, url);
    placeholders.add(assetId);
  }
  return url;
}

export function assetHasRealAudio(assetId: string): boolean {
  return audioUrls.has(assetId) && !placeholders.has(assetId);
}

export function snapshotExportUrl(snapshotId: string, format: string): string {
  const key = `${snapshotId}:${format}`;
  const cached = exportUrls.get(key);
  if (cached) return cached;
  const snap = db.snapshots.find((s) => s.id === snapshotId);
  if (!snap) return "#";
  let blob: Blob;
  if (format === "json") {
    blob = new Blob([JSON.stringify(snap.content, null, 2)], { type: "application/json" });
  } else {
    // "PDF" opens the print dialog on the same document; the browser saves it as PDF.
    const html = format === "pdf" ? snap.html.replace("</body>", "<script>addEventListener('load',()=>print())</script></body>") : snap.html;
    blob = new Blob([html], { type: "text/html;charset=utf-8" });
  }
  const url = URL.createObjectURL(blob);
  exportUrls.set(key, url);
  return url;
}

// --- Helpers --------------------------------------------------------------

function me(): Obj {
  const account = db.accounts.find((a) => a.id === db.session);
  if (!account) throw new MockError("authentication_required", 401);
  return account;
}

function writer(): Obj {
  const account = me();
  if (account.role === "viewer") throw new MockError("read_only", 403);
  return account;
}

function admin(): Obj {
  const account = me();
  if (account.role !== "admin") throw new MockError("admin_required", 403);
  return account;
}

function meeting(id: string): Obj {
  const m = db.meetings.find((x) => x.id === id);
  if (!m) throw new MockError("meeting_not_found", 404);
  return m;
}

const activeJobs = (meetingId: string) => db.jobs.filter((j) => j.meeting_id === meetingId && ["queued", "running"].includes(j.state));

const TIME = /^(?:[01][0-9]|2[0-3]):[0-5][0-9]$|^$/;

function checkTimeAndNotes(time: unknown, notes: unknown): void {
  if (time !== undefined && !TIME.test(String(time))) throw new MockError("validation_failed", 422);
  if (notes !== undefined && String(notes).length > 20000) throw new MockError("validation_failed", 422);
}

function checkTimezone(tz: string): void {
  if (!tz) return;
  try {
    new Intl.DateTimeFormat("en", { timeZone: tz });
  } catch {
    throw new MockError("invalid_timezone");
  }
}

const meetingView = (m: Obj) => ({
  id: m.id, title: m.title, date: m.date, timezone: m.timezone, language: m.language,
  classification: m.classification, revision: m.revision, status: m.status, created: m.created,
  time: m.time ?? "", notes: m.notes ?? "",
});

function meetingDetail(m: Obj): Obj {
  return {
    ...meetingView(m),
    participants: m.participants.map((name: string, i: number) => ({ id: `${m.id}-p${i}`, meeting_id: m.id, name })),
    assets: db.assets.filter((a) => a.meeting_id === m.id),
    jobs: db.jobs.filter((j) => j.meeting_id === m.id).sort((a, b) => b.created - a.created).map(({ sim: _s, ...j }) => j),
    recordings: db.recordings.filter((r) => r.meeting_id === m.id),
    transcript_pending_assets: m.transcript_pending_assets,
  };
}

/** A transcript change invalidates interpretation (services/api/transcript_state.py). */
function transcriptChanged(m: Obj, assetId: string): void {
  if (!m.transcript_pending_assets.includes(assetId)) m.transcript_pending_assets.push(assetId);
  // New speech can change the meaning of existing statements on the same recording.
  const onAsset = new Set(db.segments.filter((s) => s.asset_id === assetId).map((s) => s.id));
  for (const c of db.candidates) {
    if (c.meeting_id === m.id && c.review !== "excluded" && c.evidence.some((e: Obj) => onAsset.has(e.segment_id))) c.review = "needs_review";
  }
  m.revision += 1;
  m.status = "awaiting_review";
}

const searchKey = (s: string) => s.normalize("NFD").replace(/\p{M}/gu, "").toLocaleLowerCase();

// --- Simulated processing -------------------------------------------------

function progress(stage: string, phase: string, completed: number, total: number | null, unit: string, elapsed: number, eta: number | null) {
  return { stage, phase, completed, total, unit, elapsed_seconds: elapsed, eta_seconds: eta, eta_scope: "stage", updated_at: now() };
}

function advance(job: Obj): void {
  if (!job.sim || !["queued", "running"].includes(job.state)) return;
  const t = (Date.now() - job.sim.started) / 1000;
  if (t < 1.2) return;
  const m = db.meetings.find((x) => x.id === job.meeting_id);
  job.state = "running";
  if (m) m.status = "processing";
  const audio = job.sim.audioSeconds;
  const items = CANDIDATES.length;
  let x = t - 1.2;
  if (!job.transcript_only) {
    if (x < 2) return void Object.assign(job, { stage: "whisper", progress: progress("whisper", "loading_model", 0, null, "seconds", x, null) });
    x -= 2;
    if (x < 7) return void Object.assign(job, { stage: "whisper", progress: progress("whisper", "transcribing", (audio * x) / 7, audio, "seconds", x, 7 - x) });
    x -= 7;
  }
  if (x < 4) return void Object.assign(job, { stage: "extract", progress: progress("extract", "extracting", Math.floor((items * x) / 4), items, "items", x, 4 - x) });
  x -= 4;
  if (x < 2) return void Object.assign(job, { stage: "extract", progress: progress("extract", "checking", Math.floor((items * x) / 2), items, "items", x, 2 - x) });
  finish(job);
}

function finish(job: Obj): void {
  const m = meeting(job.meeting_id);
  const asset = db.assets.find((a) => a.id === job.asset_id)!;
  const seconds = asset.samples / asset.sample_rate;
  job.state = "complete";
  job.progress = progress("extract", "stage_complete", CANDIDATES.length, CANDIDATES.length, "items", 6, null);
  job.sim = null;
  if (!job.transcript_only) {
    db.segments = db.segments.filter((s) => s.asset_id !== asset.id);
    // No speaker model is prepared in this demo, so speakers stay unlabeled
    // for new analyses, exactly as the real service reports them.
    db.segments.push(...buildSegments(m.id, asset.id, seconds, false));
    db.checks[job.id] = buildChecks(asset.id, seconds);
  }
  const source = db.segments
    .filter((s) => s.asset_id === asset.id && !JSON.parse(s.raw || "{}").reviewed_addition)
    .sort((a, b) => a.start - b.start);
  db.candidates = db.candidates.filter((c) => c.meeting_id !== m.id);
  db.candidates.push(...buildCandidates(m.id, source));
  m.transcript_pending_assets = m.transcript_pending_assets.filter((a: string) => a !== asset.id);
  m.revision += 1;
  m.status = "awaiting_review";
}

function tick(): void {
  for (const job of db.jobs) advance(job);
  for (const d of db.deliveries) {
    if (d.state === "queued" && Date.now() / 1000 - d.created > 1.5) d.state = "sent";
  }
}

// --- Router ---------------------------------------------------------------

type Handler = (params: string[], body: any, query: URLSearchParams) => unknown | Promise<unknown>;
const routes: [string, RegExp, Handler][] = [];
const route = (method: string, pattern: string, handler: Handler) =>
  routes.push([method, new RegExp("^" + pattern.replace(/\{\w+\}/g, "([^/]+)") + "$"), handler]);

// Accounts and sessions
route("GET", "/setup", () => ({ required: db.accounts.length === 0 }));
route("POST", "/setup", (_, b) => {
  if (db.accounts.length) throw new MockError("setup_already_complete", 409);
  const account = { id: uid("usr"), name: String(b.name), password: String(b.password), role: "admin", language: "en" };
  db.accounts.push(account);
  db.session = account.id;
  return { ...account, password: undefined, csrf: uid("csrf") };
});
route("POST", "/sessions", (_, b) => {
  const account = db.accounts.find((a) => a.name === b.name && a.password === b.password);
  if (!account) throw new MockError("invalid_credentials", 401);
  db.session = account.id;
  return { ...account, password: undefined, csrf: uid("csrf") };
});
route("DELETE", "/sessions/current", () => {
  db.session = null;
  return {};
});
route("GET", "/me", () => ({ ...me(), password: undefined, csrf: uid("csrf") }));
route("PATCH", "/me", (_, b) => {
  const account = me();
  account.language = b.language;
  return { ...account, password: undefined };
});
route("GET", "/accounts", () => {
  admin();
  return db.accounts.map(({ password: _p, ...a }) => a);
});
route("POST", "/accounts", (_, b) => {
  admin();
  if (db.accounts.some((a) => a.name === b.name)) throw new MockError("data_conflict", 409);
  const account = { id: uid("usr"), name: String(b.name), password: String(b.password), role: b.role, language: "en" };
  db.accounts.push(account);
  return { ...account, password: undefined };
});

// Meetings
route("GET", "/meetings", () => {
  me();
  return [...db.meetings].sort((a, b) => (b.date || "").localeCompare(a.date || "") || b.created - a.created).map(meetingView);
});
route("POST", "/meetings", (_, b) => {
  writer();
  if (!String(b.title || "").trim()) throw new MockError("validation_failed", 422);
  checkTimezone(b.timezone);
  checkTimeAndNotes(b.time, b.notes);
  const m = {
    id: uid("mtg"), title: String(b.title).trim(), date: b.date || "", timezone: b.timezone || "", language: b.language,
    classification: b.classification, revision: 1, status: "draft", created: now(), time: b.time || "", notes: b.notes || "",
    participants: (b.participants || []).map((p: string) => p.trim()).filter(Boolean), transcript_pending_assets: [],
  };
  db.meetings.push(m);
  return meetingView(m);
});
route("GET", "/meetings/{id}", ([id]) => meetingDetail(meeting(id)));
route("PATCH", "/meetings/{id}", ([id], b) => {
  writer();
  const m = meeting(id);
  if (b.revision !== m.revision) throw new MockError("revision_conflict", 409);
  if (activeJobs(id).length) throw new MockError("cancel_processing_before_metadata_edit", 409);
  checkTimezone(b.timezone);
  checkTimeAndNotes(b.time, b.notes);
  Object.assign(m, {
    title: String(b.title).trim(), date: b.date || "", timezone: b.timezone || "", language: b.language,
    classification: b.classification, participants: b.participants, revision: m.revision + 1,
    // Fields left out of the request keep their saved values.
    time: b.time !== undefined ? b.time : m.time ?? "", notes: b.notes !== undefined ? b.notes : m.notes ?? "",
  });
  return meetingView(m);
});
route("DELETE", "/meetings/{id}", ([id], b) => {
  admin();
  const m = meeting(id);
  if (activeJobs(id).length) throw new MockError("cancel_processing_before_deletion", 409);
  if (b.revision !== m.revision || b.confirm_title !== m.title) throw new MockError("deletion_confirmation_conflict", 409);
  const drop = (list: Obj[]) => list.filter((x) => x.meeting_id !== id);
  const gone = new Set(db.segments.filter((s) => s.meeting_id === id).map((s) => s.id));
  db.segmentHistory = db.segmentHistory.filter((h) => !gone.has(h.segment_id));
  db.meetings = db.meetings.filter((x) => x.id !== id);
  db.assets = drop(db.assets);
  db.recordings = drop(db.recordings);
  db.jobs = drop(db.jobs);
  db.segments = drop(db.segments);
  db.candidates = drop(db.candidates);
  db.snapshots = drop(db.snapshots);
  return {};
});
route("POST", "/meetings/{id}/members", ([id]) => {
  admin();
  meeting(id);
  return {};
});

// Audio in
route("POST", "/meetings/{id}/uploads", async ([id], form: FormData) => {
  writer();
  const m = meeting(id);
  const file = form.get("file") as File | null;
  if (!file || !/\.(wav|mp3|m4a|ogg|flac|webm)$/i.test(file.name)) throw new MockError("unsupported_audio_type", 415);
  if (file.size > 2 * 1024 ** 3) throw new MockError("upload_too_large", 413);
  let seconds: number;
  try {
    seconds = await probeDuration(file);
  } catch {
    throw new MockError("audio_decode_failed", 422);
  }
  const asset = {
    id: uid("ast"), meeting_id: m.id, hash: await sha256Hex(await file.arrayBuffer()), sample_rate: RATE,
    samples: Math.round(seconds * RATE), channels: 1, original: file.name,
  };
  db.assets.push(asset);
  audioUrls.set(asset.id, URL.createObjectURL(file));
  return asset;
});
route("POST", "/meetings/{id}/recordings", ([id], b) => {
  writer();
  meeting(id);
  const rec = { id: uid("rec"), meeting_id: id, rate: b.sample_rate, state: "recording", gaps: "[]", acknowledged_chunks: 0, acknowledged_samples: 0, last_sequence: null };
  db.recordings.push(rec);
  pcm.set(rec.id, []);
  return rec;
});
route("PUT", "/recordings/{id}/chunks/{seq}", ([id, seq], data: ArrayBuffer) => {
  writer();
  const rec = db.recordings.find((r) => r.id === id);
  if (!rec) throw new MockError("recording_not_found", 404);
  if (rec.state !== "recording") throw new MockError("recording_sealed", 409);
  const list = pcm.get(id) ?? [];
  const sequence = Number(seq);
  if (list[sequence]) throw new MockError("chunk_content_conflict", 409);
  list[sequence] = data.slice(0);
  pcm.set(id, list);
  rec.acknowledged_chunks += 1;
  rec.acknowledged_samples += data.byteLength / 2;
  rec.last_sequence = sequence;
  return { acknowledged_samples: rec.acknowledged_samples, sample_rate: rec.rate };
});
route("POST", "/recordings/{id}/finish", ([id], b) => {
  writer();
  const rec = db.recordings.find((r) => r.id === id);
  if (!rec) throw new MockError("recording_not_found", 404);
  if (rec.state !== "recording") throw new MockError("recording_sealed", 409);
  const list = (pcm.get(id) ?? []).filter(Boolean);
  if (b.count > rec.acknowledged_chunks) throw new MockError("missing_chunks", 409);
  rec.state = "sealed";
  rec.gaps = JSON.stringify(b.gaps ?? []);
  const seconds = rec.acknowledged_samples / rec.rate;
  const asset = {
    id: uid("ast"), meeting_id: rec.meeting_id, hash: "recorded", sample_rate: RATE,
    samples: Math.round(seconds * RATE), channels: 1, original: "microphone.wav",
  };
  db.assets.push(asset);
  // Chunks lost to a reload leave an asset with no sound; playback falls back to the placeholder.
  if (list.length) audioUrls.set(asset.id, URL.createObjectURL(pcm16ToWav(list, rec.rate)));
  pcm.delete(id);
  return asset;
});

// Processing
route("POST", "/meetings/{id}/jobs", ([id], b) => {
  writer();
  const m = meeting(id);
  if (activeJobs(id).length) throw new MockError("processing_incomplete", 409);
  const asset = db.assets.find((a) => a.id === b.asset_id && a.meeting_id === id);
  if (!asset) throw new MockError("asset_not_found", 404);
  if (b.transcript_only && !db.segments.some((s) => s.asset_id === asset.id)) throw new MockError("transcript_required", 409);
  if (!b.transcript_only && (b.parakeet || b.diarization)) throw new MockError(b.parakeet ? "parakeet_not_prepared" : "diarization_not_prepared", 409);
  const job = {
    id: uid("job"), meeting_id: id, asset_id: asset.id, state: "queued", stage: b.transcript_only ? "extract" : "whisper",
    error: null, attempt: 1, cancel: 0, created: now(), progress: null, transcript_only: !!b.transcript_only,
    sim: { started: Date.now(), audioSeconds: asset.samples / asset.sample_rate },
  };
  db.jobs.push(job);
  m.status = "queued";
  return job;
});
route("POST", "/jobs/{id}/cancel", ([id]) => {
  writer();
  const job = db.jobs.find((j) => j.id === id);
  if (!job || !["queued", "running"].includes(job.state)) throw new MockError("job_not_retryable", 409);
  job.state = "cancelled";
  job.sim = null;
  const m = meeting(job.meeting_id);
  m.status = db.candidates.some((c) => c.meeting_id === m.id) ? "awaiting_review" : "draft";
  return {};
});
route("POST", "/jobs/{id}/retry", ([id]) => {
  writer();
  const job = db.jobs.find((j) => j.id === id);
  if (!job || !["failed", "cancelled"].includes(job.state)) throw new MockError("job_not_retryable", 409);
  const asset = db.assets.find((a) => a.id === job.asset_id)!;
  Object.assign(job, { state: "queued", error: null, progress: null, attempt: job.attempt + 1, sim: { started: Date.now(), audioSeconds: asset.samples / asset.sample_rate } });
  meeting(job.meeting_id).status = "queued";
  return {};
});
route("GET", "/jobs/{id}/audio-checks", ([id], _, q) => {
  me();
  const page = db.checks[id];
  if (!page) return { asset_id: "", total: 0, items: [] };
  const offset = Number(q.get("offset") || 0);
  const limit = Number(q.get("limit") || 20);
  return { asset_id: page.asset_id, total: page.items.length, items: page.items.slice(offset, offset + limit) };
});
route("POST", "/jobs/{id}/transcript-additions", ([id], b) => {
  writer();
  const job = db.jobs.find((j) => j.id === id);
  const page = db.checks[id];
  if (!job || !page) throw new MockError("audio_observation_not_found", 404);
  const m = meeting(job.meeting_id);
  if (b.revision !== m.revision) throw new MockError("revision_conflict", 409);
  const item = page.items.find((i: Obj) => i.start === b.start && i.end === b.end);
  if (!item) throw new MockError("audio_observation_not_found", 404);
  if (item.inserted_segment_id) throw new MockError("gap_already_corrected", 409);
  if (!String(b.text || "").trim() || String(b.reason || "").trim().length < 3) throw new MockError("correction_text_required", 422);
  const segment = {
    id: uid("seg"), meeting_id: m.id, asset_id: page.asset_id, start: b.start, end: b.end, text: String(b.text).trim(),
    speaker: b.speaker || null, revision: 1, raw: JSON.stringify({ reviewed_addition: true, reason: b.reason }), alternatives: "[]",
  };
  db.segments.push(segment);
  item.inserted_segment_id = segment.id;
  transcriptChanged(m, page.asset_id);
  return segment;
});

// Transcript
route("GET", "/meetings/{id}/transcript", ([id], _, q) => {
  meeting(id);
  const needle = searchKey(q.get("q") || "");
  const offset = Number(q.get("offset") || 0);
  const limit = Number(q.get("limit") || 200);
  return db.segments
    .filter((s) => s.meeting_id === id && (!needle || searchKey(s.text).includes(needle) || searchKey(s.speaker || "").includes(needle)))
    .sort((a, b) => a.start - b.start)
    .slice(offset, offset + limit);
});
route("GET", "/segments/{id}", ([id]) => {
  const s = db.segments.find((x) => x.id === id);
  if (!s) throw new MockError("segment_not_found", 404);
  return s;
});
route("GET", "/segments/{id}/history", ([id]) => {
  me();
  if (!db.segments.some((x) => x.id === id)) throw new MockError("segment_not_found", 404);
  return db.segmentHistory
    .filter((h) => h.segment_id === id)
    .sort((a, b) => a.revision - b.revision)
    .map(({ revision, text, actor, created }) => ({ revision, text, actor, created }));
});
route("POST", "/segments/{id}/revisions", ([id], b) => {
  const account = writer();
  const s = db.segments.find((x) => x.id === id);
  if (!s) throw new MockError("segment_not_found", 404);
  if (b.revision !== s.revision) throw new MockError("revision_conflict", 409);
  const text = String(b.text ?? "");
  if (!text || text.length > 10000 || String(b.speaker ?? "").length > 200) throw new MockError("validation_failed", 422);
  // The replaced wording is kept, as the service's segment_history table does.
  db.segmentHistory.push({ segment_id: s.id, revision: s.revision, text: s.text, actor: account.id, created: now() });
  s.text = text;
  s.speaker = b.speaker || null;
  s.revision += 1;
  transcriptChanged(meeting(s.meeting_id), s.asset_id);
  return { revision: s.revision };
});

// Supplied transcripts (services/api/transcript_import.py): "Speaker N" and
// "m:ss" header lines, an optional language line, then the text. Imported text
// is labelled as not verified against the audio.
const HEADER = /^Speaker ([1-9][0-9]*)\s*\r?\n(\d{1,3}):([0-5][0-9])\s*\r?\n/gm;
const LABELS = new Set(["Italian", "Macedonian", "Serbian", "Japanese", "Romanian", "Russian", "English"]);

function parseTranscript(source: string, samples: number, rate: number): Obj[] {
  const matches = [...source.matchAll(HEADER)];
  if (!matches.length || source.slice(0, matches[0].index).replace(/[﻿ \r\n\t]/g, "")) {
    throw new MockError("expected_speaker_timestamp_transcript", 422);
  }
  const rows = matches.map((match, index) => {
    const start = (Number(match[2]) * 60 + Number(match[3])) * rate;
    const next = index + 1 < matches.length ? matches[index + 1].index : source.length;
    const raw = source.slice(match.index! + match[0].length, next).trim();
    let text = raw,
      labels: string[] = [];
    const cut = raw.indexOf("\n");
    if (cut >= 0 && LABELS.has(raw.slice(0, cut).trim())) {
      labels = [raw.slice(0, cut).trim()];
      text = raw.slice(cut + 1).trim();
    }
    if (!text || text.length > 10000 || !(start >= 0 && start < samples)) throw new MockError("invalid_transcript_text_or_timestamp", 422);
    return { start, end: 0, speaker: "Speaker " + match[1], text, source_index: index, source_text: raw, supplied_language_labels: labels };
  });
  // Each passage ends at the next distinct anchor; equal anchors stay overlapping.
  const starts = [...new Set([...rows.map((r) => r.start), samples])].sort((a, b) => a - b);
  for (const row of rows) row.end = starts[starts.indexOf(row.start) + 1];
  return rows.sort((a, b) => a.start - b.start || a.source_index - b.source_index);
}

route("POST", "/meetings/{id}/transcript-imports", async ([id], b) => {
  const account = writer();
  const m = meeting(id);
  const source = String(b.source ?? "");
  if (!source || source.length > 2_000_000 || !String(b.filename ?? "") || !(b.revision >= 1)) throw new MockError("validation_failed", 422);
  const digest = await sha256Hex(source);
  const asset = db.assets.find((a) => a.id === b.asset_id && a.meeting_id === id);
  if (!asset) throw new MockError("asset_not_found", 404);
  const existing = db.segments.filter((s) => s.asset_id === asset.id);
  if (existing.length) {
    if (existing.every((s) => JSON.parse(s.raw || "{}").source_sha256 === digest)) return { segments: existing.length, sha256: digest, already_imported: true };
    throw new MockError("transcript_already_exists", 409);
  }
  if (m.revision !== b.revision) throw new MockError("revision_conflict", 409);
  if (activeJobs(id).length) throw new MockError("processing_incomplete", 409);
  const rows = parseTranscript(source, asset.samples, asset.sample_rate);
  for (const row of rows) {
    const raw = {
      origin: "user_supplied_transcript", verified_against_audio: false, source_sha256: digest, filename: b.filename, actor: account.id,
      imported_at: now(), timing: "supplied coarse anchors; end inferred from next distinct anchor",
      source_index: row.source_index, source_text: row.source_text, supplied_language_labels: row.supplied_language_labels,
    };
    db.segments.push({
      id: uid("seg"), meeting_id: id, asset_id: asset.id, start: row.start, end: row.end, text: row.text, speaker: row.speaker,
      revision: 1, raw: JSON.stringify(raw), alternatives: "[]", words: "[]",
    });
  }
  transcriptChanged(m, asset.id);
  return { segments: rows.length, sha256: digest, already_imported: false };
});

// Review
route("GET", "/meetings/{id}/items", ([id]) => {
  const m = meeting(id);
  return {
    revision: m.revision,
    candidates: db.candidates.filter((c) => c.meeting_id === id).map(({ history: _h, ...c }) => c),
  };
});
route("POST", "/review-issues/{id}/resolve", ([id], b) => {
  writer();
  const c = db.candidates.find((x) => x.id === id);
  if (!c) throw new MockError("item_not_found", 404);
  const m = meeting(c.meeting_id);
  if (b.revision !== m.revision) throw new MockError("revision_conflict", 409);
  if (b.action === "accepted" && m.transcript_pending_assets.length) throw new MockError("transcript_reanalysis_required", 409);
  c.review = b.action;
  c.history.push({ id: uid("hist"), review: b.action, body: JSON.stringify(c.body) });
  return {};
});
route("POST", "/items/{id}/corrections", ([id], b) => {
  writer();
  const c = db.candidates.find((x) => x.id === id);
  if (!c) throw new MockError("item_not_found", 404);
  const m = meeting(c.meeting_id);
  if (b.revision !== m.revision) throw new MockError("revision_conflict", 409);
  const fields = ["subject", "text", "owner", "due", "condition", "value", "category", "kind"] as const;
  const changed = fields.filter((f) => (b[f] ?? null) !== (c.body[f] ?? null));
  if (!changed.length && !(b.resolved_issues || []).length) throw new MockError("no_changes", 409);
  const account = me();
  const body = {
    ...c.body,
    ...Object.fromEntries(fields.map((f) => [f, b[f] ?? null])),
    uncertainties: c.body.uncertainties.filter((u: string) => !(b.resolved_issues || []).includes(u)),
    human_amendment: { reason: b.reason, fields: changed, actor: account.name, created: now(), resolved_issues: b.resolved_issues || [] },
  };
  // No audio evidence is invented for fields a reviewer changed.
  const evidence = c.evidence.filter((e: Obj) => !changed.includes(e.field));
  const amended = { id: uid("itm"), meeting_id: c.meeting_id, review: "unreviewed", body, evidence, history: [...c.history, { id: uid("hist"), review: "unreviewed", body: JSON.stringify(body) }] };
  db.candidates.splice(db.candidates.indexOf(c), 1, amended);
  return { id: amended.id };
});
route("GET", "/items/{id}/history", ([id]) => {
  const c = db.candidates.find((x) => x.id === id);
  if (!c) throw new MockError("item_not_found", 404);
  return [...c.history].reverse();
});
route("GET", "/actions", () => {
  me();
  return db.candidates
    .filter((c) => c.review === "accepted" && c.body.category === "action")
    .map((c) => ({ meeting_id: c.meeting_id, subject: c.body.subject, text: c.body.text, owner: c.body.owner, due: c.body.due, status: c.review, condition: c.body.condition }));
});

// Minutes, approval and delivery
route("GET", "/meetings/{id}/snapshots", ([id]) => {
  meeting(id);
  return db.snapshots.filter((s) => s.meeting_id === id).sort((a, b) => b.created - a.created).map(({ html: _h, content: _c, ...s }) => s);
});
route("POST", "/meetings/{id}/snapshots", async ([id], b) => {
  writer();
  const m = meeting(id);
  if (b.revision !== m.revision) throw new MockError("revision_conflict", 409);
  if (activeJobs(id).length) throw new MockError("processing_incomplete", 409);
  if (m.transcript_pending_assets.length) throw new MockError("transcript_reanalysis_required", 409);
  const items = db.candidates.filter((c) => c.meeting_id === id);
  if (!items.length || items.some((c) => !["accepted", "excluded"].includes(c.review))) throw new MockError("review_incomplete", 409);
  const template = db.templates.find((t) => t.classification === m.classification);
  const html = renderMinutes(m, m.participants, items, template, m.revision);
  const snap = {
    id: uid("snp"), meeting_id: id, revision: m.revision, approved: false, hash: await sha256Hex(html),
    template_revision: template?.version ?? 0, suggested_group_id: template?.recipient_group_id ?? null, created: now(),
    html, content: { meeting: meetingView(m), items: items.filter((c) => c.review === "accepted").map((c) => c.body) },
  };
  db.snapshots.push(snap);
  return { id: snap.id };
});
route("POST", "/snapshots/{id}/approve", ([id], b) => {
  writer();
  const s = db.snapshots.find((x) => x.id === id);
  if (!s) throw new MockError("snapshot_not_found", 404);
  if (s.revision !== meeting(s.meeting_id).revision || b.revision !== s.revision) throw new MockError("stale_snapshot", 409);
  s.approved = true;
  return {};
});
route("GET", "/recipient-groups", () => {
  me();
  return db.groups;
});
route("POST", "/recipient-groups", (_, b) => {
  admin();
  const addresses: string[] = (b.addresses || []).map((a: string) => a.trim()).filter(Boolean);
  if (addresses.some((a) => !ALLOWED_DOMAINS.includes(a.split("@")[1] || ""))) throw new MockError("recipient_outside_allowed_domains", 422);
  if (b.id) {
    const g = db.groups.find((x) => x.id === b.id);
    if (!g) throw new MockError("group_not_found", 404);
    if (b.version !== g.version) throw new MockError("revision_conflict", 409);
    Object.assign(g, { name: b.name, addresses, version: g.version + 1 });
    return g;
  }
  const g = { id: uid("grp"), name: b.name, addresses, version: 1 };
  db.groups.push(g);
  return g;
});
route("GET", "/snapshots/{id}/deliveries", ([id]) =>
  db.deliveries.filter((d) => d.snapshot_id === id).sort((a, b) => b.created - a.created),
);
route("POST", "/snapshots/{id}/deliveries", ([id], b) => {
  writer();
  const s = db.snapshots.find((x) => x.id === id);
  if (!s) throw new MockError("snapshot_not_found", 404);
  if (!s.approved) throw new MockError("approval_required", 409);
  if (s.revision !== meeting(s.meeting_id).revision && !b.explicitly_send_older) throw new MockError("older_version_requires_explicit_choice", 409);
  const g = db.groups.find((x) => x.id === b.group_id);
  if (!g || g.version !== b.group_version) throw new MockError("recipient_group_changed", 409);
  const d = { id: uid("dlv"), snapshot_id: id, state: "queued", error: null, addresses: JSON.stringify(g.addresses), created: now() };
  db.deliveries.push(d);
  return d;
});
route("POST", "/deliveries/{id}/retry", ([id]) => {
  writer();
  const d = db.deliveries.find((x) => x.id === id);
  if (!d || d.state !== "failed") throw new MockError("delivery_not_safe_to_retry", 409);
  Object.assign(d, { state: "queued", error: null, created: now() });
  return {};
});

// System and settings
route("GET", "/system/proof", () => {
  me();
  return {
    runtime: "Demo backend in this browser — no local service connected",
    network_observation: "Not measured",
    models: { whisper: "demo", llm: "demo" },
    capabilities: {
      parakeet: { available: false, qualification: "Not qualified", prerequisite: "Prepare the optional recognizer with the offline kit." },
      diarization: { available: false, qualification: "Not qualified", prerequisite: "Prepare speaker-labeling assets with the offline kit." },
    },
  };
});
route("GET", "/settings/templates", () => {
  me();
  return db.templates;
});
route("PUT", "/settings/templates/{classification}", ([classification], b) => {
  admin();
  const t = db.templates.find((x) => x.classification === decodeURIComponent(classification));
  if (!t) throw new MockError("template_not_found", 404);
  if (b.version !== t.version) throw new MockError("revision_conflict", 409);
  Object.assign(t, { titles: b.titles, introduction: b.introduction, recipient_group_id: b.recipient_group_id, version: t.version + 1 });
  return t;
});
route("GET", "/settings/glossary", () => {
  admin();
  return db.glossary;
});
route("PUT", "/settings/glossary", (_, b) => {
  admin();
  if (b.version !== db.glossary.version) throw new MockError("revision_conflict", 409);
  const terms: string[] = (b.terms || []).map((t: string) => t.trim()).filter(Boolean);
  if (terms.some((t) => t.length > 100)) throw new MockError("invalid_glossary_term", 422);
  db.glossary = { version: db.glossary.version + 1, terms };
  return db.glossary;
});

// --- Entry point ----------------------------------------------------------

export async function handle(path: string, method: string, body: unknown): Promise<unknown> {
  tick();
  const [pathname, search = ""] = path.split("?");
  for (const [m, pattern, handler] of routes) {
    if (m !== method) continue;
    const match = pattern.exec(pathname);
    if (!match) continue;
    const result = await handler(match.slice(1).map(decodeURIComponent), body, new URLSearchParams(search));
    save();
    return clone(result ?? {});
  }
  throw new MockError("not_found", 404);
}
