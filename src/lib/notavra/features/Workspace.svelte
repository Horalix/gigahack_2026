<script lang="ts">
  // Port of features/Workspace.tsx, plus the start-to-email flow card:
  // new audio is processed without a separate click, and the card carries the
  // meeting from recording or upload to one "Approve & send".
  import { ChevronDown, Settings2 } from "@lucide/svelte";
  import { tick, untrack } from "svelte";
  import { errorMessage } from "../errors";
  import { api, type Job, type Meeting } from "../api";
  import type { Labels } from "../i18n";
  import { createQuery, invalidateQueries, type Query } from "../query.svelte";
  import { tr } from "../translations.svelte";
  import AudioChecks from "./AudioChecks.svelte";
  import CandidateHistory from "./CandidateHistory.svelte";
  import CorrectionForm from "./CorrectionForm.svelte";
  import JobProgress from "./JobProgress.svelte";
  import MeetingAudio from "./MeetingAudio.svelte";
  import { createMeetingAudio } from "./meetingAudioState.svelte";
  import MeetingDetails from "./MeetingDetails.svelte";
  import MeetingFlow from "./MeetingFlow.svelte";
  import type { Intent } from "./flow";
  import Recorder from "./Recorder.svelte";
  import Snapshot from "./Snapshot.svelte";
  import TranscriptExperience, { loadTranscript } from "./TranscriptExperience.svelte";
  import { activeSegment, speakerIndex, speakerPalette, timeLabel, type SpeechSegment } from "./transcriptModel";

  let {
    id,
    t,
    back,
    role,
    intent,
    intentDone,
  }: { id: string; t: Labels; back: () => void; role: string; intent?: Intent; intentDone?: () => void } = $props();

  const OPTIONAL = ["parakeet", "diarization"] as const;
  const TABS = ["review", "transcript", "minutes"] as const;
  const FIELDS = ["owner", "due", "condition", "value"] as const;
  const CATEGORIES = ["all", "action", "decision", "information"] as const;

  let tab = $state<"review" | "transcript" | "minutes">("transcript");
  let error = $state("");
  let busy = $state(false);
  let search = $state("");
  let selection = $state<string | null>(null);
  let field = $state("text");
  let toolsOpen = $state(false);
  let category = $state("all");
  let jumpId = $state<string>();
  let profile = $state({ device: "cuda", parakeet: false, diarization: false });
  let uploading = $state<string | null>(null);
  let recording = $state(false);
  let saving = $state(false); // recording stopped; waiting for the saved audio to show up

  const capabilities = createQuery({ key: () => ["proof"], fn: () => api<any>("/system/proof") });
  // Poll faster while processing, so the finished minutes appear promptly.
  const meeting: Query<Meeting> = createQuery({
    key: () => ["meeting", id],
    fn: () => api<Meeting>(`/meetings/${id}`),
    interval: () => (meeting.data?.jobs?.some((j) => ["queued", "running"].includes(j.state)) ? 1000 : 2000),
  });
  const review = createQuery({ key: () => ["review", id], fn: () => api<any>(`/meetings/${id}/items`), interval: 4000 });
  const transcript = createQuery({
    key: () => ["transcript-all", id, meeting.data?.revision],
    fn: () => loadTranscript(id),
    interval: () => (meeting.data?.jobs?.some((j) => ["queued", "running"].includes(j.state)) ? 5000 : false),
  });
  const audio = createMeetingAudio(() => meeting.data?.assets);
  const segments = $derived((transcript.data || []).filter((s) => s.asset_id === audio.asset?.id));
  const active = $derived(activeSegment(segments, audio.current));
  const seek = (s: SpeechSegment) => audio.seek(s.start / 16000, true, s.asset_id);

  async function saveTranscript(s: SpeechSegment, text: string, speaker: string | null) {
    busy = true;
    try {
      await api(`/segments/${s.id}/revisions`, "POST", { revision: s.revision, text, speaker });
      await invalidateQueries();
    } finally {
      busy = false;
    }
  }

  const snapshots = createQuery({ key: () => ["snapshots", id], fn: () => api<any[]>(`/meetings/${id}/snapshots`) });
  const groups = createQuery({ key: () => ["groups"], fn: () => api<any[]>("/recipient-groups") });

  const refresh = async () => {
    await invalidateQueries();
  };

  async function act(fn: () => Promise<unknown>) {
    error = "";
    busy = true;
    try {
      await fn();
      await refresh();
    } catch (failure) {
      error = failure instanceof Error ? failure.message : tr("The request failed. Check the form, refresh, and try again.");
    } finally {
      busy = false;
    }
  }

  /** Start processing new audio right away, unless something is already running. */
  async function processNew(asset?: { id: string }) {
    if (!asset || meeting.data?.jobs?.some((j) => ["queued", "running"].includes(j.state))) return;
    await api(`/meetings/${id}/jobs`, "POST", { asset_id: asset.id, ...profile });
  }

  async function upload(file: File) {
    const form = new FormData();
    form.append("file", file);
    uploading = file.name;
    try {
      await act(async () => {
        const asset = await api<{ id: string }>(`/meetings/${id}/uploads`, "POST", form);
        await processNew(asset);
      });
      await meeting.refetch(); // show the new audio and job before leaving the uploading state
    } finally {
      uploading = null;
    }
  }

  async function recorded(asset?: { id: string }) {
    saving = true;
    recording = false;
    try {
      await act(() => processNew(asset));
      await meeting.refetch();
    } finally {
      saving = false;
    }
  }

  // Carry out what the start panel asked for, once.
  $effect(() => {
    const next = intent;
    if (!next || !meeting.data) return;
    untrack(() => {
      intentDone?.();
      if (next.kind === "record") recording = true;
      else void upload(next.file);
    });
  });

  // New results bump the meeting revision: fetch the review items straight away.
  $effect(() => {
    meeting.data?.revision;
    untrack(() => void review.refetch());
  });

  async function openItem(itemId: string) {
    tab = "review";
    category = "all";
    search = "";
    selection = itemId;
    field = "text";
    await tick();
    document.querySelector(".review-toolbar")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function play(segment: { asset_id: string; start: number }) {
    audio.seek(Math.max(0, segment.start / 16000 - 2), true, segment.asset_id);
  }

  async function openTranscript(ref: any) {
    try {
      const segment = await api<SpeechSegment>(`/segments/${ref.segment_id}`);
      jumpId = segment.id;
      tab = "transcript";
      audio.seek(segment.start / 16000, true, segment.asset_id);
    } catch (failure) {
      error = String(failure);
    }
  }

  async function playEvidence(ref: any) {
    try {
      const segment = await api(`/segments/${ref.segment_id}`);
      play(segment);
    } catch (failure) {
      error = failure instanceof Error ? failure.message : tr("The request failed. Check the form, refresh, and try again.");
    }
  }

  function importTranscript(e: SubmitEvent) {
    e.preventDefault();
    const form = new FormData(e.currentTarget as HTMLFormElement),
      file = form.get("transcript") as File,
      revision = m!.revision;
    void act(async () => {
      await api(`/meetings/${id}/transcript-imports`, "POST", { asset_id: form.get("asset"), revision, source: await file.text(), filename: file.name });
    });
  }

  const m = $derived(meeting.data);
  const candidates = $derived<any[]>(review.data?.candidates || []);
  const visibleCandidates = $derived(
    candidates.filter(
      (c) =>
        (category === "all" || c.body.category === category) &&
        (!search || `${c.body.subject} ${c.body.text}`.toLocaleLowerCase().includes(search.toLocaleLowerCase())),
    ),
  );
  const selected = $derived(visibleCandidates.find((c) => c.id === selection) || visibleCandidates[0]);
  const latestJobs = $derived.by(() => {
    const latest = new Map<string, Job>();
    for (const job of m?.jobs || []) if (!job.transcript_only && job.created >= (latest.get(job.asset_id)?.created ?? -1)) latest.set(job.asset_id, job);
    return Array.from(latest.values());
  });
  const refs = $derived<any[]>(selected?.evidence?.filter((e: any) => e.field === field) || []);
  const anyRunning = $derived(!!m?.jobs?.some((j) => ["queued", "running"].includes(j.state)));
  const openItems = $derived(candidates.filter((c) => !["accepted", "excluded"].includes(c.review)).length);
  const subjects = $derived([...new Set<string>(candidates.map((c) => c.body.subject))]);
  const speakerNames = $derived(Array.from(new Set(segments.map((s) => s.speaker).filter(Boolean))) as string[]);
</script>

{#if meeting.isPending}
  <p role="status">{t.loading}</p>
{:else if meeting.isError || !m}
  <p role="alert">{String(meeting.error)}</p>
{:else}
  <section class="meeting-workspace">
    <div class="workspace-breadcrumb">
      <button class="textbutton" onclick={back}>← {t.back}</button><button
        class="workspace-options textbutton"
        onclick={() => (toolsOpen = !toolsOpen)}
        aria-expanded={toolsOpen}><Settings2 size={16} />{tr("Meeting options")}<ChevronDown size={14} /></button
      >
    </div>
    <div class="pageheading workspace-heading">
      <div>
        <h1>{m.title}</h1>
        <p>
          {m.date || tr("Date unknown")}
          {m.time} <span class="metadata-dot">·</span>
          {tr(m.classification)} <span class="metadata-dot">·</span>
          {tr("Local workspace")}
        </p>
      </div>
    </div>
    {#if error}<p class="error" role="alert">{error}</p>{/if}

    <MeetingFlow
      meeting={m}
      {t}
      {role}
      {busy}
      {act}
      {candidates}
      reviewRevision={review.data?.revision}
      device={profile.device}
      uploading={uploading ?? (intent?.kind === "upload" ? intent.file.name : null)}
      recording={recording || intent?.kind === "record"}
      {saving}
      record={() => (recording = true)}
      {recorded}
      file={upload}
      {openItem}
    />

    {#if toolsOpen}
      <div class="workspace-tools">
        {#if m.notes}<details class="card">
            <summary>{tr("Meeting notes · draft")}</summary>
            <p style="white-space:pre-wrap;line-height:1.7">{m.notes}</p>
          </details>{/if}
        <MeetingDetails meeting={m} {role} {busy} {act} {back} />
        <details class="card">
          <summary>{tr("Audio & processing")}</summary>
          <fieldset class="mutation-controls" disabled={role === "viewer"}>
            <div class="toolbar">
              <label
                >{tr("Inference device")}<select bind:value={profile.device}
                  ><option value="cuda">{tr("GPU")}</option><option value="cpu">{tr("CPU (explicit slower profile)")}</option></select
                ></label
              >
              {#each OPTIONAL as name (name)}
                <label
                  ><span
                    ><input
                      type="checkbox"
                      bind:checked={profile[name]}
                      disabled={!capabilities.data?.capabilities?.[name]?.available}
                    />{tr(name)}</span
                  ><small>{tr(capabilities.data?.capabilities?.[name]?.available ? "Available, not qualified" : "Assets or dependencies not prepared")}</small></label
                >
              {/each}
            </div>
            <div class="toolbar">
              <label class="filelabel"
                >{t.upload}<input
                  aria-label={t.upload}
                  type="file"
                  accept=".wav,.mp3,.m4a,.ogg,.flac,.webm"
                  disabled={busy}
                  onchange={(e) => {
                    const f = e.currentTarget.files?.[0];
                    if (f) void upload(f);
                  }}
                /></label
              >
              {#each m.assets ?? [] as a (a.id)}
                <span
                  >{(a.samples / a.sample_rate).toFixed(1)}{tr(" s saved ")}<button
                    disabled={busy}
                    onclick={() => act(() => api(`/meetings/${id}/jobs`, "POST", { asset_id: a.id, ...profile }))}>{t.process}</button
                  ></span
                >
              {/each}
            </div>
            {#each (m.recordings ?? []).filter((r) => r.state === "recording" && r.acknowledged_chunks > 0) as r (r.id)}
              <div class="notice">
                <strong>{tr("Recover saved recording")}</strong>
                <p>{(r.acknowledged_samples / r.rate).toFixed(1)}{tr(" seconds acknowledged. Unacknowledged audio from a closed browser cannot be recovered.")}</p>
                <button
                  disabled={busy}
                  onclick={() =>
                    act(() =>
                      api(`/recordings/${r.id}/finish`, "POST", {
                        count: r.acknowledged_chunks,
                        gaps: [{ reason: "Recovered after interruption; missing wall interval unknown" }],
                      }),
                    )}>{tr("Seal acknowledged audio")}</button
                >
              </div>
            {/each}
            <Recorder meeting={id} {t} done={(asset) => act(() => processNew(asset))} />
            {#each m.jobs ?? [] as j (j.id)}
              <div class="job" role="status">
                <strong>{tr(j.stage.replaceAll("_", " "))}</strong> · {tr(j.state)}<JobProgress job={j} />
                {#if j.error}<span class="error">{errorMessage(j.error)}{tr(" — source audio retained")}</span>{/if}
                {#if ["queued", "running"].includes(j.state)}
                  <button class="secondary" onclick={() => act(() => api(`/jobs/${j.id}/cancel`, "POST"))}>{tr("Cancel analysis")}</button>
                {:else if ["failed", "cancelled"].includes(j.state)}
                  <button onclick={() => act(() => api(`/jobs/${j.id}/retry`, "POST"))}>{tr("Retry")}</button>
                {/if}
              </div>
            {/each}
          </fieldset>
        </details>
        {#if m.transcript_pending_assets?.length}
          <section class="notice">
            <p>{tr("The transcript changed. Reanalyze it before creating new minutes.")}</p>
            {#each m.transcript_pending_assets as asset (asset)}
              <button
                disabled={busy || role === "viewer" || anyRunning}
                onclick={() => act(() => api(`/meetings/${id}/jobs`, "POST", { asset_id: asset, device: profile.device, transcript_only: true }))}
                >{tr("Reanalyze corrected transcript")}</button
              >
            {/each}
          </section>
        {/if}
        {#each latestJobs as j (j.id)}
          <AudioChecks
            jobId={j.id}
            running={["queued", "running"].includes(j.state)}
            {play}
            revision={m.revision}
            readOnly={role === "viewer"}
            disabled={busy || anyRunning}
          />
        {/each}
        {#if role !== "viewer" && m.assets?.length}
          <details class="card">
            <summary>{tr("Import supplied transcript")}</summary>
            <p>{tr("Upload timestamped speaker text. The original is preserved; audio verification remains separate.")}</p>
            <form onsubmit={importTranscript}>
              <label
                >{tr("Source audio")}<select name="asset"
                  >{#each m.assets as a (a.id)}<option value={a.id}>{(a.samples / a.sample_rate).toFixed(1)}s · {a.id.slice(0, 8)}</option>{/each}</select
                ></label
              ><label>{tr("Transcript file")}<input name="transcript" type="file" accept=".txt" required /></label><button disabled={busy || anyRunning}
                >{tr("Import supplied transcript")}</button
              >
            </form>
          </details>
        {/if}
      </div>
    {/if}

    {#if m.assets?.length}
      <div class="tabs" role="tablist">
        {#each TABS as k (k)}
          <button role="tab" aria-selected={tab === k} onclick={() => (tab = k)}>{t[k]}</button>
        {/each}
      </div>
      <MeetingAudio {audio} {segments} />
      {#if m.assets && m.assets.length > 1}
        <label class="asset-switch"
          >{tr("Recording")}<select value={audio.asset?.id} onchange={(e) => audio.seek(0, false, e.currentTarget.value)}
            >{#each m.assets as a, i (a.id)}<option value={a.id}>{tr("Recording")} {i + 1} · {timeLabel(a.samples / a.sample_rate)}</option>{/each}</select
          ></label
        >
      {/if}
      <div class="recording-metadata">
        <div class="speaker-key" aria-label={tr("Speaker key")}>
          {#each speakerNames as name (name)}<span style:color={speakerPalette[speakerIndex(name)]}><i style:background="currentColor"></i>{name}</span>{/each}
        </div>
        {#if segments.some((s) => s.raw.includes("user_supplied_transcript"))}<span>{tr("Imported transcript · approximate timestamps")}</span>{/if}
      </div>
      {#if tab !== "transcript" && m.transcript_pending_assets?.length}
        <p class="notice">{tr("Transcript updated. Review affected items before approving minutes.")}</p>
      {/if}

      {#if tab === "review"}
        <div class="review-toolbar">
          <div class="category-filters">
            {#each CATEGORIES as k (k)}
              <button
                aria-pressed={category === k}
                onclick={() => {
                  category = k;
                  selection = null;
                }}>{tr(k === "all" ? "All items" : k)} <span>{candidates.filter((c) => k === "all" || c.body.category === k).length}</span></button
              >
            {/each}
          </div>
          <input aria-label={tr("Find an action or decision")} placeholder={tr("Find an action or decision")} bind:value={search} />
        </div>
        <div class="reviewgrid">
          <section class="card itemlist">
            <h2>{tr("Decisions & actions")}</h2>
            <p class="caption">{openItems} {tr("to review")}</p>
            {#if !candidates.length}<p>{tr("No extracted events yet. Process saved audio to begin.")}</p>{/if}
            {#each visibleCandidates as c (c.id)}
              <button
                class={selected?.id === c.id ? "selected" : ""}
                onclick={() => {
                  selection = c.id;
                  field = "text";
                }}><strong>{c.body.subject}</strong><small>{tr(c.body.kind)} · {tr(c.review.replaceAll("_", " "))}</small></button
              >
            {/each}
          </section>
          <section class="card detail">
            {#if selected}
              <p class="eyebrow">{tr(selected.body.category)} · {tr(selected.body.kind)}</p>
              <h2>{selected.body.text}</h2>
              <p class="badge">{tr("Review: ")}{tr(selected.review.replaceAll("_", " "))}</p>
              {#each FIELDS as f (f)}
                <button class="field" onclick={() => (field = f)}
                  ><span>{tr(f)}</span><strong>{selected.body[f] || t.notSpecified}</strong><small>{tr("View source ↗")}</small></button
                >
              {/each}
              {#if selected.body.uncertainties.length > 0}<p class="caption">{tr("Processing warning (original wording)")}</p>{/if}
              {#each selected.body.uncertainties as u (u)}<p class="notice">{u}</p>{/each}
              <div class="toolbar">
                <button
                  disabled={busy ||
                    role === "viewer" ||
                    selected.review === "accepted" ||
                    !!m.transcript_pending_assets?.length ||
                    anyRunning ||
                    review.data?.revision !== m.revision}
                  onclick={() => act(() => api(`/review-issues/${selected.id}/resolve`, "POST", { revision: review.data.revision, action: "accepted" }))}
                  >{t.accept}</button
                ><button
                  class="secondary"
                  disabled={busy || role === "viewer" || selected.review === "excluded"}
                  onclick={() => act(() => api(`/review-issues/${selected.id}/resolve`, "POST", { revision: review.data.revision, action: "excluded" }))}
                  >{t.exclude}</button
                >
              </div>
              <p class="caption">{tr("Acceptance confirms your review of the interpretation, including each field.")}</p>
              {#if role !== "viewer"}
                {#key selected.id}
                  <CorrectionForm candidate={selected} revision={review.data.revision} {act} corrected={(next) => (selection = next)} {subjects} />
                {/key}
              {/if}
            {:else}
              <h2>{tr("Review the evidence before approving")}</h2>
            {/if}
          </section>
          <aside class="card evidence">
            <p class="eyebrow">{tr("SOURCE EVIDENCE · ")}{tr(field)}</p>
            {#each refs as r (r.id)}
              <div>
                <blockquote>{r.quote}</blockquote>
                <p>{tr("Transcript revision ")}{r.revision}</p>
                <button class="secondary" onclick={() => playEvidence(r)}>{tr("▶ Play source clip")}</button><button
                  class="textbutton source-jump"
                  onclick={() => void openTranscript(r)}>{tr("Open in transcript")} ↗</button
                >
              </div>
            {:else}
              <p>{tr("No source supplied for this field. Keep unsupported values unresolved.")}</p>
            {/each}
            <CandidateHistory id={selected?.id} />
          </aside>
        </div>
      {/if}

      {#if tab === "transcript"}
        {#if transcript.isPending}
          <p role="status">{t.loading}</p>
        {:else if transcript.isError}
          <p role="alert" class="error">{String(transcript.error)}</p>
        {:else}
          <TranscriptExperience
            {jumpId}
            {segments}
            activeId={audio.loaded ? active?.id : undefined}
            readOnly={role === "viewer"}
            {seek}
            save={saveTranscript}
            {busy}
          />
        {/if}
      {/if}

      {#if tab === "minutes"}
        <section class="card">
          <div class="pageheading">
            <div>
              <h2>{tr("Versioned minutes")}</h2>
              <p>{tr("Resolve every review item, then create an immutable preview.")}</p>
            </div>
            <button disabled={busy || role === "viewer"} onclick={() => act(() => api(`/meetings/${id}/snapshots`, "POST", { revision: m.revision }))}
              >{tr("Create preview")}</button
            >
          </div>
          {#each snapshots.data ?? [] as s (s.id)}
            <Snapshot snapshot={s} revision={m.revision} {t} groups={groups.data || []} {act} busy={busy || role === "viewer"} />
          {/each}
          {#if !snapshots.data?.length}<p>{tr("No versions yet. Approval and sending are separate steps.")}</p>{/if}
        </section>
      {/if}
    {/if}
  </section>
{/if}
