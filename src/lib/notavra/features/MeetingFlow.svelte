<script lang="ts">
  // The whole path from audio to email in one card: where the meeting is,
  // how long each part took, and the one thing (if any) that needs a person.
  // The happy path after processing is a single "Approve & send"; everything
  // else here is an exception with its fix next to it.
  import { Check, CircleAlert, FileText, LoaderCircle, Send } from "@lucide/svelte";
  import { errorMessage } from "../errors";
  import { api, DEMO_BACKEND, snapshotExportUrl, type Job, type Meeting } from "../api";
  import type { Labels } from "../i18n";
  import { createQuery, type Query } from "../query.svelte";
  import { tr, ui } from "../translations.svelte";
  import AudioStart from "./AudioStart.svelte";
  import {
    clearToAccept,
    duration,
    finishedAt,
    isActive,
    latestJobs,
    needsAttention,
    observeDelivery,
    readableDay,
  } from "./flow";
  import Recorder from "./Recorder.svelte";
  import { timeLabel } from "./transcriptModel";

  let {
    meeting: m,
    t,
    role,
    busy,
    act,
    candidates,
    reviewRevision,
    device,
    uploading,
    recording,
    saving,
    record,
    recorded,
    file,
    openItem,
  }: {
    meeting: Meeting;
    t: Labels;
    role: string;
    busy: boolean;
    act: (fn: () => Promise<unknown>) => Promise<void>;
    candidates: any[];
    reviewRevision: number | undefined;
    device: string;
    uploading: string | null;
    recording: boolean;
    saving: boolean;
    record: () => void;
    recorded: (asset?: { id: string }) => void;
    file: (f: File) => void;
    openItem: (id: string) => void;
  } = $props();

  const PHASES: Record<string, string> = {
    loading_model: "Loading local model",
    transcribing: "Transcribing audio",
    extracting: "Reading transcript",
    checking: "Checking evidence and changes",
    diarizing: "Separating speakers",
    stage_complete: "Stage complete",
  };
  const CATEGORY_HEADINGS: [string, string][] = [
    ["decision", "Decisions"],
    ["action", "Actions"],
    ["information", "Information"],
  ];

  const canEdit = $derived(role !== "viewer");

  // Live clock for the running timers.
  let now = $state(Date.now() / 1000);
  $effect(() => {
    const timer = setInterval(() => (now = Date.now() / 1000), 1000);
    return () => clearInterval(timer);
  });

  const templates = createQuery({ key: () => ["templates"], fn: () => api<any[]>("/settings/templates") });
  const groups = createQuery({ key: () => ["groups"], fn: () => api<any[]>("/recipient-groups") });
  const snapshots = createQuery({ key: () => ["snapshots", m.id], fn: () => api<any[]>(`/meetings/${m.id}/snapshots`) });
  const newest = $derived(snapshots.data?.[0]);
  const current = $derived(snapshots.data?.find((s) => s.revision === m.revision));
  const deliveries: Query<any[]> = createQuery({
    key: () => ["delivery", newest?.id],
    fn: () => api<any[]>(`/snapshots/${newest!.id}/deliveries`),
    enabled: () => !!newest,
    interval: (): number | false => (deliveries.data?.some((d: any) => d.state === "queued") ? 1000 : false),
  });
  const delivery = $derived(deliveries.data?.[0]);
  const sentAt = $derived(delivery ? observeDelivery(delivery) : undefined);

  const group = $derived.by(() => {
    const template = templates.data?.find((x) => x.classification === m.classification);
    return groups.data?.find((g) => g.id === (current?.suggested_group_id ?? template?.recipient_group_id));
  });

  const jobs = $derived(latestJobs(m.jobs));
  const job = $derived(jobs.latest);
  const attention = $derived(candidates.filter(needsAttention));
  const clear = $derived(candidates.filter(clearToAccept));
  const willSend = $derived(candidates.filter((c) => c.review === "accepted" || clearToAccept(c)));
  const leftOut = $derived(candidates.filter((c) => c.review === "excluded"));
  const pendingAssets = $derived(m.transcript_pending_assets ?? []);

  type Phase = "empty" | "recording" | "uploading" | "processing" | "reanalyze" | "stopped" | "unprocessed" | "sending" | "sent" | "failed" | "uncertain" | "ready";
  const deliveryForCurrent = $derived(newest && newest.revision === m.revision ? delivery : undefined);
  const phase = $derived.by((): Phase => {
    if (recording) return "recording";
    if (uploading || saving) return "uploading";
    if (!m.assets?.length) return "empty";
    if (isActive(job)) return "processing";
    if (pendingAssets.length) return "reanalyze";
    if (job && ["failed", "cancelled"].includes(job.state)) return "stopped";
    if (!job) return "unprocessed";
    if (deliveryForCurrent?.state === "queued") return "sending";
    if (deliveryForCurrent?.state === "sent") return "sent";
    if (deliveryForCurrent?.state === "failed") return "failed";
    if (deliveryForCurrent?.state === "uncertain") return "uncertain";
    return "ready";
  });

  // --- Timing: service timestamps, plus the observed send time -------------------
  const started = $derived(jobs.full?.created);
  const processed = $derived(finishedAt(job));
  const approvedAt = $derived(deliveryForCurrent ? current?.created : undefined);
  const timing = $derived.by(() => {
    if (!started) return "";
    const lang = ui.lang;
    if (phase === "processing") return `${tr("Processing for")} ${duration(now - started, lang)}`;
    if (phase === "sent" && sentAt && approvedAt && processed) {
      return `${tr("Processing start → email")}: ${duration(sentAt - started, lang)} · ${tr("processing")} ${duration(processed - started, lang)} · ${tr("your review")} ${duration(Math.max(0, approvedAt - processed), lang)} · ${tr("delivery")} ${duration(sentAt - approvedAt, lang)}`;
    }
    if (processed && ["ready", "sending", "sent"].includes(phase)) {
      const done = `${tr("Processed in")} ${duration(processed - started, lang)}`;
      return phase === "ready" ? `${done} · ${tr("waiting for approval")} ${duration(now - processed, lang)}` : done;
    }
    return "";
  });

  // --- Steps ------------------------------------------------------------------------
  type StepState = "todo" | "active" | "done" | "attention" | "failed";
  const onTranscribing = (j?: Job) => !!j && !j.transcript_only && (j.stage === "whisper" || ["loading_model", "transcribing"].includes(j.progress?.phase ?? ""));
  const steps = $derived.by((): { label: string; state: StepState; detail: string }[] => {
    const audio: StepState = phase === "recording" || phase === "uploading" ? "active" : m.assets?.length ? "done" : "todo";
    const asset = m.assets?.[m.assets.length - 1];
    let transcript: StepState = "todo",
      decisions: StepState = "todo",
      approval: StepState = "todo",
      email: StepState = "todo";
    if (job && ["processing", "stopped"].includes(phase)) {
      const early = onTranscribing(job);
      const s: StepState = phase === "processing" ? "active" : "failed";
      transcript = early ? s : "done";
      decisions = early ? "todo" : s;
    } else if (job) {
      transcript = "done";
      decisions = phase === "reanalyze" ? "attention" : "done";
      approval = phase === "ready" ? (attention.length ? "attention" : "active") : phase === "reanalyze" ? "todo" : "done";
      email = phase === "sending" ? "active" : phase === "sent" ? "done" : ["failed", "uncertain"].includes(phase) ? "failed" : "todo";
    }
    const running = phase === "processing" && job?.progress ? tr(PHASES[job.progress.phase] ?? "") : phase === "processing" ? tr("Waiting for the local worker") : "";
    return [
      {
        label: tr("Audio"),
        state: audio,
        detail: phase === "recording" ? tr("Recording") : phase === "uploading" ? tr(saving ? "Saving" : "Uploading") : asset ? timeLabel(asset.samples / asset.sample_rate) : tr("Record or upload"),
      },
      { label: tr("Transcript"), state: transcript, detail: transcript === "active" ? running : transcript === "done" ? tr("Done") : transcript === "failed" ? tr("Stopped") : "" },
      {
        label: tr("Decisions & actions"),
        state: decisions,
        detail:
          decisions === "active" ? running : decisions === "attention" ? tr("Transcript changed") : decisions === "done" ? `${tr("Found")}: ${candidates.length}` : decisions === "failed" ? tr("Stopped") : "",
      },
      {
        label: tr("Your approval"),
        state: approval,
        detail: approval === "attention" ? `${tr("To check")}: ${attention.length}` : approval === "active" ? tr("Ready") : approval === "done" ? tr("Approved") : "",
      },
      {
        label: tr("Email"),
        state: email,
        detail: email === "active" ? tr("Sending") : email === "done" ? tr("Sent") : email === "failed" ? tr("Not confirmed") : "",
      },
    ];
  });

  // --- The one action ---------------------------------------------------------------
  let sendingStep = $state<string | null>(null);
  const blocked = $derived(
    !canEdit
      ? ""
      : !candidates.length
        ? "No decisions or actions were found, so there are no minutes to send."
        : attention.length
          ? "Resolve the items above first."
          : !group && templates.data && groups.data
            ? "No recipient group is set for this meeting type. An admin can choose one in Templates."
            : "",
  );
  const stale = $derived(reviewRevision !== m.revision);

  async function approveAndSend() {
    const revision = m.revision,
      target = group;
    if (!target) return;
    await act(async () => {
      sendingStep = "Approving items";
      for (const c of clear) await api(`/review-issues/${c.id}/resolve`, "POST", { revision, action: "accepted" });
      let snapshot = current;
      if (!snapshot) {
        sendingStep = "Creating the minutes";
        snapshot = await api<{ id: string; approved?: boolean }>(`/meetings/${m.id}/snapshots`, "POST", { revision });
      }
      if (!snapshot!.approved) {
        sendingStep = "Approving the minutes";
        await api(`/snapshots/${snapshot!.id}/approve`, "POST", { revision });
      }
      sendingStep = "Sending";
      const queued = await api<{ id: string; state: string }>(`/snapshots/${snapshot!.id}/deliveries`, "POST", {
        group_id: target.id,
        group_version: target.version,
        explicitly_send_older: false,
      });
      observeDelivery(queued);
    });
    sendingStep = null;
  }

  const resolve = (c: any, action: "accepted" | "excluded") =>
    act(() => api(`/review-issues/${c.id}/resolve`, "POST", { revision: reviewRevision, action }));
  const recipients = (d: any): string[] => JSON.parse(d?.addresses || "[]");
  const clock = (seconds?: number) => (seconds ? new Date(seconds * 1000).toTimeString().slice(0, 5) : "");
