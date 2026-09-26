<script lang="ts">
  import { goto } from "$app/navigation";
  import { page } from "$app/state";
  import EvidenceList from "$lib/components/meetings/evidence-list.svelte";
  import MeetingSteps from "$lib/components/meetings/meeting-steps.svelte";
  import StatusChip from "$lib/components/meetings/status-chip.svelte";
  import { groupFor, participants } from "$lib/prototype/fixtures";
  import { formatDateTime, formatDay, MEETING_TYPE_LABEL } from "$lib/prototype/format";
  import { assignOwner, getMeeting, participantName, regenerateMinutes, sendMinutes, setDueDate } from "$lib/prototype/store.svelte";
  import type { Action } from "$lib/prototype/types";

  const meeting = $derived(getMeeting(page.params.id ?? ""));
  const adopted = $derived(meeting?.actions.filter((a) => a.status === "confirmed" || a.status === "unresolved") ?? []);
  const unresolved = $derived(adopted.filter((a) => a.status === "unresolved"));
  const proposed = $derived(meeting?.actions.filter((a) => a.status === "proposed") ?? []);
  const rejected = $derived(meeting?.actions.filter((a) => a.status === "rejected") ?? []);
  const group = $derived(meeting ? groupFor(meeting.meetingType) : null);
  const locked = $derived(!!meeting?.delivery);
  const openCount = $derived(unresolved.length + proposed.length);

  let editingItem = $state<string | null>(null);
  let confirming = $state(false);

  function missing(a: Action): string {
    const noOwner = a.kind === "action" && !a.ownerParticipantId;
    const noDate = !a.dueAt;
    if (noOwner && noDate) return "Needs owner and date";
    if (noOwner) return "Needs owner";
    if (noDate) return "Needs date";
    return "Needs review";
  }

  function requestSend() {
    if (!meeting || meeting.minutesStale || locked) return;
    if (openCount > 0 && !confirming) {
      confirming = true;
      return;
    }
    sendMinutes(meeting.id);
    goto(`/meetings/${meeting.id}/sent`);
  }
</script>

<svelte:head><title>Minutes · {meeting?.title ?? "Meeting"} · Secure MOM</title></svelte:head>

