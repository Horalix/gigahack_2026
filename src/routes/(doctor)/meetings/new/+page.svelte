<script lang="ts">
  import { goto } from "$app/navigation";
  import { page } from "$app/state";
  import LanguageBadge from "$lib/components/meetings/language-badge.svelte";
  import { groupFor, sampleSegments } from "$lib/prototype/fixtures";
  import { chisinauIso, formatBytes, formatMs, MEETING_TYPE_LABEL, nowLocalInput } from "$lib/prototype/format";
  import { createMeeting, db, getPatient } from "$lib/prototype/store.svelte";
  import type { MeetingType, Segment } from "$lib/prototype/types";

  const MAX_BYTES = 2 * 1024 ** 3; // the service's documented upload limit
  const MEETING_TYPES: MeetingType[] = ["medical", "executive", "administrative"];
  const PROVISIONAL_SOURCE = sampleSegments("preview");

  // --- Details ---
  const presetPatient = page.url.searchParams.get("patient");
  let mode = $state<"upload" | "record">(page.url.searchParams.get("mode") === "record" ? "record" : "upload");
  let title = $state("");
  let meetingType = $state<MeetingType>("medical");
  let recordedAtLocal = $state(nowLocalInput());
  let outputLanguage = $state<"ro" | "ru" | "en">("ro");
  let patientIds = $state<string[]>(presetPatient && getPatient(presetPatient) ? [presetPatient] : []);

  const group = $derived(groupFor(meetingType));
  const linkable = $derived(
    [...db.patients].filter((p) => !patientIds.includes(p.id)).sort((a, b) => a.displayName.localeCompare(b.displayName)),
  );

  // --- Upload ---
  let fileInput: HTMLInputElement | undefined = $state();
  let file = $state<File | null>(null);
  let fileError = $state<string | null>(null);
  let dragging = $state(false);

  function pickFile(candidate: File | undefined) {
    if (!candidate) return;
    fileError = null;
    const looksLikeMedia =
      candidate.type.startsWith("audio/") ||
      candidate.type.startsWith("video/") ||
      /\.(m4a|mp3|wav|flac|ogg|opus|webm|mp4|mkv|mov)$/i.test(candidate.name);
    if (!looksLikeMedia) {
      file = null;
      fileError = "That doesn't look like an audio or video file.";
    } else if (candidate.size > MAX_BYTES) {
      file = null;
      fileError = "Recordings up to 2 GB are supported.";
    } else {
      // The title is deliberately not filled from the file name: file names
      // often carry patient names, and the service ignores them for that reason.
      file = candidate;
    }
  }

  // --- Recording (simulated) ---
  type RecState = "idle" | "recording" | "paused" | "stopped";
  let rec = $state<RecState>("idle");
  let elapsedMs = $state(0);
  let levels = $state<number[]>(Array(32).fill(0.04));
  let chunks = $state(0);
  let provisional = $state<Segment[]>([]);

  $effect(() => {
    if (rec !== "recording") return;
    const timer = setInterval(() => {
      elapsedMs += 100;
      levels = [...levels.slice(1), 0.08 + Math.random() * (Math.random() > 0.25 ? 0.9 : 0.15)];
      if (elapsedMs % 1000 === 0) chunks += 1;
      if (elapsedMs % 3000 === 0 && provisional.length < PROVISIONAL_SOURCE.length) {
        provisional = [...provisional, PROVISIONAL_SOURCE[provisional.length]];
      }
    }, 100);
    return () => clearInterval(timer);
  });

  function discardRecording() {
    rec = "idle";
    elapsedMs = 0;
    chunks = 0;
    provisional = [];
    levels = Array(32).fill(0.04);
  }

  // --- Submit ---
  const sourceReady = $derived(mode === "upload" ? file !== null : rec === "stopped" && elapsedMs >= 1000);
  const canStart = $derived(title.trim().length > 0 && sourceReady);
  const busyRecording = $derived(rec === "recording" || rec === "paused");

  function start() {
    if (!canStart) return;
    const id = createMeeting({
      title: title.trim(),
      recordedAt: chisinauIso(recordedAtLocal),
      meetingType,
      outputLanguage,
      patientIds,
      source:
        mode === "upload" && file
          ? { kind: "upload", label: file.name, sizeBytes: file.size, durationMs: 0 }
          : { kind: "recording", label: "Microphone recording", sizeBytes: null, durationMs: elapsedMs },
    });
    goto(`/meetings/${id}`);
  }
</script>

<svelte:head><title>New meeting · Secure MOM</title></svelte:head>

