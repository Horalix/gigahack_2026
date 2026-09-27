<script lang="ts">
  // Port of features/AudioChecks.tsx.
  import { api } from "../api";
  import { createQuery, invalidateQueries } from "../query.svelte";
  import { tr } from "../translations.svelte";

  type Recovery = { text: string; attempt: "initial" | "short_retry"; source_start: number; source_end: number };
  type Observation = {
    kind: "speech_without_transcript" | "empty_second_recognizer";
    start: number;
    end: number;
    hypotheses?: Recovery[];
    inserted_segment_id?: string | null;
  };
  type CheckPage = { asset_id: string; total: number; items: Observation[] };

  let {
    jobId,
    running,
    play,
    revision,
    readOnly = true,
    disabled = false,
  }: {
    jobId: string;
    running: boolean;
    play: (span: { asset_id: string; start: number; end: number }) => void;
    revision?: number;
    readOnly?: boolean;
    disabled?: boolean;
  } = $props();

  let offset = $state(0);
  let saving = $state(false);
  let error = $state("");

  const checks = createQuery({
    key: () => ["audio-checks", jobId, running, offset],
    fn: () => api<CheckPage>(`/jobs/${jobId}/audio-checks?offset=${offset}&limit=20`),
    interval: () => (running ? 3000 : false),
  });

  async function addWords(event: SubmitEvent, item: Observation) {
    event.preventDefault();
    const form = new FormData(event.currentTarget as HTMLFormElement);
    saving = true;
    error = "";
    try {
      await api(`/jobs/${jobId}/transcript-additions`, "POST", {
        revision,
        start: item.start,
        end: item.end,
        text: form.get("text"),
        speaker: form.get("speaker") || null,
        reason: form.get("reason"),
        reviewed: form.get("reviewed") === "on",
      });
      await invalidateQueries();
    } catch (failure) {
      error = failure instanceof Error ? failure.message : tr("The request failed. Check the form, refresh, and try again.");
    } finally {
      saving = false;
    }
  }
</script>

{#if checks.isError}
  <p role="alert">{tr("Audio checks could not be loaded.")} <button onclick={() => void checks.refetch()}>{tr("Retry")}</button></p>
{:else if checks.data?.total}
  {@const page = checks.data}
  <section class="notice" aria-label={tr("Audio passages to check")}>
    <details>
      <summary>{tr("Audio passages to check")} ({page.total})</summary>
      <p>{tr("These automated flags may be wrong. Compare any recovery hypothesis with the source before correcting the transcript.")}</p>
      <p>{tr("Flags come from the latest analysis of this recording. Transcript edits do not recalculate them.")}</p>
      {#if error}<p role="alert">{error}</p>{/if}
      <ul>
        {#each page.items as item (`${item.kind}-${item.start}-${item.end}`)}
          <li>
            <button onclick={() => play({ ...item, asset_id: page.asset_id })}
              >{tr("Play passage")} {(item.start / 16000).toFixed(1)}–{(item.end / 16000).toFixed(1)}s</button
            >{" "}
            <span>{tr(item.kind === "speech_without_transcript" ? "Possible speech outside the transcript." : "The second recognizer returned no text here.")}</span>
            {#each item.hypotheses ?? [] as hypothesis, index (index)}
              <details>
                <summary>{tr(hypothesis.attempt === "short_retry" ? "Recovery hypothesis · shorter retry" : "Recovery hypothesis · initial pass")}</summary>
                <p>{hypothesis.text || tr("The second recognizer returned no text here.")}</p>
                <p>{tr("This hypothesis includes surrounding context and may repeat nearby words. It has not been added to the transcript.")}</p>
                <button onclick={() => play({ asset_id: page.asset_id, start: hypothesis.source_start, end: hypothesis.source_end })}
                  >{tr("Play recovery context")} {(hypothesis.source_start / 16000).toFixed(1)}–{(hypothesis.source_end / 16000).toFixed(1)}s</button
                >
              </details>
            {/each}
            {#if item.inserted_segment_id}
              <p role="status">{tr("Reviewed words added to the transcript.")}</p>
            {:else if item.kind === "speech_without_transcript" && !readOnly}
              <details>
                <summary>{tr("Add reviewed words")}</summary>
                <p>
                  {tr("Enter only words you heard inside the flagged interval. Do not copy surrounding context. A new analysis is required before creating minutes.")}
                </p>
                <form onsubmit={(event) => addWords(event, item)}>
                  <fieldset disabled={saving || running || disabled || revision === undefined}>
                    <label>{tr("Corrected words for this interval")}<textarea name="text" required maxlength="10000"></textarea></label>
                    <label>{tr("Speaker (manual)")}<input name="speaker" maxlength="200" /></label>
                    <label>{tr("Reason for correction")}<input name="reason" required minlength="3" maxlength="1000" /></label>
                    <label><input name="reviewed" type="checkbox" required />{tr("I listened to this interval and checked these words.")}</label>
                    <button>{tr("Save reviewed words")}</button>
                  </fieldset>
                </form>
              </details>
            {/if}
          </li>
        {/each}
      </ul>
      <div class="toolbar">
        <button disabled={offset === 0} onclick={() => (offset = Math.max(0, offset - 20))}>{tr("Previous")}</button><button
          disabled={offset + 20 >= page.total}
          onclick={() => (offset += 20)}>{tr("Next")}</button
        >
      </div>
    </details>
  </section>
{/if}