<div class="page">
  {#if !meeting || !group}
    <div class="card empty"><h1>Meeting not found</h1><p>This meeting does not exist or you do not have access.</p></div>
  {:else if meeting.job.stage !== "complete"}
    <MeetingSteps {meeting} current="minutes" />
    <div class="notice attention">
      <span>The minutes are not ready yet.</span>
      <a class="btn btn-sm" href="/meetings/{meeting.id}">See progress</a>
    </div>
  {:else}
    <MeetingSteps {meeting} current="minutes" />

    <div class="page-head">
      <div>
        <h1>Minutes</h1>
        <p class="muted meta">{meeting.title} · {MEETING_TYPE_LABEL[meeting.meetingType]} · {formatDateTime(meeting.recordedAt)}</p>
      </div>
      <div class="actions">
        <a class="btn" href="/meetings/{meeting.id}/review">← Transcript</a>
        {#if locked}
          <a class="btn btn-primary" href="/meetings/{meeting.id}/sent">View delivery</a>
        {:else}
          <button class="btn btn-primary" disabled={meeting.minutesStale} onclick={requestSend}>Approve and send</button>
        {/if}
      </div>
    </div>

    {#if meeting.minutesStale && !locked}
      <div class="notice attention" role="status">
        <span>The transcript was edited after these minutes were drafted. Regenerate them so they match what was said.</span>
        <button class="btn btn-sm" onclick={() => regenerateMinutes(meeting.id)}>Regenerate minutes</button>
      </div>
    {/if}

    {#if locked && meeting.delivery}
      <div class="notice success">
        <span>Sent to {group.label} on {formatDateTime(meeting.delivery.sentAt)}. This version can no longer be changed; a correction would go out as a new version.</span>
      </div>
    {/if}

    {#if confirming && !locked}
      <div class="notice attention" role="alertdialog" aria-labelledby="confirm-title">
        <div>
          <strong id="confirm-title">{openCount} item{openCount === 1 ? " is" : "s are"} still open</strong>
          <p>They will be sent marked as unresolved, not guessed. You can also resolve them below first.</p>
        </div>
        <div class="actions">
          <button class="btn" onclick={() => (confirming = false)}>Keep reviewing</button>
          <button class="btn btn-primary" onclick={requestSend}>Send with open items</button>
        </div>
      </div>
    {/if}

    <section class="card" aria-labelledby="summary-title">
      <h2 id="summary-title">Summary</h2>
      <p class="summary">{meeting.summary}</p>
    </section>

    <section class="card" aria-labelledby="actions-title">
      <div class="card-head">
        <h2 id="actions-title">Decisions and actions</h2>
        <span class="subtle">{adopted.length - unresolved.length} of {adopted.length} complete</span>
      </div>

      <ol class="items">
        {#each adopted as a (a.id)}
          {@const owner = participantName(a.ownerParticipantId)}
          {@const editing = !locked && (editingItem === a.id || a.status === "unresolved")}
          <li id="item-{a.id}" class:open={a.status === "unresolved"}>
            <div class="item-head">
              <span class="chip tone-neutral">{a.kind === "decision" ? "Decision" : "Action"}</span>
              {#if a.status === "confirmed"}
                <StatusChip label="Complete" tone="success" />
              {:else}
                <StatusChip label={missing(a)} tone="attention" />
              {/if}
              {#if a.resolvedByReviewer}<span class="chip tone-accent">set by reviewer</span>{/if}
              {#if !locked && a.status === "confirmed"}
                <button class="btn btn-sm btn-ghost edit" onclick={() => (editingItem = editingItem === a.id ? null : a.id)}>
                  {editingItem === a.id ? "Done" : "Edit"}
                </button>
              {/if}
            </div>

            <p class="item-text">{a.text}</p>
            <EvidenceList meetingId={meeting.id} evidence={a.taskEvidence} />

            <dl class="facts">
              {#if a.kind === "action"}
                <dt>Owner</dt>
                <dd>
                  {#if owner}<strong>{owner}</strong>{:else}<span class="missing">Not stated in the meeting</span>{/if}
                  {#if editing}
                    <select
                      aria-label="Owner for: {a.text}"
                      value={a.ownerParticipantId ?? ""}
                      onchange={(e) => assignOwner(meeting.id, a.id, e.currentTarget.value || null)}
                    >
                      <option value="">{owner ? "Clear owner" : "Assign an owner…"}</option>
                      {#each participants as p (p.id)}
                        <option value={p.id}>{p.displayName} · {p.role}</option>
                      {/each}
                    </select>
                  {/if}
                  <EvidenceList meetingId={meeting.id} evidence={a.ownerEvidence} />
                </dd>
              {/if}

              <dt>{a.kind === "decision" ? "From" : "Due"}</dt>
              <dd>
                {#if a.dueAt}<strong>{formatDay(a.dueAt)}</strong>{:else}<span class="missing">No date given</span>{/if}
                {#if a.originalDateExpression && !a.dateEvidence.length}<span class="subtle">said “{a.originalDateExpression}”</span>{/if}
                {#if editing}
                  <input
                    type="date"
                    aria-label="Date for: {a.text}"
                    value={a.dueAt ?? ""}
                    onchange={(e) => setDueDate(meeting.id, a.id, e.currentTarget.value || null)}
                  />
                {/if}
                <EvidenceList meetingId={meeting.id} evidence={a.dateEvidence} />
              </dd>
            </dl>
          </li>
        {:else}
          <li class="empty">No decisions or actions were found in this meeting.</li>
        {/each}
      </ol>
    </section>

    {#if proposed.length || unresolved.length}
      <section class="card" aria-labelledby="clarify-title">
        <h2 id="clarify-title">Needs clarification</h2>
        <ul class="plain">
          {#each unresolved as a (a.id)}
            <li><a href="#item-{a.id}">{a.text}</a> <span class="subtle">· {missing(a).replace("Needs ", "missing ")}</span></li>
          {/each}
          {#each proposed as a (a.id)}
            <li>
              Mentioned but not agreed: {a.text}
              <EvidenceList meetingId={meeting.id} evidence={a.taskEvidence} />
            </li>
          {/each}
        </ul>
      </section>
    {/if}

    {#if rejected.length}
      <section class="card" aria-labelledby="rejected-title">
        <div class="card-head">
          <h2 id="rejected-title">Not adopted</h2>
          <span class="subtle">Proposed, then explicitly rejected. Never listed as an action.</span>
        </div>
        <ul class="plain">
          {#each rejected as a (a.id)}
            <li>
              <s>{a.text}</s>
              <EvidenceList meetingId={meeting.id} evidence={a.taskEvidence} />
            </li>
          {/each}
        </ul>
      </section>
    {/if}

    <section class="card" aria-labelledby="recipients-title">
      <div class="card-head">
        <h2 id="recipients-title">Recipients</h2>
        <span class="subtle">{group.label} · from configuration, never from the recording</span>
      </div>
      <ul class="plain recipients">
        {#each group.to as r (r.address)}<li>{r.name} <span class="subtle mono">{r.address}</span></li>{/each}
        {#each group.cc as r (r.address)}<li>{r.name} <span class="subtle mono">{r.address}</span> <span class="chip tone-neutral">cc</span></li>{/each}
      </ul>
    </section>
  {/if}
</div>

<style>
  .summary {
    line-height: 1.65;
  }
  .items {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .items > li {
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding: 14px;
    border-radius: var(--radius-default);
    background: var(--bgColor-inset);
    border: 1px solid transparent;
    scroll-margin-top: 80px;
  }
  .items > li.open {
    border-color: color-mix(in oklch, var(--fgColor-attention) 45%, transparent);
  }
  .item-head {
    display: flex;
    gap: 8px;
    align-items: center;
    flex-wrap: wrap;
  }
  .edit {
    margin-left: auto;
  }
  .item-text {
    font-weight: 600;
    font-size: 1.02rem;
  }
  .facts {
    display: grid;
    grid-template-columns: 70px 1fr;
    gap: 8px 12px;
    margin: 0;
  }
  dt {
    color: var(--fgColor-subtle);
    font-size: 0.875rem;
    padding-top: 2px;
  }
  dd {
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 6px;
    align-items: flex-start;
  }
  dd select,
  dd input {
    max-width: 320px;
  }
  .missing {
    color: var(--fgColor-attention);
    font-style: italic;
  }
  .plain {
    margin: 0;
    padding-left: 20px;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .recipients {
    list-style: none;
    padding-left: 0;
    gap: 6px;
  }
</style>
