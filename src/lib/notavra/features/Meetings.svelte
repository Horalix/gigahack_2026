<script lang="ts">
  // Port of features/Meetings.tsx. The "New meeting" form is replaced by the
  // start panel: record or upload in one action, details optional.
  import { api, type Meeting } from "../api";
  import type { Labels } from "../i18n";
  import { createQuery } from "../query.svelte";
  import { tr } from "../translations.svelte";
  import type { Intent } from "./flow";
  import StartPanel from "./StartPanel.svelte";

  let { t, open, canCreate }: { canCreate: boolean; t: Labels; open: (id: string, intent?: Intent) => void } = $props();

  const query = createQuery({ key: () => ["meetings"], fn: () => api<Meeting[]>("/meetings") });
</script>

<div class="pageheading">
  <div>
    <p class="eyebrow">{tr("YOUR MEETING RECORD")}</p>
    <h1>{t.meetings}</h1>
    <p>{tr("From conversation to reviewed decisions.")}</p>
  </div>
</div>
{#if canCreate}<StartPanel {t} {open} />{/if}
{#if query.isPending}
  <p role="status">{t.loading}</p>
{:else if query.isError}
  <p role="alert">{String(query.error)}</p>
{:else if !query.data?.length}
  {#if !canCreate}
    <section class="card empty">
      <span class="emptyicon">▤</span>
      <h2>{tr("No meetings have been shared with you yet.")}</h2>
    </section>
  {/if}
{:else}
  <h2 class="list-heading">{tr("Recent meetings")}</h2>
  <div class="meetinglist">
    {#each query.data as m (m.id)}
      <button class="meetingrow" onclick={() => open(m.id)}
        ><span class="datebox">{m.date ? m.date.slice(8) : "—"}<small>{m.date ? m.date.slice(0, 7) : tr("Date unknown")}</small></span><span
          ><strong>{m.title}</strong><small>{tr(m.classification)} · {m.language.toUpperCase()}</small></span
        ><span class="badge">{tr(m.status.replaceAll("_", " "))}</span><span aria-hidden="true">→</span></button
      >
    {/each}
  </div>
{/if}
<div class="guidance">
  <h3>{tr("A record you can trace")}</h3>
  <p>{tr("Review the original speech, see where a decision changed, and approve an exact version before sending.")}</p>
</div>