<div class="page">
  <div class="page-head">
    <div>
      <h1>New meeting</h1>
      <p class="muted meta">Add the details, then upload a recording or record the meeting live.</p>
    </div>
  </div>

  <div class="grid-2">
    <section class="card" aria-labelledby="details-title">
      <h2 id="details-title">Details</h2>

      <label class="field">
        <span>Title</span>
        <input type="text" bind:value={title} placeholder="e.g. Consiliul medical, 26 septembrie" maxlength="240" />
      </label>

      <div class="field">
        <span>Meeting type</span>
        <div class="segmented" role="group" aria-label="Meeting type">
          {#each MEETING_TYPES as type (type)}
            <button type="button" aria-pressed={meetingType === type} onclick={() => (meetingType = type)}>
              {MEETING_TYPE_LABEL[type]}
            </button>
          {/each}
        </div>
      </div>

      <div class="two">
        <label class="field">
          <span>Date and time (Chișinău)</span>
          <input type="datetime-local" bind:value={recordedAtLocal} />
        </label>
        <label class="field">
          <span>Minutes language</span>
          <select bind:value={outputLanguage}>
            <option value="ro">Romanian</option>
            <option value="ru">Russian</option>
            <option value="en">English</option>
          </select>
        </label>
      </div>

      <div class="field">
        <span>Linked patients <em class="subtle">(optional)</em></span>
        {#if patientIds.length}
          <div class="chips">
            {#each patientIds as id (id)}
              {@const p = getPatient(id)}
              <span class="chip tone-accent">
                {p?.displayName} <span class="mono">{p?.reference ?? ""}</span>
                <button type="button" class="x" aria-label="Unlink {p?.displayName}" onclick={() => (patientIds = patientIds.filter((x) => x !== id))}>×</button>
              </span>
            {/each}
          </div>
        {/if}
        <select
          aria-label="Link a patient"
          value=""
          onchange={(e) => {
            const id = e.currentTarget.value;
            if (id) patientIds = [...patientIds, id];
            e.currentTarget.value = "";
          }}
        >
          <option value="">Link a patient…</option>
          {#each linkable as p (p.id)}
            <option value={p.id}>{p.displayName} · {p.reference ?? "no reference"}</option>
          {/each}
        </select>
        <span class="subtle">Linking is always a manual choice. Patients are never matched from what is said.</span>
      </div>

      <div class="inset recipients">
        <span class="subtle">Minutes will be emailed to</span>
        <strong>{group.label}</strong>
        <span class="subtle">
          {[...group.to, ...group.cc].map((r) => r.name).join(", ")}
        </span>
        <span class="subtle">Set by meeting type in configuration, never taken from the recording.</span>
      </div>
    </section>

    <section class="card" aria-labelledby="audio-title">
      <div class="card-head">
        <h2 id="audio-title">Audio</h2>
        <div class="segmented" role="group" aria-label="Audio source">
          <button type="button" aria-pressed={mode === "upload"} disabled={busyRecording} onclick={() => (mode = "upload")}>Upload</button>
          <button type="button" aria-pressed={mode === "record"} onclick={() => (mode = "record")}>Record</button>
        </div>
      </div>

      {#if mode === "upload"}
        <div
          class="drop"
          class:dragging
          role="region"
          aria-label="Drop a recording here"
          ondragover={(e) => {
            e.preventDefault();
            dragging = true;
          }}
          ondragleave={() => (dragging = false)}
          ondrop={(e) => {
            e.preventDefault();
            dragging = false;
            pickFile(e.dataTransfer?.files[0]);
          }}
        >
          {#if file}
            <strong>{file.name}</strong>
            <span class="subtle">{formatBytes(file.size)} · {file.type || "unknown type"}</span>
            <button type="button" class="btn btn-sm" onclick={() => (file = null)}>Choose a different file</button>
          {:else}
            <span class="big" aria-hidden="true">⤒</span>
            <strong>Drop an audio or video file here</strong>
            <span class="subtle">M4A, MP3, WAV, FLAC, MP4, WebM · up to 2 GB</span>
            <button type="button" class="btn" onclick={() => fileInput?.click()}>Browse files</button>
          {/if}
          <input
            bind:this={fileInput}
            type="file"
            accept="audio/*,video/*"
            hidden
            onchange={(e) => pickFile(e.currentTarget.files?.[0])}
          />
        </div>
        {#if fileError}
          <p class="notice danger" role="alert">{fileError}</p>
        {/if}
        <p class="subtle">The file stays on this computer. In the prototype it is not read at all.</p>
      {:else}
        <div class="recorder">
          <div class="rec-top">
            <span class="timer mono" class:live={rec === "recording"}>
              {#if rec === "recording"}<span class="pulse" aria-hidden="true"></span>{/if}
              {formatMs(elapsedMs)}
            </span>
            <span class="subtle">
              {#if rec === "idle"}Ready
              {:else if rec === "recording"}Recording · saved locally ({chunks} chunks)
              {:else if rec === "paused"}Paused · saved locally ({chunks} chunks)
              {:else}Recording ready{/if}
            </span>
          </div>

          <div class="meter" aria-hidden="true">
            {#each levels as level, i (i)}
              <span style="height: {Math.round(level * 100)}%" class:quiet={rec !== "recording"}></span>
            {/each}
          </div>

          <div class="actions">
            {#if rec === "idle"}
              <button type="button" class="btn btn-primary btn-lg" onclick={() => (rec = "recording")}>● Start recording</button>
            {:else if rec === "recording"}
              <button type="button" class="btn" onclick={() => (rec = "paused")}>❚❚ Pause</button>
              <button type="button" class="btn btn-danger" onclick={() => (rec = "stopped")}>■ Stop</button>
            {:else if rec === "paused"}
              <button type="button" class="btn btn-primary" onclick={() => (rec = "recording")}>● Resume</button>
              <button type="button" class="btn btn-danger" onclick={() => (rec = "stopped")}>■ Stop</button>
            {:else}
              <button type="button" class="btn btn-sm" onclick={discardRecording}>Discard and start over</button>
            {/if}
          </div>

          {#if provisional.length}
            <div class="provisional">
              <span class="subtle">Live transcript · provisional, corrected after the meeting</span>
              <ul>
                {#each provisional.slice(-4) as seg (seg.id)}
                  <li><LanguageBadge language={seg.language} /> {seg.text}</li>
                {/each}
              </ul>
            </div>
          {/if}
          <p class="subtle">Microphone input is simulated in the prototype; no permission is requested.</p>
        </div>
      {/if}
    </section>
  </div>

  <div class="submit">
    <span class="subtle">
      {#if !title.trim()}Add a title to continue.
      {:else if !sourceReady}{mode === "upload" ? "Choose a recording to continue." : "Record and stop to continue."}
      {:else}Processing runs on this computer. You can leave the page while it works.{/if}
    </span>
    <a class="btn" href="/dashboard">Cancel</a>
    <button class="btn btn-primary btn-lg" disabled={!canStart} onclick={start}>Start processing →</button>
  </div>
</div>

<style>
  .two {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
  }
  .chips {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
  }
  .x {
    border: 0;
    background: none;
    color: inherit;
    cursor: pointer;
    font-size: 1rem;
    line-height: 1;
    padding: 0 2px;
  }
  .recipients {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .drop {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 8px;
    min-height: 220px;
    padding: 20px;
    text-align: center;
    border: 2px dashed var(--borderColor-emphasis);
    border-radius: var(--radius-default);
    background: var(--bgColor-inset);
  }
  .drop.dragging {
    border-color: var(--borderColor-accent);
    background: var(--bgColor-accent-muted);
  }
  .big {
    font-size: 2rem;
    color: var(--fgColor-subtle);
  }
  .recorder {
    display: flex;
    flex-direction: column;
    gap: 14px;
  }
  .rec-top {
    display: flex;
    align-items: baseline;
    gap: 14px;
  }
  .timer {
    font-size: 2.2rem;
    font-weight: 600;
    display: inline-flex;
    align-items: center;
    gap: 10px;
  }
  .timer.live {
    color: var(--danger-fg);
  }
  .pulse {
    width: 12px;
    height: 12px;
    border-radius: 50%;
    background: var(--danger-fg);
    animation: pulse 1.2s ease-in-out infinite;
  }
  @keyframes pulse {
    50% {
      opacity: 0.25;
    }
  }
  .meter {
    display: flex;
    align-items: flex-end;
    gap: 3px;
    height: 56px;
    padding: 6px;
    border-radius: var(--radius-default);
    background: var(--bgColor-inset);
  }
  .meter span {
    flex: 1;
    min-height: 3px;
    border-radius: 2px;
    background: var(--fgColor-accent);
    transition: height 0.1s linear;
  }
  .meter span.quiet {
    opacity: 0.35;
  }
  .provisional ul {
    list-style: none;
    margin: 6px 0 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 6px;
    font-size: 0.92rem;
    color: var(--fgColor-muted);
    font-style: italic;
  }
  .submit {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 12px;
    flex-wrap: wrap;
    padding-top: 8px;
    border-top: 1px solid var(--borderColor-default);
  }
  .submit .subtle {
    margin-right: auto;
  }
</style>
