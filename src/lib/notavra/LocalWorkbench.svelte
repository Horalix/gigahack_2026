<script lang="ts">
  import { onDestroy, onMount } from "svelte";

  type User = { id: string; username: string; role: string };
  type Meeting = { id: string; title: string; recordedAt: string; status: string; outputLanguage: string; transcriptRevision: number };
  type Segment = { id: string; startMs: number; endMs: number; text: string; language: string };
  type Patient = { id: string; displayName: string; hospitalReference: string | null; status: string; meetings?: { id: string; title: string; recordedAt: string; status: string }[] };
  type Capture = { id: string; state: string; next_sequence: number; received_bytes: number; error_code?: string | null };
  type Profile = { id: string; hardware: { gpu: string; vram_gb: number }; asrFilesPresent: boolean; llmFilePresent: boolean; compatible: boolean };
  type Detail = { meeting: Meeting; permission: string; asset: { durationMs: number; decodeWarning?: string } | null; latestJob?: { id: string; state: string; stage: string; errorCode?: string | null } | null; segments: Segment[]; decisions: any; canUndoCorrection: boolean; captures: Capture[]; artifact: { id: string; sha256: string; approvedAt: string; storageKey: string } | null };

  let user = $state<User | null>(null);
  let setupRequired = $state(false);
  let username = $state("");
  let password = $state("");
  let error = $state("");
  let meetings = $state<Meeting[]>([]);
  let total = $state(0);
  let query = $state("");
  let offset = $state(0);
  let detail = $state<Detail | null>(null);
  let directoryView = $state(false);
  let patients = $state<Patient[]>([]);
  let patientTotal = $state(0);
  let patientCursor = $state<string | null>(null);
  let patientHasMore = $state(false);
  let patientQuery = $state("");
  let selectedPatient = $state<Patient | null>(null);
  let patientSearchTimer: ReturnType<typeof setTimeout> | undefined;
  let profiles = $state<Profile[]>([]);
  let profileId = $state("laptop8");
  let language = $state("ro");
  let busy = $state(false);
  let status = $state("");
  let recording = $state(false);
  let recordingSeconds = $state(0);
  let microphoneLevel = $state(0);
  let liveSegments = $state<Segment[]>([]);
  let livePreviewStatus = $state("");
  let acknowledgedCaptureChunks = $state(0);
  let captureId: string | undefined;
  let nextCaptureSequence = 0;
  let chunkUpload: Promise<void> = Promise.resolve();
  let pendingChunkUploads = $state(0);
  let captureFailure = "";
  let captureWarning = "";
  let recorder: MediaRecorder | undefined;
  let mediaStream: MediaStream | undefined;
  let audioContext: AudioContext | undefined;
  let audioAnalyser: AnalyserNode | undefined;
  let previewProcessor: ScriptProcessorNode | undefined;
  let previewSamples: number[] = [];
  let previewStartSample = 0;
  let previewWindowIndex = 0;
  let previewInFlight = false;
  let previewSkipped = false;
  let previewTask: Promise<void> = Promise.resolve();
  let audioMeterTimer: ReturnType<typeof setInterval> | undefined;
  let recordingTimer: ReturnType<typeof setInterval> | undefined;
  let editingSegment = $state<string | null>(null);
  let editText = $state("");
  let findQuery = $state("");
  let activeFindIndex = $state(0);
  let selectedCorrectionSegments = $state<string[]>([]);
  let replacementText = $state("");
  let reviewConfirmed = $state(false);
  let progressTimer: ReturnType<typeof setInterval> | undefined;
  let searchTimer: ReturnType<typeof setTimeout> | undefined;
  let searchMatches = $derived.by(() => {
    const needle = findQuery.trim().toLocaleLowerCase();
    if (!needle || !detail) return [] as { segmentId: string; start: number }[];
    return detail.segments.flatMap((segment) => {
      const source = segment.text.toLocaleLowerCase();
      const matches: { segmentId: string; start: number }[] = [];
      let at = source.indexOf(needle);
      while (at >= 0) { matches.push({ segmentId: segment.id, start: at }); at = source.indexOf(needle, at + Math.max(needle.length, 1)); }
      return matches;
    });
  });

  async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const response = await fetch(`/api${path}`, {
      credentials: "same-origin",
      ...options,
      headers: { ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }), ...options.headers },
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.message || body.code || `Request failed (${response.status})`);
    return body as T;
  }

  async function initialize() {
    try {
      const health = await request<{ setupRequired: boolean }>("/health");
      setupRequired = health.setupRequired;
      if (!setupRequired) {
        const me = await request<{ user: User }>("/auth/me");
        user = me.user;
        await Promise.all([loadMeetings(), loadProfiles()]);
      }
    } catch (e) {
      error = e instanceof Error ? e.message : "Local service is unavailable";
    }
  }

  async function authenticate(event: SubmitEvent) {
    event.preventDefault();
    error = "";
    try {
      const path = setupRequired ? "/auth/setup" : "/auth/login";
      const result = await request<{ user: User }>(path, { method: "POST", body: JSON.stringify({ username, password }) });
      user = result.user;
      setupRequired = false;
      password = "";
      await Promise.all([loadMeetings(), loadProfiles()]);
    } catch (e) {
      if (setupRequired) {
        try {
          const health = await request<{ setupRequired: boolean }>("/health");
          if (!health.setupRequired) {
            setupRequired = false;
            password = "";
            error = "An administrator already exists. Sign in with the existing account.";
            return;
          }
        } catch {
          // Keep the original setup error if the service cannot confirm its state.
        }
      }
      error = e instanceof Error ? e.message : "Sign in failed";
    }
  }

  async function loadMeetings() {
    const result = await request<{ meetings: Meeting[]; total: number }>(`/meetings?q=${encodeURIComponent(query)}&limit=10&offset=${offset}`);
    meetings = result.meetings;
    total = result.total;
  }

  async function loadPatients(cursor?: string, append = false) {
    const params = new URLSearchParams({ limit: "25", q: patientQuery });
    if (cursor) params.set("cursor", cursor);
    const result = await request<{ patients: Patient[]; total: number; nextCursor: string | null; hasMore: boolean }>(`/patients?${params}`);
    patients = append ? [...patients, ...result.patients] : result.patients;
    patientTotal = result.total; patientCursor = result.nextCursor; patientHasMore = result.hasMore;
  }

  async function openPatient(patientId: string) {
    const result = await request<{ patient: Patient }>(`/patients/${patientId}`);
    selectedPatient = result.patient;
  }

  async function createPatient(event: SubmitEvent) {
    event.preventDefault();
    const form = new FormData(event.currentTarget as HTMLFormElement);
    try {
      const result = await request<{ patient: Patient }>("/patients", { method: "POST", body: JSON.stringify({
        displayName: String(form.get("displayName")), hospitalReference: String(form.get("hospitalReference") || "") || null,
      }) });
      selectedPatient = result.patient; await loadPatients();
      (event.currentTarget as HTMLFormElement).reset();
    } catch (e) { showError(e); }
  }

  async function loadProfiles() {
    const result = await request<{ profiles: Profile[]; defaultProfileId?: string }>("/profiles");
    profiles = result.profiles;
    if (result.defaultProfileId && result.profiles.some((profile) => profile.id === result.defaultProfileId && profile.compatible)) {
      profileId = result.defaultProfileId;
    }
  }

  async function openMeeting(id: string) {
    stopPolling();
    reviewConfirmed = false;
    selectedCorrectionSegments = [];
    findQuery = "";
    activeFindIndex = 0;
    detail = await request<Detail>(`/meetings/${id}`);
    editingSegment = null;
    error = "";
  }

  async function deleteMeeting() {
    if (!detail || !window.confirm("Permanently remove this meeting, its local audio, transcript, actions, approved files, and patient links? Previously downloaded copies are outside this app.")) return;
    const id = detail.meeting.id;
    try {
      const result = await request<{ pendingFileCleanup: number }>(`/meetings/${id}`, { method: "DELETE" });
      detail = null; status = result.pendingFileCleanup ? "Meeting removed. Some files are locked and will be retried by the local worker." : "Meeting and app-managed files removed.";
      await loadMeetings();
    } catch (e) { showError(e); }
  }

  async function saveSegment(segment: Segment) {
    if (!detail) return;
    try {
      await request(`/meetings/${detail.meeting.id}/segments/${segment.id}`, {
        method: "PUT", body: JSON.stringify({ transcriptRevision: detail.meeting.transcriptRevision, text: editText }),
      });
      await openMeeting(detail.meeting.id);
      status = "Transcript correction saved. Recheck extracted actions before approval.";
    } catch (e) { showError(e); }
  }

  function moveFindMatch(direction: number) {
    if (!searchMatches.length) return;
    activeFindIndex = (activeFindIndex + direction + searchMatches.length) % searchMatches.length;
    const target = searchMatches[activeFindIndex];
    document.getElementById(`segment-${target.segmentId}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function playPassage(startMs: number) {
    const player = document.querySelector<HTMLAudioElement>(".audio-review");
    if (!player) return;
    player.currentTime = startMs / 1000;
    void player.play().catch(() => showError("Audio playback could not start. Use the player controls to retry."));
  }

  function findKeydown(event: KeyboardEvent) {
    if (event.key === "ArrowDown") { event.preventDefault(); moveFindMatch(1); }
    else if (event.key === "ArrowUp") { event.preventDefault(); moveFindMatch(-1); }
    else if (event.key === "Enter") { event.preventDefault(); moveFindMatch(event.shiftKey ? -1 : 1); }
  }

  function highlightParts(text: string, segmentId: string) {
    const needle = findQuery.trim().toLocaleLowerCase();
    if (!needle) return [{ text, match: false, current: false }];
    const source = text.toLocaleLowerCase();
    const parts: { text: string; match: boolean; current: boolean }[] = [];
    let cursor = 0;
    let at = source.indexOf(needle);
    while (at >= 0) {
      if (at > cursor) parts.push({ text: text.slice(cursor, at), match: false, current: false });
      const current = searchMatches[activeFindIndex]?.segmentId === segmentId && searchMatches[activeFindIndex]?.start === at;
      parts.push({ text: text.slice(at, at + needle.length), match: true, current });
      cursor = at + needle.length;
      at = source.indexOf(needle, cursor);
    }
    if (cursor < text.length) parts.push({ text: text.slice(cursor), match: false, current: false });
    return parts.length ? parts : [{ text, match: false, current: false }];
  }

  function buildSelectedCorrections() {
    if (!detail || !findQuery.trim() || !selectedCorrectionSegments.length) return { corrections: [] as { segmentId: string; text: string; oldText: string }[], count: 0 };
    const needle = findQuery.trim().toLocaleLowerCase();
    const escaped = findQuery.trim().replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const expression = new RegExp(escaped, "giu");
    let count = 0;
    const corrections = detail.segments.filter((segment) => selectedCorrectionSegments.includes(segment.id))
      .filter((segment) => segment.text.toLocaleLowerCase().includes(needle))
      .map((segment) => {
        count += [...segment.text.matchAll(expression)].length;
        expression.lastIndex = 0;
        return { segmentId: segment.id, oldText: segment.text, text: segment.text.replace(expression, () => replacementText) };
      });
    return { corrections, count };
  }

  async function replaceInSelectedPassages() {
    if (!detail || !findQuery.trim() || !selectedCorrectionSegments.length) return;
    const { corrections } = buildSelectedCorrections();
    if (!corrections.length) return;
    try {
      await request(`/meetings/${detail.meeting.id}/segments`, { method: "PUT", body: JSON.stringify({
        transcriptRevision: detail.meeting.transcriptRevision,
        corrections: corrections.map(({ segmentId, text }) => ({ segmentId, text })),
      }) });
      selectedCorrectionSegments = [];
      await openMeeting(detail.meeting.id);
      status = `Updated ${corrections.length} passages. Reprocess saved audio to refresh extracted actions.`;
    } catch (e) { showError(e); }
  }

  async function undoLastCorrection() {
    if (!detail) return;
    try {
      await request(`/meetings/${detail.meeting.id}/transcript/undo`, {
        method: "POST", body: JSON.stringify({ transcriptRevision: detail.meeting.transcriptRevision }),
      });
      await openMeeting(detail.meeting.id);
      status = "Last correction batch undone. Reprocess saved audio to refresh actions.";
    } catch (e) { showError(e); }
  }

  function downloadTranscript(format: "txt" | "json") {
    if (!detail) return;
    const body = format === "txt"
      ? detail.segments.map((segment) => `[${formatTime(segment.startMs)}] ${segment.text}`).join("\n")
      : JSON.stringify({ meeting: detail.meeting, transcript: detail.segments, decisions: detail.decisions }, null, 2);
    const blob = new Blob([body], { type: format === "txt" ? "text/plain;charset=utf-8" : "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url; link.download = `${detail.meeting.title.replace(/[^\p{L}\p{N}-]+/gu, "-")}.${format}`;
    link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  async function approveAndDownload() {
    if (!detail || !reviewConfirmed) return;
    try {
      const result = await request<{ artifact: { id: string } }>(`/meetings/${detail.meeting.id}/artifacts`, {
        method: "POST", body: JSON.stringify({ transcriptRevision: detail.meeting.transcriptRevision, confirmHumanReview: true }),
      });
      const response = await fetch(`/api/artifacts/${result.artifact.id}/content`, { credentials: "same-origin" });
      if (!response.ok) throw new Error("Approved minutes could not be downloaded");
      const blob = await response.blob(); const url = URL.createObjectURL(blob);
      const link = document.createElement("a"); link.href = url; link.download = `notavra-minutes-${result.artifact.id}.html`; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      reviewConfirmed = false; status = "Reviewed HTML minutes generated and downloaded.";
      await openMeeting(detail.meeting.id);
    } catch (e) { showError(e); }
  }

  async function reviewDecision(decisionId: string, reviewStatus: "accepted" | "excluded") {
    if (!detail) return;
    const meetingId = detail.meeting.id;
    try {
      await request(`/meetings/${meetingId}/decisions/${decisionId}`, {
        method: "PUT", body: JSON.stringify({ transcriptRevision: detail.meeting.transcriptRevision, reviewStatus }),
      });
      await openMeeting(meetingId);
      status = reviewStatus === "accepted" ? "Action included in the approved minutes." : "Action excluded from the approved minutes.";
    } catch (e) { showError(e); }
  }

  function allDecisionsReviewed() {
    return detail?.decisions?.items?.every((item: any) => ["accepted", "excluded"].includes(item.reviewStatus)) ?? true;
  }

  async function createMeeting(event: SubmitEvent) {
    event.preventDefault();
    const form = new FormData(event.currentTarget as HTMLFormElement);
    busy = true; error = "";
    try {
      const meeting = await request<Meeting>("/meetings", { method: "POST", body: JSON.stringify({
        contractVersion: "1.0", title: String(form.get("title")),
        recordedAt: new Date().toISOString(), timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        outputLanguage: language === "auto" ? "ro" : language, patientLinkIds: selectedPatient ? [selectedPatient.id] : [], meetingType: "Clinical consultation",
      }) });
      await loadMeetings(); await openMeeting(meeting.id);
    } catch (e) { error = e instanceof Error ? e.message : "Could not create meeting"; }
    finally { busy = false; }
  }

  async function upload(event: SubmitEvent) {
    event.preventDefault();
    if (!detail) return;
    const form = new FormData(event.currentTarget as HTMLFormElement);
    const file = form.get("audio");
    if (!(file instanceof File) || !file.size) { error = "Choose an audio or video file first."; return; }
    busy = true; error = ""; status = "Uploading and preparing audio…";
    try {
      const payload = new FormData(); payload.set("file", file);
      const asset = await request<{ id: string }>(`/meetings/${detail.meeting.id}/audio`, { method: "POST", body: payload });
      status = "Starting local transcription and decision extraction…";
      const job = await request<{ id: string }>(`/meetings/${detail.meeting.id}/jobs`, {
        method: "POST", body: JSON.stringify({ profileId, language }),
      });
      void asset;
      watchJob(job.id);
    } catch (e) { error = e instanceof Error ? e.message : "Processing could not start"; status = ""; busy = false; }
  }

  async function reprocessSavedAudio() {
    if (!detail) return;
    busy = true; error = ""; status = "Re-running local transcription and decision extraction…";
    try {
      const job = await request<{ id: string }>(`/meetings/${detail.meeting.id}/jobs`, {
        method: "POST", body: JSON.stringify({ profileId, language }),
      });
      watchJob(job.id);
    } catch (e) { error = e instanceof Error ? e.message : "Processing could not start"; status = ""; busy = false; }
  }

  async function retryFailedJob() {
    if (!detail?.latestJob || detail.latestJob.state !== "failed") return;
    busy = true; error = ""; status = "Retrying the failed local processing step…";
    try {
      const job = await request<{ id: string }>(`/jobs/${detail.latestJob.id}/retry`, { method: "POST" });
      watchJob(job.id);
    } catch (e) { error = e instanceof Error ? e.message : "The failed step could not be retried"; status = ""; busy = false; }
  }

  function startMicrophoneMeter(stream: MediaStream) {
    try {
      audioContext = new AudioContext();
      audioAnalyser = audioContext.createAnalyser();
      audioAnalyser.fftSize = 256;
      const source = audioContext.createMediaStreamSource(stream);
      const silentOutput = audioContext.createGain();
      silentOutput.gain.value = 0;
      source.connect(audioAnalyser);
      audioAnalyser.connect(silentOutput);
      silentOutput.connect(audioContext.destination);
      void audioContext.resume().catch(() => stopMicrophoneMeter());
      const samples = new Uint8Array(audioAnalyser.fftSize);
      audioMeterTimer = setInterval(() => {
        if (!audioAnalyser) return;
        audioAnalyser.getByteTimeDomainData(samples);
        let energy = 0;
        for (const sample of samples) energy += ((sample - 128) / 128) ** 2;
        microphoneLevel = Math.min(1, Math.sqrt(energy / samples.length) * 4);
      }, 100);
    } catch {
      stopMicrophoneMeter();
    }
  }

  function stopMicrophoneMeter() {
    if (audioMeterTimer) clearInterval(audioMeterTimer);
    audioMeterTimer = undefined;
    audioAnalyser?.disconnect();
    audioAnalyser = undefined;
    previewProcessor?.disconnect();
    previewProcessor = undefined;
    const context = audioContext;
    audioContext = undefined;
    if (context && context.state !== "closed") void context.close().catch(() => undefined);
    microphoneLevel = 0;
  }

  function pcmWindowWav(samples: number[]) {
    const buffer = new ArrayBuffer(44 + samples.length * 2);
    const view = new DataView(buffer);
    const write = (offset: number, value: string) => { for (let index = 0; index < value.length; index += 1) view.setUint8(offset + index, value.charCodeAt(index)); };
    write(0, "RIFF"); view.setUint32(4, 36 + samples.length * 2, true); write(8, "WAVE");
    write(12, "fmt "); view.setUint32(16, 16, true); view.setUint16(20, 1, true);
    view.setUint16(22, 1, true); view.setUint32(24, 16000, true); view.setUint32(28, 32000, true);
    view.setUint16(32, 2, true); view.setUint16(34, 16, true); write(36, "data"); view.setUint32(40, samples.length * 2, true);
    for (let index = 0; index < samples.length; index += 1) view.setInt16(44 + index * 2, samples[index], true);
    return new Blob([buffer], { type: "audio/wav" });
  }

  async function sendPreviewWindow(samples: number[], startSample: number, ownedEndMs: number) {
    const sessionId = captureId;
    if (!sessionId || samples.length < 16000) return;
    const startMs = Math.round(startSample * 1000 / 16000);
    const durationMs = Math.round(samples.length * 1000 / 16000);
    const endMs = startMs + durationMs;
    const params = new URLSearchParams({ profileId, language, start_ms: String(startMs),
      ownershipStartMs: String(startMs), ownershipEndMs: String(Math.min(ownedEndMs, endMs)) });
    try {
      const result = await request<{ segments: Segment[]; wallSeconds: number }>(`/captures/${sessionId}/preview?${params}`, {
        method: "POST", body: pcmWindowWav(samples), headers: { "Content-Type": "audio/wav" },
      });
      const windowIndex = previewWindowIndex++;
      liveSegments = [...liveSegments, ...result.segments.map((segment) => ({
        ...segment, id: `${sessionId}-preview-${windowIndex}-${segment.id}`,
      }))];
      livePreviewStatus = previewSkipped ? "Live preview resumed after a delay; skipped audio remains in the saved recording." : "Local preview · provisional";
    } catch (e) {
      const message = e instanceof Error ? e.message : "Live preview unavailable";
      livePreviewStatus = message.includes("busy") ? "Live preview paused while the local model is busy; full audio is still being saved." : `Live preview paused: ${message}`;
    }
  }

  function startLivePreview(stream: MediaStream) {
    if (!audioContext) return;
    try {
      const source = audioContext.createMediaStreamSource(stream);
      const processor = audioContext.createScriptProcessor(4096, 1, 1);
      const silentOutput = audioContext.createGain();
      silentOutput.gain.value = 0;
      source.connect(processor);
      processor.connect(silentOutput);
      silentOutput.connect(audioContext.destination);
      previewProcessor = processor;
      previewSamples = []; previewStartSample = 0; previewWindowIndex = 0; previewInFlight = false; previewSkipped = false;
      liveSegments = []; livePreviewStatus = "Waiting for the first 18 seconds of speech…";
      processor.onaudioprocess = (event) => {
        const input = event.inputBuffer.getChannelData(0);
        const ratio = audioContext!.sampleRate / 16000;
        for (let at = 0; at < input.length; at += ratio) {
          const sample = Math.max(-1, Math.min(1, input[Math.floor(at)]));
          previewSamples.push(sample < 0 ? Math.round(sample * 32768) : Math.round(sample * 32767));
        }
        while (previewSamples.length >= 20 * 16000) {
          const window = previewSamples.slice(0, 20 * 16000);
          const start = previewStartSample;
          previewSamples.splice(0, 18 * 16000);
          previewStartSample += 18 * 16000;
          if (previewInFlight) { previewSkipped = true; continue; }
          previewInFlight = true;
          livePreviewStatus = "Recognizing a complete local audio window…";
          previewTask = sendPreviewWindow(window, start, start + 18 * 1000)
            .finally(() => { previewInFlight = false; });
        }
      };
    } catch {
      livePreviewStatus = "Live preview is unavailable; the full recording is still being saved.";
    }
  }

  async function finishLivePreview() {
    previewProcessor?.disconnect();
    previewProcessor = undefined;
    await previewTask;
    if (previewSamples.length >= 16000 && !previewInFlight) {
      const tail = previewSamples;
      previewSamples = [];
      await sendPreviewWindow(tail, previewStartSample, previewStartSample * 1000 / 16000 + tail.length * 1000 / 16000);
    }
  }

  async function startRecording() {
    if (!detail) return;
    error = ""; captureFailure = ""; captureWarning = ""; nextCaptureSequence = 0; pendingChunkUploads = 0; acknowledgedCaptureChunks = 0; chunkUpload = Promise.resolve(); recordingSeconds = 0;
    try {
      mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      startMicrophoneMeter(mediaStream);
      const requestedMime = ["audio/webm;codecs=opus", "audio/mp4"].find((type) => MediaRecorder.isTypeSupported(type));
      recorder = requestedMime ? new MediaRecorder(mediaStream, { mimeType: requestedMime }) : new MediaRecorder(mediaStream);
      const mimeType = recorder.mimeType || requestedMime || "audio/webm";
      const session = await request<{ id: string }>(`/meetings/${detail.meeting.id}/captures`, {
        method: "POST", body: JSON.stringify({ contentType: mimeType }),
      });
      captureId = session.id;
      startLivePreview(mediaStream);
      recorder.ondataavailable = (event) => {
        if (!event.data.size) return;
        const sequence = nextCaptureSequence++;
        const sessionId = captureId;
        pendingChunkUploads += 1;
        if (pendingChunkUploads >= 4 && recording) {
          captureWarning = "Recording stopped because local storage could not keep pace; the captured portion is being saved.";
          stopRecording();
        }
        chunkUpload = chunkUpload.then(async () => {
          if (captureFailure || !sessionId) return;
          const response = await fetch(`/api/captures/${sessionId}/chunks/${sequence}`, {
            method: "PUT", body: event.data, credentials: "same-origin", headers: { "Content-Type": mimeType },
          });
          const body = await response.json().catch(() => ({}));
          if (!response.ok) throw new Error(body.message || "A recording chunk could not be saved");
          acknowledgedCaptureChunks += 1;
        }).catch((e) => { captureFailure = e instanceof Error ? e.message : "Chunk upload failed"; error = captureFailure; })
          .finally(() => pendingChunkUploads = Math.max(0, pendingChunkUploads - 1));
      };
      recorder.onstop = () => {
        mediaStream?.getTracks().forEach((track) => track.stop());
        mediaStream = undefined;
        void finishRecording();
      };
      recorder.start(10_000);
      recording = true;
      recordingTimer = setInterval(() => recordingSeconds += 1, 1000);
    } catch (e) { stopMicrophoneMeter(); error = e instanceof Error ? e.message : "Microphone access failed"; mediaStream?.getTracks().forEach((track) => track.stop()); mediaStream = undefined; }
  }

  async function finishRecording() {
    const sessionId = captureId;
    if (!sessionId) return;
    await finishLivePreview();
    stopMicrophoneMeter();
    await chunkUpload;
    if (!nextCaptureSequence) {
      await request(`/captures/${sessionId}`, { method: "DELETE" }).catch(() => undefined);
      captureId = undefined; error = "The microphone recording was empty.";
      return;
    }
    if (captureFailure) {
      const meetingId = detail?.meeting.id;
      captureId = undefined;
      if (meetingId) await openMeeting(meetingId).catch(showError);
      error = captureFailure;
      status = "Saved chunks are available to process or discard below.";
      return;
    }
    busy = true; status = `${captureWarning ? `${captureWarning} ` : ""}Sealing saved audio and starting local processing…`;
    try {
      await request(`/captures/${sessionId}/seal`, { method: "POST", body: JSON.stringify({ expectedSequenceCount: nextCaptureSequence }) });
      const job = await request<{ id: string }>(`/meetings/${detail?.meeting.id}/jobs`, {
        method: "POST", body: JSON.stringify({ profileId, language }),
      });
      captureId = undefined; watchJob(job.id);
    } catch (e) { error = e instanceof Error ? e.message : "Recording could not be sealed"; status = ""; busy = false; }
  }

  async function processSavedCapture(capture: Capture) {
    if (!detail) return;
    busy = true; error = ""; status = "Sealing the locally saved portion of the recording…";
    try {
      await request(`/captures/${capture.id}/seal`, { method: "POST", body: JSON.stringify({ expectedSequenceCount: capture.next_sequence }) });
      const job = await request<{ id: string }>(`/meetings/${detail.meeting.id}/jobs`, {
        method: "POST", body: JSON.stringify({ profileId, language }),
      });
      watchJob(job.id);
    } catch (e) { error = e instanceof Error ? e.message : "Saved audio could not be processed"; status = ""; busy = false; }
  }

  async function discardSavedCapture(capture: Capture) {
    try { await request(`/captures/${capture.id}`, { method: "DELETE" }); if (detail) await openMeeting(detail.meeting.id); }
    catch (e) { showError(e); }
  }

  function stopRecording() {
    if (recordingTimer) clearInterval(recordingTimer);
    recordingTimer = undefined;
    recording = false;
    if (recorder?.state === "recording") recorder.stop();
    else stopMicrophoneMeter();
  }

  function watchJob(jobId: string) {
    stopPolling();
    progressTimer = setInterval(async () => {
      try {
        const job = await request<{ state: string; stage: string; errorCode?: string; progressMs?: number }>(`/jobs/${jobId}`);
        status = job.state === "ready" ? "Transcript and decisions are ready for review." : job.state === "failed" ? `Processing failed: ${job.errorCode || "unknown error"}` : `${job.stage}: ${job.state}…`;
        if (job.state === "ready" || job.state === "failed") {
          stopPolling(); busy = false;
          liveSegments = []; livePreviewStatus = "";
          if (detail) await openMeeting(detail.meeting.id);
          await loadMeetings();
        }
      } catch (e) { status = e instanceof Error ? e.message : "Lost connection to the local service"; stopPolling(); busy = false; }
    }, 1800);
  }

  function stopPolling() { if (progressTimer) clearInterval(progressTimer); progressTimer = undefined; }
  function searchChanged() { offset = 0; if (searchTimer) clearTimeout(searchTimer); searchTimer = setTimeout(() => void loadMeetings().catch(showError), 250); }
  function patientSearchChanged() { if (patientSearchTimer) clearTimeout(patientSearchTimer); patientSearchTimer = setTimeout(() => { selectedPatient = null; void loadPatients().catch(showError); }, 250); }
  function showError(e: unknown) { error = e instanceof Error ? e.message : "Request failed"; }
  function formatTime(ms: number) { return new Date(ms).toISOString().slice(11, 19); }
  function formatElapsed(seconds: number) { return `${String(Math.floor(seconds / 3600)).padStart(2,"0")}:${String(Math.floor(seconds / 60) % 60).padStart(2,"0")}:${String(seconds % 60).padStart(2,"0")}`; }
  async function logout() { await request("/auth/logout", { method: "POST" }); user = null; detail = null; selectedPatient = null; patients = []; await initialize(); }

  onMount(() => { void initialize(); });
  onDestroy(() => { stopPolling(); stopRecording(); mediaStream?.getTracks().forEach((track) => track.stop()); if (searchTimer) clearTimeout(searchTimer); if (patientSearchTimer) clearTimeout(patientSearchTimer); });
</script>

<svelte:head><title>Notavra · Clinical workspace</title></svelte:head>

{#if !user}
  <main class="auth-shell">
    <form class="auth-card" onsubmit={authenticate}>
      <img src="/brand/lockup.png" alt="Notavra" />
      <h1>{setupRequired ? "Set up your local workspace" : "Sign in to Notavra"}</h1>
      <p>Audio and transcripts stay on this computer.</p>
      <label>Username<input bind:value={username} required minlength="3" autocomplete="username" /></label>
      <label>Password<input bind:value={password} type="password" required minlength={setupRequired ? 12 : 1} autocomplete={setupRequired ? "new-password" : "current-password"} /></label>
      {#if setupRequired}<small>First account becomes the local administrator. Use at least 12 characters.</small>{/if}
      {#if error}<p class="error" role="alert">{error}</p>{/if}
      <button class="primary" disabled={!username || !password}>{setupRequired ? "Create administrator" : "Sign in"}</button>
    </form>
  </main>
{:else}
  <main class="workspace">
    <header><div><img src="/brand/symbol.svg" alt="" /><span><b>Notavra</b><small>LOCAL CLINICAL WORKSPACE</small></span></div><nav><button class:chosen={!directoryView} class="quiet" onclick={() => { directoryView = false; }}>Meetings</button><button class:chosen={directoryView} class="quiet" onclick={() => { directoryView = true; selectedPatient = null; loadPatients().catch(showError); }}>Patients</button></nav><span>{user.username} · {user.role}</span><button class="quiet" onclick={logout}>Sign out</button></header>
    {#if error}<p class="error" role="alert">{error}</p>{/if}
    {#if directoryView}
      <div class="columns">
        <aside><div class="panel-head"><h2>Patients</h2><span class="muted">{patientTotal} records</span></div><input aria-label="Search patients" placeholder="Name or hospital reference" bind:value={patientQuery} oninput={patientSearchChanged} /><ul class="meeting-list">{#each patients as patient (patient.id)}<li><button class:chosen={selectedPatient?.id === patient.id} onclick={() => openPatient(patient.id).catch(showError)}><b>{patient.displayName}</b><small>{patient.hospitalReference || "No hospital reference"} · {patient.status}</small></button></li>{/each}</ul>{#if patientHasMore}<button class="quiet" onclick={() => patientCursor && loadPatients(patientCursor, true).catch(showError)}>Show more</button>{/if}<form class="new-meeting" onsubmit={createPatient}><h3>Add patient</h3><label>Name<input name="displayName" required maxlength="160" /></label><label>Hospital reference<input name="hospitalReference" maxlength="120" /></label><button class="primary">Save patient</button></form></aside>
        <section class="content">{#if selectedPatient}<div class="panel-head"><div><p class="eyebrow">Patient record</p><h1>{selectedPatient.displayName}</h1><p class="muted">{selectedPatient.hospitalReference || "No hospital reference"} · {selectedPatient.status}</p></div><button class="primary" onclick={() => { directoryView = false; detail = null; }}>Start linked meeting</button></div><section class="panel"><h2>Linked meetings</h2>{#if selectedPatient.meetings?.length}<ul class="meeting-list">{#each selectedPatient.meetings as meeting (meeting.id)}<li><button onclick={() => { directoryView = false; openMeeting(meeting.id).catch(showError); }}><b>{meeting.title}</b><small>{new Date(meeting.recordedAt).toLocaleString()} · {meeting.status}</small></button></li>{/each}</ul>{:else}<p>No meetings are linked to this patient.</p>{/if}</section>{:else}<div class="empty"><span>02</span><h1>Patient directory</h1><p>Search by name or local hospital reference, or add a minimal patient record.</p></div>{/if}</section>
      </div>
    {:else}
    <div class="columns">
      <aside>
        <div class="panel-head"><h2>Meetings</h2><button class="quiet" onclick={() => { detail = null; }}>New</button></div>
        <input aria-label="Search meetings" placeholder="Search meetings" bind:value={query} oninput={searchChanged} />
        <ul class="meeting-list">{#each meetings as item (item.id)}<li><button class:chosen={detail?.meeting.id === item.id} onclick={() => openMeeting(item.id).catch(showError)}><b>{item.title}</b><small>{new Date(item.recordedAt).toLocaleString()} · {item.status}</small></button></li>{/each}</ul>
        <div class="pager"><button disabled={offset === 0} onclick={() => { offset = Math.max(0, offset - 10); loadMeetings().catch(showError); }}>←</button><span>{total ? offset + 1 : 0}–{Math.min(offset + 10, total)} of {total}</span><button disabled={offset + 10 >= total} onclick={() => { offset += 10; loadMeetings().catch(showError); }}>→</button></div>
        {#if !detail}<form class="new-meeting" onsubmit={createMeeting}><h3>Start a meeting</h3>{#if selectedPatient}<small>Will be linked to {selectedPatient.displayName} <button type="button" class="edit-button" onclick={() => (selectedPatient = null)}>Remove link</button></small>{/if}<label>Meeting title<input name="title" required maxlength="240" placeholder="Patient consultation" /></label><label>Transcript language<select bind:value={language}><option value="ro">Romanian</option><option value="ru">Russian</option><option value="en">English</option><option value="auto">Auto-detect</option></select></label><button class="primary" disabled={busy}>Create meeting</button></form>{/if}
      </aside>
      <section class="content">
        {#if detail}
          <div class="panel-head"><div><p class="eyebrow">{new Date(detail.meeting.recordedAt).toLocaleString()}</p><h1>{detail.meeting.title}</h1></div><div class="downloads"><button class="quiet" onclick={() => (detail = null)}>← Meetings</button>{#if detail.permission === "owner"}<button class="quiet" onclick={deleteMeeting}>Delete local meeting data</button>{/if}</div></div>
          {#if detail.asset}<p class="muted">Audio length: {(detail.asset.durationMs / 60000).toFixed(1)} min {#if detail.asset.decodeWarning}<span class="warning">· Audio decode warning</span>{/if}</p>{/if}
          {#each detail.captures as capture (capture.id)}<section class="panel"><h2>Unfinished microphone capture</h2><p>Only acknowledged chunks were saved ({(capture.received_bytes / 1048576).toFixed(1)} MB). The last part of speech may be missing. Process the saved portion or discard it.</p><div class="downloads"><button class="primary" disabled={busy || !capture.next_sequence} onclick={() => processSavedCapture(capture)}>Process saved portion</button><button class="quiet" disabled={busy} onclick={() => discardSavedCapture(capture)}>Discard saved chunks</button></div></section>{/each}
          <section class="panel"><h2>Add recording</h2><p>Upload audio or video, or record through the microphone. Live words are provisional; after Stop, local ASR fills skipped windows from the saved recording.</p><div class="live-record"><button class:recording class="quiet" type="button" onclick={() => recording ? stopRecording() : startRecording()} disabled={busy}>{recording ? "Stop recording" : "● Record live"}</button>{#if recording}<span class="record-indicator"><i></i> Recording · {formatElapsed(recordingSeconds)}<label class="record-health">Microphone level <meter min="0" max="1" value={microphoneLevel}></meter></label><small>{acknowledgedCaptureChunks} {acknowledgedCaptureChunks === 1 ? "chunk" : "chunks"} saved · {pendingChunkUploads} pending</small></span>{/if}</div>{#if livePreviewStatus}<p role="status" class="status">{livePreviewStatus}</p>{/if}{#if liveSegments.length}<section class="panel live-transcript"><h3>Live transcript <span>Provisional</span></h3><div class="transcript">{#each liveSegments as segment (segment.id)}<p><time>{formatTime(segment.startMs)}</time><span>{segment.text}</span><small>{segment.language}</small></p>{/each}</div></section>{/if}<form class="upload-form" onsubmit={upload}>
            <label class="file-input">Recording file<input name="audio" type="file" accept="audio/*,video/*,.m4a,.mp3,.wav,.mp4,.mov,.webm" required /></label>
            <label>Hardware profile<select bind:value={profileId}>{#each profiles as p (p.id)}<option value={p.id} disabled={!p.compatible}>{p.id === "laptop8" ? "Laptop · RTX 3070 Ti · 8 GB" : p.id === "hospital16" ? "Workstation · RTX 5080 · 16 GB" : p.id} {!p.compatible ? "· unavailable on this computer" : p.asrFilesPresent && p.llmFilePresent ? "· ready" : "· models missing"}</option>{/each}</select></label>
            <label>ASR language<select bind:value={language}><option value="ro">Romanian</option><option value="ru">Russian</option><option value="en">English</option><option value="auto">Auto-detect</option></select></label>
            <button class="primary" disabled={busy || recording || !profiles.find((p) => p.id === profileId)?.asrFilesPresent || !profiles.find((p) => p.id === profileId)?.llmFilePresent}>{busy ? "Processing…" : "Transcribe recording"}</button>
          </form>{#if status}<p role="status" class="status">{status}</p>{/if}</section>
          {#if detail.asset}<audio class="audio-review" controls preload="none" src={`/api/meetings/${detail.meeting.id}/audio`}>Audio playback is unavailable in this browser.</audio>{/if}
          {#if detail.segments.length}<section class="panel"><div class="panel-head"><h2>Transcript <span>{detail.segments.length} passages · click edit to correct</span></h2><div class="downloads">{#if detail.canUndoCorrection && user.role !== "reviewer"}<button class="quiet" onclick={undoLastCorrection}>Undo last correction</button>{/if}<button class="quiet" onclick={() => downloadTranscript("txt")}>TXT</button><button class="quiet" onclick={() => downloadTranscript("json")}>JSON</button></div></div>
            <div class="find-toolbar"><label>Find in transcript<input bind:value={findQuery} oninput={() => (activeFindIndex = 0)} onkeydown={findKeydown} placeholder="Search Romanian or Cyrillic text" /></label><span>{searchMatches.length ? `${activeFindIndex + 1} of ${searchMatches.length}` : "0 matches"}</span><button class="quiet" disabled={!searchMatches.length} onclick={() => moveFindMatch(-1)}>↑ Previous</button><button class="quiet" disabled={!searchMatches.length} onclick={() => moveFindMatch(1)}>↓ Next</button></div>
            {#if findQuery.trim() && user.role !== "reviewer"}{@const bulkPreview = buildSelectedCorrections()}<div class="bulk-correction"><label>Replace with<input bind:value={replacementText} placeholder="Correct spelling or term" /></label><button class="primary" disabled={!bulkPreview.count} onclick={replaceInSelectedPassages}>Replace {bulkPreview.count} matches in selected passages</button><span>{bulkPreview.corrections.length} passages selected for change</span></div>{#each bulkPreview.corrections as correction (correction.segmentId)}<details class="correction-preview"><summary>Preview before and after</summary><del>{correction.oldText}</del><p>{correction.text}</p></details>{/each}{/if}
            <div class="transcript">{#each detail.segments as segment (segment.id)}{@const parts = highlightParts(segment.text, segment.id)}<p class:with-find={!!findQuery.trim() && user.role !== "reviewer"} id={`segment-${segment.id}`}><button class="play-passage" type="button" aria-label={`Play audio from ${formatTime(segment.startMs)}`} title="Play from this passage" onclick={() => playPassage(segment.startMs)}>▶</button><time>{formatTime(segment.startMs)}</time>{#if findQuery.trim() && user.role !== "reviewer"}<input class="select-match" type="checkbox" value={segment.id} bind:group={selectedCorrectionSegments} aria-label={`Select passage at ${formatTime(segment.startMs)} for bulk correction`} />{/if}{#if editingSegment === segment.id}<span class="edit-cell"><textarea bind:value={editText} rows="2"></textarea><button class="primary" onclick={() => saveSegment(segment)}>Save correction</button><button class="quiet" onclick={() => (editingSegment = null)}>Cancel</button></span>{:else}<span>{#each parts as part}<mark class:current={part.current} class:found={part.match}>{part.text}</mark>{/each}</span>{#if user.role !== "reviewer"}<button class="edit-button" onclick={() => { editingSegment = segment.id; editText = segment.text; }}>Edit</button>{/if}{/if}<small>{segment.language}</small></p>{/each}</div></section>{/if}
          {#if detail.decisions}<section class="panel"><h2>Decisions and actions <span>human review required</span></h2>{#if detail.decisions.items?.length}{#each detail.decisions.items as item (item.id)}<article class="action-card"><div class="action-title"><span class="action-kind">{item.kind}</span><span class="action-state">{item.status}</span><b>{item.text}</b></div><div class="action-meta">{#if item.ownerLabel}<span>Owner: {item.ownerLabel}</span>{/if}{#if item.originalDateExpression}<span>Due: {item.originalDateExpression}</span>{/if}<span>Review: {item.reviewStatus || "needs_review"}</span></div>{#each item.taskEvidence as evidence (evidence.segmentId + evidence.startMs)}<blockquote><time>{formatTime(evidence.startMs)}</time>“{evidence.quote}”</blockquote>{/each}{#if user.role !== "reviewer"}<div class="downloads"><button class:chosen={item.reviewStatus === "accepted"} class="quiet" onclick={() => reviewDecision(item.id, "accepted")}>Include in minutes</button><button class:chosen={item.reviewStatus === "excluded"} class="quiet" onclick={() => reviewDecision(item.id, "excluded")}>Exclude</button></div>{/if}</article>{/each}{:else}<p>No decisions or follow-up actions were identified.</p>{/if}<small class="review-note">Suggested by local AI and backed by transcript excerpts. Confirm or correct before use.</small></section>{/if}
          {#if detail.artifact}<p class="status">Current approved file · revision {detail.meeting.transcriptRevision} · SHA-256 {detail.artifact.sha256} · <a href={`/api/artifacts/${detail.artifact.id}/content`}>Download again</a></p>{/if}
          {#if detail.decisions && user.role !== "reviewer"}<section class="panel"><label class="approval"><input type="checkbox" bind:checked={reviewConfirmed} /> I reviewed the transcript and every suggested decision/action above.</label>{#if !allDecisionsReviewed()}<p class="muted">Include or exclude each suggested action before approving minutes.</p>{/if}<button class="primary" disabled={!reviewConfirmed || !allDecisionsReviewed()} onclick={approveAndDownload}>Approve and download HTML minutes</button><p class="muted">This creates a local, self-contained file for the current transcript revision. Corrections supersede it.</p></section>{/if}
          {#if detail.asset && detail.latestJob?.state === "failed" && user.role !== "reviewer"}<section class="panel"><p>Local processing stopped at {detail.latestJob.stage} ({detail.latestJob.errorCode || "unknown error"}). Retry resumes from the saved checkpoint when available.</p><button class="primary" disabled={busy} onclick={retryFailedJob}>Retry failed step</button></section>{/if}
          {#if detail.asset && !detail.decisions && user.role !== "reviewer"}<section class="panel"><p>The transcript changed or decision extraction is not ready. Re-run processing from the saved audio before approving minutes.</p><button class="primary" disabled={busy} onclick={reprocessSavedAudio}>Reprocess saved audio locally</button></section>{/if}
          {#if !detail.segments.length}<div class="empty"><span>01</span><h2>Upload the recording</h2><p>Notavra processes the audio locally, then shows the transcript and evidence-backed actions here.</p></div>{/if}
        {:else}<div class="empty"><span>01</span><h1>Clinical meetings, ready to review</h1><p>Choose a meeting, or start one and upload its audio. Transcription and action extraction run locally on the selected profile.</p></div>{/if}
      </section>
    </div>
    {/if}
    <footer>Local inference · No runtime cloud calls · Verify every transcript and action before clinical use</footer>
  </main>
{/if}

<style>
  :global(body){margin:0;background:#f4f6f8;color:#17212b;font:15px/1.5 "Noto Sans",system-ui,sans-serif} :global(button),:global(input),:global(select){font:inherit} :global(button){cursor:pointer}
  .auth-shell{min-height:100vh;display:grid;place-items:center}.auth-card{display:grid;gap:16px;background:white;border:1px solid #e0e6ec;border-radius:18px;padding:36px;width:min(420px,calc(100vw - 48px));box-shadow:0 18px 60px #182d4212}.auth-card img{width:166px}.auth-card h1,.auth-card p{margin:0}.auth-card>p,.muted{color:#667583}.auth-card label,.new-meeting label,.upload-form label{display:grid;gap:6px;font-weight:600}.auth-card input,.new-meeting input,.workspace input,.workspace select{box-sizing:border-box;width:100%;border:1px solid #d7e0e7;border-radius:9px;background:#fff;padding:10px 12px;color:#17212b}.primary{border:0;border-radius:9px;background:#126a62;color:white;font-weight:700;padding:11px 16px}.primary:disabled{opacity:.5;cursor:not-allowed}.error{margin:16px;padding:12px 14px;border-radius:8px;background:#ffeded;color:#a12b2b}
  .workspace{max-width:1440px;margin:auto;padding:22px 32px;min-height:100vh;box-sizing:border-box;display:grid;grid-template-rows:auto 1fr auto;gap:20px}.workspace header{display:flex;align-items:center;gap:16px;border-bottom:1px solid #dfe5e9;padding-bottom:16px}.workspace header>div{display:flex;align-items:center;gap:10px;margin-right:auto}.workspace header img{width:34px;height:36px}.workspace header span{display:grid}.workspace header small{font-size:10px;letter-spacing:.1em;color:#71808b}.quiet{background:white;border:1px solid #d9e0e5;border-radius:8px;padding:8px 12px;color:#37505d}.columns{display:grid;grid-template-columns:330px minmax(0,1fr);gap:22px;min-height:0}.columns aside,.content{min-width:0}.columns aside{border-right:1px solid #dfe5e9;padding-right:20px}.panel-head{display:flex;align-items:center;justify-content:space-between;gap:12px}.panel-head h1,.panel-head h2{margin:0}.meeting-list{list-style:none;padding:0;margin:12px 0}.meeting-list button{width:100%;display:grid;text-align:left;border:0;border-radius:8px;background:transparent;padding:12px;color:inherit;gap:4px}.meeting-list button:hover,.meeting-list button.chosen{background:#e7f2f0}.meeting-list small,.muted,.eyebrow{color:#71808b}.pager{display:flex;justify-content:space-between;align-items:center;color:#6c7a85;font-size:13px}.pager button{border:1px solid #d9e0e5;border-radius:6px;background:white;padding:5px 10px}.pager button:disabled{opacity:.4}.new-meeting{display:grid;gap:12px;border-top:1px solid #dfe5e9;margin-top:18px;padding-top:18px}.new-meeting h3{margin:0}.content{display:grid;align-content:start;gap:16px}.eyebrow{margin:0 0 3px;font-size:13px}.panel{background:white;border:1px solid #e1e6ea;border-radius:12px;padding:18px 20px}.panel h2{font-size:18px;margin:0 0 8px}.panel h2 span{font-size:12px;font-weight:400;color:#71808b;margin-left:8px}.panel>p{margin:0 0 14px;color:#687985}.upload-form{display:grid;grid-template-columns:minmax(180px,1fr) 220px 155px auto;align-items:end;gap:12px}.upload-form input[type=file]{padding:8px}.upload-form label{font-size:13px}.status{color:#17675f;margin:14px 0 0}.transcript{max-height:55vh;overflow:auto}.transcript p{display:grid;grid-template-columns:25px 76px 1fr 35px;gap:12px;border-bottom:1px solid #eef1f3;padding:10px 0;margin:0}.transcript time,.transcript small{color:#82909a;font-size:12px}.warning{color:#9a6512}.empty{align-self:center;justify-self:center;max-width:560px;text-align:center;padding:56px 20px}.empty>span{display:inline-grid;place-items:center;background:#dcefea;color:#14655c;border-radius:50%;width:42px;height:42px;font-weight:800}.empty p{color:#6e7d87}.workspace footer{text-align:center;color:#81909a;font-size:12px;border-top:1px solid #dfe5e9;padding-top:12px}
  .transcript p{grid-template-columns:25px 76px 1fr 52px 35px}.edit-button{border:0;background:transparent;color:#17675f;font-size:12px}.edit-cell{display:grid;grid-template-columns:1fr auto auto;gap:8px}.edit-cell textarea{width:100%;box-sizing:border-box;border:1px solid #d7e0e7;border-radius:6px;padding:8px;font:inherit}.downloads{display:flex;gap:7px}.action-card{border-top:1px solid #eef1f3;padding:14px 0}.action-title{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.action-title b{font-size:15px}.action-kind,.action-state{border-radius:999px;background:#e8f2f0;color:#17675f;padding:3px 9px;font-size:11px;text-transform:capitalize}.action-state{background:#f1f2ed;color:#71632e}.action-meta{display:flex;gap:16px;color:#687985;font-size:13px;margin:8px 0}.action-card blockquote{margin:8px 0 0 12px;border-left:2px solid #83b7ad;padding:4px 10px;color:#42565f;font-size:13px}.action-card blockquote time{color:#81909a;margin-right:8px;font-size:11px}.review-note{display:block;border-top:1px solid #eef1f3;padding-top:10px;color:#71808b}
  .transcript p.with-find{grid-template-columns:25px 76px 24px 1fr 52px 35px}.select-match{align-self:center}.find-toolbar,.bulk-correction{display:flex;align-items:end;gap:10px;margin:10px 0 14px;flex-wrap:wrap}.find-toolbar label,.bulk-correction label{display:grid;gap:5px;font-size:12px;color:#71808b;min-width:200px}.find-toolbar input,.bulk-correction input{border:1px solid #d7e0e7;border-radius:6px;padding:8px;font:inherit}.find-toolbar span{color:#61727c;font-size:12px;margin:0 auto 8px 0}.bulk-correction{background:#f6f9f8;padding:10px;border-radius:8px}.audio-review{width:100%;margin:8px 0 14px}.play-passage{align-self:start;width:25px;height:25px;padding:0;border:1px solid #d9e0e5;border-radius:6px;background:white;color:#17675f;cursor:pointer}.play-passage:hover{background:#e7f2f0}.transcript mark{background:#fff0af;color:inherit}.transcript mark.current{background:#ffce57;outline:2px solid #e6a400;border-radius:2px}
  .approval{display:flex;align-items:center;gap:9px;margin-bottom:14px;font-size:14px}.approval input{width:auto}.live-record{display:flex;align-items:center;gap:12px;margin:0 0 16px}.quiet.recording{border-color:#cd5b58;color:#a73535}.record-indicator{display:flex;align-items:center;gap:8px;color:#aa3d3d;font-size:13px;font-variant-numeric:tabular-nums}.record-indicator i{width:9px;height:9px;border-radius:50%;background:#cd4b48;animation:pulse 1.2s infinite}.record-health{display:flex;align-items:center;gap:8px;color:#71808b}.record-health meter{width:100px;height:12px}.record-indicator small{color:#71808b;font-size:11px;font-weight:400}.live-transcript{margin-top:12px;background:#f7faf9;padding:12px 16px}.live-transcript h3{margin:0 0 6px;font-size:14px}.live-transcript h3 span{color:#71808b;font-size:11px;font-weight:400}.live-transcript .transcript{max-height:28vh}@keyframes pulse{50%{opacity:.3}}
  @media(max-width:900px){.columns{grid-template-columns:1fr}.columns aside{border:0;padding:0}.upload-form{grid-template-columns:1fr 1fr}.workspace{padding:18px}.transcript p{grid-template-columns:25px 62px 1fr 52px 35px}.transcript p.with-find{grid-template-columns:25px 62px 24px 1fr 52px 35px}}
</style>
