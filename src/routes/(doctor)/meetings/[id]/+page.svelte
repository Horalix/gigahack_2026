<script lang="ts">
  import { page } from "$app/state";
  import MeetingSteps from "$lib/components/meetings/meeting-steps.svelte";
  import { formatBytes, formatDateTime, formatMs, MEETING_TYPE_LABEL } from "$lib/prototype/format";
  import { getMeeting, retryJob, STAGES, tickJob } from "$lib/prototype/store.svelte";

  const STEP_MS = 1500; // pace of the simulated pipeline

  const meeting = $derived(getMeeting(page.params.id ?? ""));
  const job = $derived(meeting?.job);
  const done = $derived(job?.stage === "complete");
  const failed = $derived(job?.state === "failed");
  const running = $derived(!!job && !done && !failed);
  const currentIndex = $derived(job ? STAGES.findIndex((s) => s.stage === job.stage) : -1);
  const openItems = $derived(meeting?.actions.filter((a) => a.status === "unresolved" || a.status === "proposed").length ?? 0);

  let elapsed = $state(0);

  $effect(() => {
    if (!running || !meeting) return;
    const id = meeting.id;
    const clock = setInterval(() => (elapsed += 100), 100);
    const step = setInterval(() => {
      if (tickJob(id)) clearInterval(step);
    }, STEP_MS);
    return () => {
      clearInterval(clock);
      clearInterval(step);
    };
  });

  function skipAhead() {
    if (!meeting) return;
    while (!tickJob(meeting.id));
  }

  // Plain-language explanations for error codes, instead of showing raw codes.
  const ERRORS: Record<string, string> = {
    AUDIO_TRACK_MISSING: "The file has no audio track we could read. If it is a video, check that it was recorded with sound.",
    MODEL_NOT_READY: "The speech model is not installed on this computer yet.",
  };
</script>

<svelte:head><title>{meeting?.title ?? "Meeting"} · Secure MOM</title></svelte:head>

<div class="page">
  {#if !meeting || !job}
    <div class="card empty"><h1>Meeting not found</h1><p>This meeting does not exist or you do not have access.</p></div>
  {:else}
    <MeetingSteps {meeting} current="processing" />

    <div class="page-head">
      <div>
        <h1>{meeting.title}</h1>
        <p class="muted meta">
          {MEETING_TYPE_LABEL[meeting.meetingType]} · {formatDateTime(meeting.recordedAt)}
          {#if meeting.source}
            · {meeting.source.kind === "upload" ? meeting.source.label : "Live recording"}
            {#if meeting.source.sizeBytes}({formatBytes(meeting.source.sizeBytes)}){/if}
          {/if}
        </p>
      </div>
    </div>

    {#if failed}
      <div class="notice danger" role="alert">
        <div>
          <strong>Processing stopped</strong>
          <p>{ERRORS[job.errorCode ?? ""] ?? "Something went wrong while processing this recording."}</p>
          <p class="subtle mono">Code {job.errorCode ?? "UNKNOWN"} · the original recording is kept, nothing was lost.</p>
        </div>
        <div class="actions">
          <a class="btn" href="/dashboard">Back to dashboard</a>
          <button class="btn btn-primary" onclick={() => { elapsed = 0; retryJob(meeting.id); }}>Try again</button>
        </div>
      </div>
    {/if}

    {#if done}
      <div class="notice success">
        <div>
          <strong>Transcript and draft minutes are ready</strong>
          <p>
            {#if openItems}
              {openItems} item{openItems === 1 ? " needs" : "s need"} your attention before sending.
            {:else}
              Everything was matched to evidence in the recording.
            {/if}
          </p>
        </div>
        <div class="actions">
          <a class="btn" href="/meetings/{meeting.id}/minutes">Go to minutes</a>
          <a class="btn btn-primary" href="/meetings/{meeting.id}/review">Review transcript →</a>
        </div>
      </div>
    {/if}

    {#if !failed}
      <section class="card" aria-labelledby="stages-title">
        <div class="card-head">
          <h2 id="stages-title">{done ? "Processing finished" : "Processing"}</h2>
          {#if running}
            <span class="subtle mono">{formatMs(elapsed)} elapsed</span>
          {/if}
        </div>

        <ol class="stages">
          {#each STAGES as stage, i (stage.stage)}
            {@const state = done || i < currentIndex ? "done" : i === currentIndex && job.state === "running" ? "current" : "pending"}
            <li class={state}>
              <span class="icon" aria-hidden="true">
                {#if state === "done"}✓{:else if state === "current"}<span class="spinner"></span>{:else}{i + 1}{/if}
              </span>
              <span>
                <strong>{stage.label}</strong>
                <span class="subtle">{stage.detail}</span>
              </span>
            </li>
          {/each}
        </ol>

        {#if running}
          <div class="foot">
            <span class="subtle">
              {job.state === "queued" ? "Waiting for the GPU…" : "Runs entirely on this computer. You can leave this page; it keeps going."}
            </span>
            <button class="btn btn-sm btn-ghost" onclick={skipAhead} title="Prototype shortcut">Skip ahead (prototype)</button>
          </div>
        {/if}
      </section>
    {/if}
  {/if}
</div>

<style>
  .stages {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 14px;
  }
  .stages li {
    display: flex;
    gap: 14px;
    align-items: flex-start;
  }
  .stages li > span:last-child {
    display: flex;
    flex-direction: column;
  }
  .pending {
    opacity: 0.5;
  }
  .icon {
    flex: none;
    display: inline-grid;
    place-items: center;
    width: 28px;
    height: 28px;
    border-radius: 50%;
    border: 1px solid var(--borderColor-emphasis);
    font-size: 0.85rem;
    font-weight: 700;
  }
  .done .icon {
    background: var(--bgColor-success-muted);
    border-color: transparent;
    color: var(--fgColor-success);
  }
  .current .icon {
    border-color: var(--borderColor-accent);
  }
  .spinner {
    width: 14px;
    height: 14px;
    border-radius: 50%;
    border: 2px solid var(--fgColor-accent);
    border-right-color: transparent;
    animation: spin 0.8s linear infinite;
  }
  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
  .foot {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
    border-top: 1px solid var(--borderColor-muted);
    padding-top: 12px;
  }
</style>
