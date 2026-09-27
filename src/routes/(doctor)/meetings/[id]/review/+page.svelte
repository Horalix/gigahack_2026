<script lang="ts">
  import { page } from "$app/state";
  import LanguageBadge from "$lib/components/meetings/language-badge.svelte";
  import MeetingSteps from "$lib/components/meetings/meeting-steps.svelte";
  import { formatDateTime, formatMs, LANGUAGE_LABEL, MEETING_TYPE_LABEL } from "$lib/prototype/format";
  import { canUndo, editSegment, getMeeting, speakerLabel, undoLastEdit } from "$lib/prototype/store.svelte";
  import type { Language } from "$lib/prototype/types";

  const meeting = $derived(getMeeting(page.params.id ?? ""));
  // Evidence links land here as #seg-<id>. CSS :target does not update on
  // client-side navigation (pushState), so the highlight follows the URL hash.
  const targeted = $derived(page.url.hash.slice(1));

  type Filter = "all" | Language;
  let filter = $state<Filter>("all");
  let editingId = $state<string | null>(null);
  let draft = $state("");

  const counts = $derived.by(() => {
    const c: Record<string, number> = {};
    for (const s of meeting?.segments ?? []) c[s.language] = (c[s.language] ?? 0) + 1;
    return c;
  });
  const filters = $derived<Filter[]>(["all", ...(["ro", "ru", "en", "mul"] as Language[]).filter((l) => counts[l])]);
  const visible = $derived((meeting?.segments ?? []).filter((s) => filter === "all" || s.language === filter));
  const edits = $derived(meeting?.segments.filter((s) => s.origin === "human_edit").length ?? 0);
  const unknownSpeakers = $derived(
    Object.entries(meeting?.speakers ?? {})
      .filter(([, person]) => !person)
      .map(([cluster]) => cluster),
  );

  function startEdit(id: string, text: string) {
    editingId = id;
    draft = text;
  }
  function save() {
    if (meeting && editingId && draft.trim()) editSegment(meeting.id, editingId, draft.trim());
    editingId = null;
  }
  function onEditorKey(event: KeyboardEvent) {
    if (event.key === "Escape") editingId = null;
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) save();
  }
</script>

<svelte:head><title>Transcript · {meeting?.title ?? "Meeting"} · Secure MOM</title></svelte:head>

<div class="page">
  {#if !meeting}
    <div class="card empty"><h1>Meeting not found</h1><p>This meeting does not exist or you do not have access.</p></div>
  {:else if meeting.job.stage !== "complete"}
    <MeetingSteps {meeting} current="transcript" />
    <div class="notice attention">
      <span>The transcript is not ready yet.</span>
      <a class="btn btn-sm" href="/meetings/{meeting.id}">See progress</a>
    </div>
  {:else}
    <MeetingSteps {meeting} current="transcript" />

    <div class="page-head">
      <div>
        <h1>Transcript</h1>
        <p class="muted meta">
          {meeting.title} · {MEETING_TYPE_LABEL[meeting.meetingType]} · {formatDateTime(meeting.recordedAt)}
          · revision {meeting.transcriptRevision}
          {#if edits}· {edits} edited{/if}
        </p>
      </div>
      <div class="actions">
        <button class="btn" disabled={!canUndo(meeting.id)} onclick={() => undoLastEdit(meeting.id)}>↶ Undo last edit</button>
        <a class="btn btn-primary" href="/meetings/{meeting.id}/minutes">Continue to minutes →</a>
      </div>
    </div>

    <div class="toolbar">
      <div class="segmented" role="group" aria-label="Filter by language">
        {#each filters as f (f)}
          <button aria-pressed={filter === f} onclick={() => (filter = f)}>
            {f === "all" ? "All" : LANGUAGE_LABEL[f]}
            <span class="count">{f === "all" ? meeting.segments.length : counts[f]}</span>
          </button>
        {/each}
      </div>
      <span class="subtle">Original language is kept as spoken. Nothing is translated.</span>
    </div>

    {#if unknownSpeakers.length}
      <div class="notice attention">
        <span>
          {unknownSpeakers.length} speaker{unknownSpeakers.length === 1 ? " was" : "s were"} not identified. Their words stay in the
          transcript, but they cannot be named as owners.
        </span>
      </div>
    {/if}

    <ol class="segments">
      {#each visible as seg (seg.id)}
        {@const speaker = speakerLabel(meeting, seg.speakerClusterId)}
        <li id="seg-{seg.id}" class:editing={editingId === seg.id} class:targeted={targeted === `seg-${seg.id}`}>
          <span class="time mono">{formatMs(seg.startMs)}</span>
          <div class="body">
            <div class="who">
              <span class:unknown={!speaker.known}>{speaker.name}</span>
              <LanguageBadge language={seg.language} />
              {#if seg.origin === "human_edit"}<span class="chip tone-accent">edited</span>{/if}
            </div>
            {#if editingId === seg.id}
              <!-- svelte-ignore a11y_autofocus -->
              <textarea bind:value={draft} onkeydown={onEditorKey} autofocus aria-label="Edit segment text"></textarea>
              <div class="actions">
                <button class="btn btn-sm btn-primary" onclick={save}>Save</button>
                <button class="btn btn-sm" onclick={() => (editingId = null)}>Cancel</button>
                <span class="subtle">Ctrl+Enter to save · Esc to cancel</span>
              </div>
            {:else}
              <p class="text">{seg.text}</p>
            {/if}
          </div>
          {#if editingId !== seg.id}
            <button class="btn btn-sm btn-ghost edit" onclick={() => startEdit(seg.id, seg.text)} aria-label="Edit segment at {formatMs(seg.startMs)}">
              Edit
            </button>
          {/if}
        </li>
      {:else}
        <li class="empty">No segments in this language.</li>
      {/each}
    </ol>
  {/if}
</div>

<style>
  .toolbar {
    display: flex;
    align-items: center;
    gap: 16px;
    flex-wrap: wrap;
  }
  .count {
    margin-left: 6px;
    opacity: 0.6;
    font-size: 0.8em;
  }
  .segments {
    list-style: none;
    margin: 0;
    padding: 0;
    border: 1px solid var(--borderColor-default);
    border-radius: var(--radius-default);
    background: var(--bgColor-raised);
  }
  .segments li {
    display: grid;
    grid-template-columns: 56px 1fr auto;
    gap: 14px;
    padding: 12px 16px;
    align-items: start;
    scroll-margin-top: 80px;
  }
  .segments li + li {
    border-top: 1px solid var(--borderColor-muted);
  }
  .segments li.targeted {
    background: var(--bgColor-attention-muted);
    box-shadow: inset 3px 0 0 var(--fgColor-attention);
  }
  .segments li.editing {
    background: var(--bgColor-muted);
  }
  .time {
    color: var(--fgColor-subtle);
    padding-top: 2px;
  }
  .body {
    display: flex;
    flex-direction: column;
    gap: 6px;
    min-width: 0;
  }
  .who {
    display: flex;
    gap: 8px;
    align-items: center;
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--fgColor-muted);
  }
  .unknown {
    color: var(--fgColor-attention);
    font-style: italic;
  }
  .text {
    line-height: 1.6;
  }
  .edit {
    opacity: 0;
  }
  .segments li:hover .edit,
  .edit:focus-visible {
    opacity: 1;
  }
</style>