</script>

{#snippet stepIcon(state: StepState, index: number)}
  <span class="flow-dot" aria-hidden="true"
    >{#if state === "done"}<Check size={14} strokeWidth={3} />{:else if state === "active"}<LoaderCircle
        size={14}
        strokeWidth={3}
        class="spin"
      />{:else if state === "attention" || state === "failed"}<CircleAlert size={14} strokeWidth={2.5} />{:else}{index + 1}{/if}</span
  >
{/snippet}

{#snippet itemLine(c: any)}
  <li>
    <span>{c.body.text}</span>
    {#if c.body.category === "action"}<small
        >{tr("Owner")}: {c.body.owner || t.notSpecified} · {tr("Due")}: {c.body.due || t.notSpecified}{c.body.condition ? ` · ${c.body.condition}` : ""}</small
      >{/if}
  </li>
{/snippet}

<section class="flow card" aria-label={tr("Progress")}>
  <ol class="flow-steps">
    {#each steps as step, i (i)}
      <li class={`flow-step is-${step.state}`} aria-current={step.state === "active" || step.state === "attention" ? "step" : undefined}>
        {@render stepIcon(step.state, i)}<span class="flow-label">{step.label}<small>{step.detail}</small></span>
      </li>
    {/each}
  </ol>

  <div class="flow-body">
    {#if phase === "empty"}
      {#if canEdit}
        <h2>{tr("Add the meeting audio")}</h2>
        <AudioStart {record} {file} {busy} />
      {:else}
        <p>{tr("No audio has been added to this meeting yet.")}</p>
      {/if}
    {:else if phase === "recording"}
      <Recorder meeting={m.id} {t} done={recorded} hero autostart />
    {:else if phase === "uploading"}
      <p class="flow-status"><LoaderCircle size={18} class="spin" />{saving ? tr("Saving the recording…") : `${tr("Uploading")} ${uploading}…`}</p>
      <progress class="flow-progress" aria-label={tr(saving ? "Saving" : "Uploading")}></progress>
    {:else if phase === "processing" && job}
      <div class="flow-status-row">
        <p class="flow-status"><LoaderCircle size={18} class="spin" />{tr(job.progress ? (PHASES[job.progress.phase] ?? "") : "Waiting for the local worker")}</p>
        {#if canEdit}<button class="textbutton" disabled={busy} onclick={() => act(() => api(`/jobs/${job.id}/cancel`, "POST"))}>{tr("Cancel analysis")}</button>{/if}
      </div>
      <progress
        class="flow-progress"
        aria-label={tr("Current step progress")}
        max={job.progress?.total ?? 1}
        value={job.progress?.total == null ? undefined : job.progress.completed}
      ></progress>
      <p class="caption">
        {#if job.progress?.eta_seconds != null && job.progress.eta_seconds > now - job.progress.updated_at}
          {tr("About")} {duration(job.progress.eta_seconds - (now - job.progress.updated_at), ui.lang)} {tr("left in this step.")}
        {/if}
        {tr("Nothing to do here: the minutes will be ready for approval when this finishes.")}
      </p>
    {:else if phase === "reanalyze"}
      <p class="notice">{tr("The transcript changed. Reanalyze it before creating new minutes.")}</p>
      {#if canEdit}
        <div class="toolbar">
          {#each pendingAssets as asset (asset)}
            <button disabled={busy} onclick={() => act(() => api(`/meetings/${m.id}/jobs`, "POST", { asset_id: asset, device, transcript_only: true }))}
              >{tr("Reanalyze corrected transcript")}</button
            >
          {/each}
        </div>
      {/if}
    {:else if phase === "stopped" && job}
      <p class="error">{job.state === "cancelled" ? tr("Processing was cancelled.") : errorMessage(job.error ?? "")}{tr(" — source audio retained")}</p>
      {#if canEdit}<button disabled={busy} onclick={() => act(() => api(`/jobs/${job.id}/retry`, "POST"))}>{tr("Process again")}</button>{/if}
    {:else if phase === "unprocessed"}
      <p>{tr("The audio is saved but has not been processed.")}</p>
      {#if canEdit}
        <button disabled={busy} onclick={() => act(() => api(`/meetings/${m.id}/jobs`, "POST", { asset_id: m.assets![m.assets!.length - 1].id, device }))}
          >{t.process}</button
        >
      {/if}
    {:else if phase === "ready" && reviewRevision === undefined}
      <p role="status">{t.loading}</p>
    {:else if phase === "ready"}
      <div class="ready-head">
        <div>
          <h2>{tr("Minutes are ready to approve")}</h2>
          <p>
            {CATEGORY_HEADINGS.map(([category, heading]) => `${tr(heading)}: ${candidates.filter((c) => c.body.category === category).length}`).join(" · ")}.
            {attention.length ? `${tr("Need your attention")}: ${attention.length}.` : tr("Nothing needs your attention.")}
          </p>
        </div>
        {#if canEdit}
          <div class="approve-box">
            <button class="approve-send" disabled={busy || !!blocked || stale || !group} onclick={approveAndSend}
              >{#if sendingStep}<LoaderCircle size={18} class="spin" />{tr(sendingStep)}…{:else}<Send size={18} />{tr("Approve & send")}{/if}</button
            >
            {#if blocked}<small>{tr(blocked)}</small>{/if}
          </div>
        {/if}
      </div>
      {#if newest && newest.revision !== m.revision && delivery?.state === "sent"}
        <p class="notice">{tr("The meeting changed after the last email. Approve & send emails the updated minutes.")}</p>
      {/if}
      {#if attention.length}
        <div class="attention">
          <h3>{tr("Needs your attention")}</h3>
          {#each attention as c (c.id)}
            <article class="attention-item">
              <div>
                <strong>{c.body.subject}</strong>
                <p>{c.body.text}</p>
                {#each c.body.uncertainties as u (u)}<p class="attention-reason"><CircleAlert size={14} />{u}</p>{/each}
              </div>
              {#if canEdit}
                <div class="attention-actions">
                  <button class="secondary" disabled={busy || stale} onclick={() => resolve(c, "accepted")}>{t.accept}</button><button
                    class="textbutton"
                    disabled={busy || stale}
                    onclick={() => resolve(c, "excluded")}>{t.exclude}</button
                  ><button class="textbutton" onclick={() => openItem(c.id)}>{tr("Edit")}</button>
                </div>
              {/if}
            </article>
          {/each}
        </div>
      {/if}
      <div class="send-preview">
        <h3>{tr("What will be sent")}</h3>
        {#each CATEGORY_HEADINGS as [category, heading] (category)}
          {@const list = willSend.filter((c) => c.body.category === category)}
          {#if list.length}
            <h4>{tr(heading)}</h4>
            <ul>
              {#each list as c (c.id)}{@render itemLine(c)}{/each}
            </ul>
          {/if}
        {/each}
        {#if !willSend.length}<p class="caption">{tr("No items will be included yet.")}</p>{/if}
        {#if leftOut.length}<p class="caption">{tr("Excluded")}: {leftOut.map((c) => c.body.subject).join(", ")}</p>{/if}
        <p class="send-meta">
          {#if group}{tr("To")} <strong>{group.name}</strong>: {group.addresses.join(", ")}{/if}
          {#if m.date}<br />{tr("Relative deadlines are counted from the meeting date")}: {readableDay(m.date, ui.lang)}{/if}
        </p>
      </div>
    {:else if phase === "sending"}
      <p class="flow-status"><LoaderCircle size={18} class="spin" />{tr("Sending to the local mail server…")}</p>
    {:else if phase === "sent" && deliveryForCurrent}
      <div class="sent">
        <span class="sent-icon" aria-hidden="true"><Check size={22} strokeWidth={3} /></span>
        <div>
          <h2>{tr("Minutes emailed")}</h2>
          <p>{tr("To")}: {recipients(deliveryForCurrent).join(", ")}{sentAt ? ` · ${clock(sentAt)}` : ""}</p>
          <div class="toolbar sent-links">
            {#each ["html", "pdf"] as f (f)}<a target="_blank" rel="noreferrer" href={snapshotExportUrl(deliveryForCurrent.snapshot_id, f)}
                ><FileText size={16} />{tr(f === "html" ? "Open minutes" : "PDF")}</a
              >{/each}
          </div>
          {#if DEMO_BACKEND}<p class="caption">{tr("Demo backend: no email actually left this browser.")}</p>{/if}
        </div>
      </div>
    {:else if phase === "failed" && deliveryForCurrent}
      <p class="error">{tr("Delivery failed.")} {errorMessage(deliveryForCurrent.error ?? "")}</p>
      {#if canEdit}<button disabled={busy} onclick={() => act(() => api(`/deliveries/${deliveryForCurrent.id}/retry`, "POST", { explicitly_send_older: false }))}
          >{tr("Retry this failed delivery")}</button
        >{/if}
    {:else if phase === "uncertain"}
      <p class="notice">{tr("Delivery is uncertain. Check the mail server; this attempt cannot be retried automatically.")}</p>
    {/if}
  </div>

  {#if timing}<p class="flow-timing">{timing}</p>{/if}
</section>
