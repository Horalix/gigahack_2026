<script lang="ts">
  // Port of features/JobProgress.tsx.
  import type { Job } from "../api";
  import { tr } from "../translations.svelte";

  let { job }: { job: Job } = $props();

  const phases = {
    loading_model: "Loading local model",
    transcribing: "Transcribing audio",
    extracting: "Reading transcript",
    checking: "Checking evidence and changes",
    diarizing: "Separating speakers",
    stage_complete: "Stage complete",
  };

  const p = $derived(job.progress);
  const running = $derived(job.state === "running");
  const age = $derived(p ? Math.max(0, Date.now() / 1000 - p.updated_at) : 0);
  const elapsed = $derived(p ? Math.floor(p.elapsed_seconds + (running ? age : 0)) : 0);
  const eta = $derived(p && running && p.eta_seconds != null && p.eta_seconds > age ? Math.ceil((p.eta_seconds - age) / 60) : null);
</script>

{#if job.state === "complete"}
  <p class="caption">{tr("Analysis saved. Ready for review.")}</p>
{:else if !p && !["queued", "running"].includes(job.state)}
  <p class="caption">{tr("Processing stopped. The last observed progress is retained.")}</p>
{:else if !p}
  <div class="job-progress">
    <progress aria-label={tr("Analysis progress")}></progress><small
      >{tr(job.state === "queued" ? "Waiting for the local worker" : "Waiting for a progress update")}</small
    >
  </div>
{:else}
  <div class="job-progress">
    <div class="progress-heading">
      <strong>{tr(phases[p.phase])}</strong><span>{tr("Elapsed")}: {Math.floor(elapsed / 60)}:{String(elapsed % 60).padStart(2, "0")}</span>
    </div>
    <progress aria-label={tr("Current step progress")} max={p.total ?? 1} value={p.total == null ? undefined : p.completed}></progress>
    <small>{p.total != null ? `${Math.floor(p.completed)} / ${Math.ceil(p.total)} ${tr(p.unit)}` : tr("Preparing local processing")}</small>
    {#if running}<small>{eta != null ? `${tr("Estimated remaining in this step")}: ~${eta} ${tr("min")}` : tr("Estimating remaining time…")}</small>{/if}
    {#if running}<small>{tr("Estimates cover this step. Later steps and human review are not included.")}</small>{/if}
    {#if !running}<small>{tr("Processing stopped. The last observed progress is retained.")}</small>{/if}
  </div>
{/if}
