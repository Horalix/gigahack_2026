<script lang="ts">
  // Port of Other from main.tsx: the Actions page (and the system status view).
  import { api } from "./api";
  import type { Labels } from "./i18n";
  import { createQuery } from "./query.svelte";
  import { tr } from "./translations.svelte";

  let { page, t }: { page: string; t: Labels } = $props();

  const q = createQuery({ key: () => [page], fn: () => api<any>(page === "actions" ? "/actions" : "/system/proof") });
</script>

<p class="eyebrow">{tr("WORKSPACE")}</p>
<h1>{t[page as keyof Labels]}</h1>
{#if q.isPending}
  <p>{t.loading}</p>
{:else if q.isError}
  <p role="alert">{String(q.error)}</p>
{:else if page === "actions"}
  <section class="card">
    {#each q.data as i (i.meeting_id + i.subject)}
      <article class="segment">
        <div>
          <h3>{i.text}</h3>
          <p>{i.owner || t.notSpecified} · {i.due || t.notSpecified} · {tr(i.status)}</p>
          {#if i.condition}<p>{i.condition}</p>{/if}
        </div>
      </article>
    {:else}
      <p>{tr("No reviewed actions yet.")}</p>
    {/each}
  </section>
{:else if page === "templates"}
  <section class="card">
    <h2>{tr("Evidence-first minutes")}</h2>
    <p>
      {tr(
        "Administrative, Executive and Medical meetings use a deterministic document: participants, decisions, actions, conditions, unresolved matters and amendment history.",
      )}
    </p>
    <p>{tr("Output language is chosen separately for each meeting. Original speech remains unchanged.")}</p>
  </section>
{:else}
  <section class="card">
    <h2>{tr("Local processing status")}</h2>
    <dl>
      {#each Object.entries(q.data) as [key, value] (key)}
        <dt>{key.replaceAll("_", " ")}</dt>
        <dd>{typeof value === "object" ? JSON.stringify(value) : String(value)}</dd>
      {/each}
    </dl>
    <p class="notice">{tr("Network observation is not measured. Local inference is not proof of host-wide isolation.")}</p>
    <a href="http://127.0.0.1:8025" target="_blank" rel="noreferrer">{tr("Open local Mailpit inbox ↗")}</a>
  </section>
{/if}
