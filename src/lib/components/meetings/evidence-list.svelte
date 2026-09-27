<script lang="ts">
  import { formatMs } from "$lib/prototype/format";
  import type { Evidence } from "$lib/prototype/types";

  type Props = { meetingId: string; evidence: Evidence[] };
  let { meetingId, evidence }: Props = $props();
</script>

{#if evidence.length}
  <ul class="evidence">
    {#each evidence as item (item.segmentId + item.quote)}
      <li>
        <a class="stamp mono" href="/meetings/{meetingId}/review#seg-{item.segmentId}" title="Open this moment in the transcript">
          {formatMs(item.startMs)}
        </a>
        <q>{item.quote}</q>
      </li>
    {/each}
  </ul>
{/if}

<style>
  .evidence {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  li {
    display: flex;
    gap: 10px;
    align-items: baseline;
    font-size: 0.9rem;
    color: var(--fgColor-muted);
  }
  .stamp {
    flex: none;
    text-decoration: none;
    padding: 0 6px;
    border-radius: 4px;
    background: var(--bgColor-inset);
  }
  q {
    font-style: italic;
  }
</style>
