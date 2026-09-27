<script lang="ts">
  import { page } from "$app/state";
  import MeetingSteps from "$lib/components/meetings/meeting-steps.svelte";
  import { groupFor } from "$lib/prototype/fixtures";
  import { formatDateTime } from "$lib/prototype/format";
  import { getMeeting } from "$lib/prototype/store.svelte";

  const meeting = $derived(getMeeting(page.params.id ?? ""));
  const group = $derived(meeting ? groupFor(meeting.meetingType) : null);
  const open = $derived(meeting?.actions.filter((a) => a.status === "unresolved" || a.status === "proposed").length ?? 0);
</script>

<svelte:head><title>Sent · {meeting?.title ?? "Meeting"} · Secure MOM</title></svelte:head>

<div class="page">
  {#if !meeting || !group}
    <div class="card empty"><h1>Meeting not found</h1><p>This meeting does not exist or you do not have access.</p></div>
  {:else if !meeting.delivery}
    <MeetingSteps {meeting} current="sent" />
    <div class="notice attention">
      <span>These minutes have not been sent yet.</span>
      <a class="btn btn-sm btn-primary" href="/meetings/{meeting.id}/minutes">Review and send</a>
    </div>
  {:else}
    <MeetingSteps {meeting} current="sent" />

    <div class="hero card">
      <span class="tick" aria-hidden="true">✓</span>
      <h1>Minutes sent to {group.label}</h1>
      <p class="muted">
        {formatDateTime(meeting.delivery.sentAt)} · {group.to.length + group.cc.length} recipients
        {#if open}· {open} item{open === 1 ? "" : "s"} marked unresolved{/if}
      </p>
      <div class="actions">
        <a class="btn" href="/meetings/{meeting.id}/minutes">View minutes</a>
        <a class="btn" href="/dashboard">Back to dashboard</a>
        <a class="btn btn-primary" href="/meetings/new">New meeting</a>
      </div>
    </div>

    <div class="grid-2">
      <section class="card" aria-labelledby="who-title">
        <h2 id="who-title">Delivered to</h2>
        <ul class="list">
          {#each group.to as r (r.address)}
            <li class="row"><span>{r.name}</span><span class="subtle mono">{r.address}</span></li>
          {/each}
          {#each group.cc as r (r.address)}
            <li class="row"><span>{r.name} <span class="chip tone-neutral">cc</span></span><span class="subtle mono">{r.address}</span></li>
          {/each}
        </ul>
      </section>

      <section class="card" aria-labelledby="doc-title">
        <h2 id="doc-title">Document</h2>
        <dl class="kv">
          <dt>Format</dt>
          <dd>Self-contained HTML (UTF-8)</dd>
          <dt>Built from</dt>
          <dd>Transcript revision {meeting.delivery.snapshotRevision}</dd>
          <dt>Delivery</dt>
          <dd>Local mail server on this network</dd>
        </dl>
      </section>
    </div>

    <div class="notice attention">
      <span>
        <strong>Prototype:</strong> nothing was emailed. In the real app this step renders the minutes file and
        sends it over local SMTP, where it shows up in the
        <a href="http://127.0.0.1:8025" target="_blank" rel="noreferrer">Mailpit inbox</a>.
      </span>
    </div>
  {/if}
</div>

<style>
  .hero {
    align-items: center;
    text-align: center;
    padding: 32px 18px;
  }
  .tick {
    display: grid;
    place-items: center;
    width: 56px;
    height: 56px;
    border-radius: 50%;
    background: var(--bgColor-success-muted);
    color: var(--fgColor-success);
    font-size: 1.6rem;
    font-weight: 700;
  }
  .row {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    padding: 8px 4px;
  }
  .kv {
    display: grid;
    grid-template-columns: 110px 1fr;
    gap: 8px 12px;
    margin: 0;
  }
  dt {
    color: var(--fgColor-subtle);
  }
  dd {
    margin: 0;
  }
</style>
