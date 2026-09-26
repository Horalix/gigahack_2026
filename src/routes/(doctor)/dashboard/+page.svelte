<script lang="ts">
  import { goto } from "$app/navigation";
  import StatusChip from "$lib/components/meetings/status-chip.svelte";
  import { formatDateTime, meetingHref, meetingStatus, MEETING_TYPE_LABEL } from "$lib/prototype/format";
  import { db, searchPatients, type PatientPage } from "$lib/prototype/store.svelte";

  const PAGE_SIZE = 25;

  let query = $state("");
  let offset = $state(0);
  let result = $state<PatientPage | null>(null);
  let loading = $state(true);
  let activeIndex = $state(-1);
  let latestRequest = 0;

  // Debounced search. Responses that arrive after a newer request started are
  // dropped, so a slow early reply cannot overwrite a newer result.
  $effect(() => {
    const q = query;
    const at = offset;
    loading = true;
    const request = ++latestRequest;
    const timer = setTimeout(async () => {
      const page = await searchPatients(q, at, PAGE_SIZE);
      if (request !== latestRequest) return;
      result = page;
      loading = false;
      activeIndex = -1;
    }, 250);
    return () => clearTimeout(timer);
  });

  function onQuery(value: string) {
    query = value;
    offset = 0; // a new search starts from the first page
  }

  function onKeydown(event: KeyboardEvent) {
    const items = result?.items ?? [];
    if (!items.length) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      activeIndex = Math.min(activeIndex + 1, items.length - 1);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      activeIndex = Math.max(activeIndex - 1, 0);
    } else if (event.key === "Enter" && activeIndex >= 0) {
      event.preventDefault();
      goto(`/patients/${items[activeIndex].id}`);
    }
  }

  const recent = $derived(
    [...db.meetings].sort((a, b) => Date.parse(b.recordedAt) - Date.parse(a.recordedAt)).slice(0, 8),
  );
  const needsReview = $derived(db.meetings.filter((m) => m.status === "needs_review" && !m.delivery).length);
</script>

<svelte:head><title>Dashboard · Secure MOM</title></svelte:head>

<div class="page">
  <div class="page-head">
    <div>
      <h1>Dashboard</h1>
      <p class="muted meta">
        {#if needsReview}
          {needsReview} meeting{needsReview === 1 ? "" : "s"} waiting for your review.
        {:else}
          Nothing waiting for review.
        {/if}
      </p>
    </div>
    <div class="actions">
      <a class="btn" href="/meetings/new?mode=upload">⤒ Upload recording</a>
      <a class="btn btn-primary" href="/meetings/new?mode=record">● Record meeting</a>
    </div>
  </div>

  <div class="grid-2">
    <section class="card" aria-labelledby="patients-title">
      <div class="card-head">
        <h2 id="patients-title">Patients</h2>
        <span class="subtle">Fictional demo data</span>
      </div>

      <input
        type="search"
        placeholder="Search by name or reference (e.g. turcanu, MP-2026-0007, Иван)"
        aria-label="Search patients"
        aria-controls="patient-results"
        value={query}
        oninput={(e) => onQuery(e.currentTarget.value)}
        onkeydown={onKeydown}
      />

      <p class="subtle" aria-live="polite">
        {#if loading}
          Searching…
        {:else if result && result.total === 0}
          No patients match “{query}”.
        {:else if result}
          {result.offset + 1}–{result.offset + result.items.length} of {result.total}
          {query ? "matching" : ""} · ↑↓ to move, Enter to open
        {/if}
      </p>

      <ul class="list" id="patient-results" class:stale={loading}>
        {#each result?.items ?? [] as patient, i (patient.id)}
          <li>
            <a class="row-link" class:active={i === activeIndex} href="/patients/{patient.id}">
              <span>{patient.displayName}</span>
              <span class="subtle mono">{patient.reference ?? "no reference"}</span>
            </a>
          </li>
        {/each}
      </ul>

      {#if result && result.total > PAGE_SIZE}
        <div class="actions pager">
          <button class="btn btn-sm" disabled={offset === 0 || loading} onclick={() => (offset = Math.max(0, offset - PAGE_SIZE))}>
            ← Previous
          </button>
          <button class="btn btn-sm" disabled={!result.hasMore || loading} onclick={() => (offset += PAGE_SIZE)}>
            Next →
          </button>
        </div>
      {/if}
    </section>

    <section class="card" aria-labelledby="meetings-title">
      <div class="card-head">
        <h2 id="meetings-title">Recent meetings</h2>
      </div>
      <ul class="list">
        {#each recent as meeting (meeting.id)}
          {@const status = meetingStatus(meeting)}
          <li>
            <a class="row-link" href={meetingHref(meeting)}>
              <span class="meeting">
                <span class="title">{meeting.title}</span>
                <span class="subtle">{MEETING_TYPE_LABEL[meeting.meetingType]} · {formatDateTime(meeting.recordedAt)}</span>
              </span>
              <StatusChip {...status} />
            </a>
          </li>
        {:else}
          <li class="empty">No meetings yet.</li>
        {/each}
      </ul>
    </section>
  </div>
</div>

<style>
  .stale {
    opacity: 0.55;
    transition: opacity 0.15s;
  }
  .pager {
    justify-content: flex-end;
  }
  .meeting {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }
  .title {
    font-weight: 500;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
</style>
