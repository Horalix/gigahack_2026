<script lang="ts">
  // Port of features/Meetings.tsx.
  import { focusOnMount } from "../actions";
  import { api, type Meeting } from "../api";
  import type { Labels } from "../i18n";
  import { createQuery, invalidateQueries } from "../query.svelte";
  import { tr } from "../translations.svelte";

  let { t, open, canCreate }: { canCreate: boolean; t: Labels; open: (id: string) => void } = $props();

  let creating = $state(false);
  let error = $state("");
  let busy = $state(false);
  const query = createQuery({ key: () => ["meetings"], fn: () => api<Meeting[]>("/meetings") });

  async function create(e: SubmitEvent) {
    e.preventDefault();
    busy = true;
    error = "";
    const f = new FormData(e.currentTarget as HTMLFormElement);
    try {
      const m = await api<Meeting>("/meetings", "POST", {
        title: f.get("title"),
        date: f.get("date") || null,
        language: f.get("language"),
        timezone: f.get("timezone"),
        classification: f.get("classification"),
        participants: String(f.get("participants")).split("\n").filter(Boolean),
      });
      await invalidateQueries();
      open(m.id);
    } catch (failure) {
      error = failure instanceof Error ? failure.message : tr("The request failed. Check the form, refresh, and try again.");
    } finally {
      busy = false;
    }
  }
</script>

<div class="pageheading">
  <div>
    <p class="eyebrow">{tr("YOUR MEETING RECORD")}</p>
    <h1>{t.meetings}</h1>
    <p>{tr("From conversation to reviewed decisions.")}</p>
  </div>
  {#if canCreate}<button onclick={() => (creating = !creating)}>＋ {t.new}</button>{/if}
</div>
{#if error}<p role="alert" class="error">{error}</p>{/if}
{#if creating}
  <form class="card form" onsubmit={create}>
    <h2>{t.new}</h2>
    <label>{t.title}<input name="title" required maxlength="200" use:focusOnMount /></label>
    <div class="formrow">
      <label>{t.date}<input name="date" type="date" value="" /></label>
      <label>{tr("Timezone")}<input name="timezone" value="" /></label>
    </div>
    <p class="caption">{tr("Leave date and timezone blank if unknown. Relative dates will need review.")}</p>
    <div class="formrow">
      <label
        >{tr("Minutes language")}<select name="language"
          ><option value="en">English</option><option value="ro">Română</option><option value="ru">Русский</option></select
        ></label
      >
      <label
        >{tr("Classification")}<select name="classification"
          ><option value="Administrative">{tr("Administrative")}</option><option value="Executive">{tr("Executive")}</option><option value="Medical"
            >{tr("Medical")}</option
          ></select
        ></label
      >
    </div>
    <label>{t.participants}<textarea name="participants" rows="3"></textarea></label>
    <button disabled={busy}>{busy ? t.loading : t.save}</button>
  </form>
{/if}
{#if query.isPending}
  <p role="status">{t.loading}</p>
{:else if query.isError}
  <p role="alert">{String(query.error)}</p>
{:else if !query.data?.length}
  <section class="card empty">
    <span class="emptyicon">▤</span>
    <h2>{canCreate ? t.empty : tr("No meetings have been shared with you yet.")}</h2>
    {#if canCreate}
      <p>{tr("Create a meeting, add your participants, then record or upload audio.")}<br />{tr("Every decision stays connected to its source.")}</p>
      <button onclick={() => (creating = true)}>{t.new}</button>
    {/if}
  </section>
{:else}
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
