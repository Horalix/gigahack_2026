<script lang="ts">
  // Port of CandidateHistory from features/MeetingDetails.tsx.
  import { api } from "../api";
  import { createQuery } from "../query.svelte";
  import { tr } from "../translations.svelte";

  let { id }: { id: string | undefined } = $props();

  const history = createQuery({
    key: () => ["candidate-history", id],
    fn: () => api<any[]>(`/items/${id}/history`),
    enabled: () => !!id,
    interval: 4000,
  });
</script>

<h3>{tr("Decision history")}</h3>
{#if history.isError}
  <p role="alert">{String(history.error)}</p>
{:else}
  {#each history.data ?? [] as row (row.id)}
    {@const body = JSON.parse(row.body)}
    {@const amendment = body.human_amendment}
    <article>
      <p><strong>{tr(body.kind)}</strong> · {tr(row.review.replaceAll("_", " "))}</p>
      <p>{body.text}</p>
      <p>{body.owner || "—"} · {body.due || "—"}</p>
      {#if body.condition}<p>{body.condition}</p>{/if}
      {#if body.value}<p>{body.value}</p>{/if}
      {#if amendment}
        <details>
          <summary>{tr("Secretary amendment")}</summary>
          <p>{amendment.reason}</p>
          <p>{tr("Changed fields")}: {amendment.fields.map(tr).join(", ")}</p>
          <p>{tr("Reviewer")}: {amendment.actor}</p>
          <time datetime={new Date(amendment.created * 1000).toISOString()}>{new Date(amendment.created * 1000).toLocaleString()}</time>
          {#each amendment.resolved_issues ?? [] as issue (issue)}<p>{issue}</p>{/each}
        </details>
      {/if}
    </article>
  {/each}
{/if}
