<script lang="ts">
  // Port of Utterance (and MarkedText) from features/TranscriptExperience.tsx.
  import { History, MoreHorizontal, Pencil, Play, X } from "@lucide/svelte";
  import { api } from "../api";
  import { createQuery } from "../query.svelte";
  import { tr } from "../translations.svelte";
  import { speakerIndex, speakerInk, speakerPalette, timeLabel, type SpeechSegment } from "./transcriptModel";

  let {
    segment: s,
    active,
    query,
    readOnly,
    seek,
    save,
    speakers,
    busy,
  }: {
    segment: SpeechSegment;
    active: boolean;
    query: string;
    readOnly: boolean;
    seek: (s: SpeechSegment) => void;
    save: (s: SpeechSegment, text: string, speaker: string | null) => Promise<void>;
    speakers: string[];
    busy: boolean;
  } = $props();

  // Captured once when the passage mounts, like the useState initialisers it replaces.
  const initial = () => ({ text: s.text, speaker: s.speaker || "" });
  let editing = $state(false);
  let text = $state(initial().text);
  let speaker = $state(initial().speaker);
  let history = $state(false);
  let error = $state("");
  let menu: HTMLDetailsElement | undefined = $state();
  let editor: HTMLTextAreaElement | undefined = $state();
  const index = $derived(speakerIndex(s.speaker));

  const revisions = createQuery({
    key: () => ["segment-history", s.id, s.revision],
    fn: () => api<any[]>(`/segments/${s.id}/history`),
    enabled: () => history,
  });
  const raw = $derived(JSON.parse(s.raw || "{}"));
  const alternatives = $derived(JSON.parse(s.alternatives || "[]") as { engine: string; text: string }[]);

  function begin() {
    text = s.text;
    speaker = s.speaker || "";
    error = "";
    editing = true;
    if (menu) menu.open = false;
  }

  async function commit() {
    if (!text.trim() || busy) return;
    try {
      await save(s, text, speaker.trim() || null);
      editing = false;
    } catch (e) {
      error = String(e);
    }
  }

  $effect(() => {
    if (editing) editor?.focus();
  });

  function keydown(e: KeyboardEvent) {
    if (e.key === "Escape") {
      editing = false;
      e.stopPropagation();
    }
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      void commit();
    }
  }

  /** MarkedText: the passage split around case-insensitive matches of the search. */
  function marked(value: string, needle: string): { text: string; mark: boolean }[] {
    if (!needle) return [{ text: value, mark: false }];
    const parts: { text: string; mark: boolean }[] = [];
    const lower = value.toLocaleLowerCase(),
      find = needle.toLocaleLowerCase();
    let start = 0,
      at = lower.indexOf(find);
    while (at >= 0) {
      parts.push({ text: value.slice(start, at), mark: false }, { text: value.slice(at, at + needle.length), mark: true });
      start = at + needle.length;
      at = lower.indexOf(find, start);
    }
    parts.push({ text: value.slice(start), mark: false });
    return parts;
  }
</script>

<article
  id={"utterance-" + s.id}
  class={`utterance ${active ? "is-active" : ""}`}
  style:--speaker={speakerPalette[index]}
  style:--speaker-ink={speakerInk[index]}
  aria-current={active ? "true" : undefined}
>
  <div class="speaker-line">
    <span class="speaker-dot"></span><span class="speaker-name">{s.speaker || tr("Unknown speaker")}</span><button
      class="utterance-time"
      aria-label={`${tr("Play from")} ${timeLabel(s.start / 16000)}`}
      onclick={() => seek(s)}>{timeLabel(s.start / 16000)}</button
    >
  </div>
  {#if !editing}
    <div class="utterance-controls">
      <button class="icon-button" aria-label={tr("Play passage")} onclick={() => seek(s)}><Play size={15} /></button>{#if !readOnly}<button
          class="icon-button"
          aria-label={tr("Edit transcript")}
          onclick={begin}><Pencil size={15} /></button
        >{/if}<details class="utterance-menu" bind:this={menu}>
        <summary aria-label={tr("Passage options")}><MoreHorizontal size={18} /></summary>
        <div class="context-menu">
          {#if !readOnly}<button onclick={begin}><Pencil size={14} />{tr("Edit transcript / speaker")}</button>{/if}<button
            onclick={() => {
              history = !history;
              if (menu) menu.open = false;
            }}><History size={14} />{tr("History & source")}</button
          >
        </div>
      </details>
    </div>
  {/if}
  {#if editing}
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div class="utterance-editor" onkeydown={keydown}>
      <textarea
        bind:this={editor}
        aria-label={tr("Transcript text")}
        bind:value={text}
        maxlength="10000"
        rows={Math.max(3, Math.min(10, Math.ceil(text.length / 85)))}
      ></textarea>
      <div class="edit-footer">
        <label>{tr("Speaker")}<input aria-label={tr("Speaker")} list={"speakers-" + s.id} bind:value={speaker} maxlength="200" /></label><datalist
          id={"speakers-" + s.id}>{#each speakers as name (name)}<option value={name}></option>{/each}</datalist
        >
        <div>
          <button class="textbutton" onclick={() => (editing = false)} disabled={busy}>{tr("Cancel")}</button><button
            onclick={() => void commit()}
            disabled={busy || !text.trim()}>{tr("Save")}</button
          >
        </div>
      </div>
      {#if error}<p role="alert" class="error">{error}</p>{/if}
    </div>
  {:else}
    <!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_noninteractive_element_interactions -->
    <p class="utterance-text" onclick={() => seek(s)}>{#each marked(s.text, query) as part, i (i)}{#if part.mark}<mark>{part.text}</mark>{:else}{part.text}{/if}{/each}</p>
  {/if}
  {#if history}
    <div class="source-history">
      <div class="toolbar">
        <strong>{tr("History & source")}</strong><button class="icon-button" aria-label={tr("Close history")} onclick={() => (history = false)}><X size={16} /></button>
      </div>
      <p>{tr("Revision")} {s.revision} · {tr(raw.origin === "user_supplied_transcript" ? "Imported transcript · approximate timestamps" : "Original transcript")}</p>
      {#if raw.boundary_review}<p>{tr("Check this passage against the audio.")}</p>{/if}
      {#if raw.supplied_language_labels?.length > 0}<p>{tr("Unverified language labels")}: {raw.supplied_language_labels.join(", ")}</p>{/if}
      {#if revisions.isError}<p role="alert">{String(revisions.error)}</p>{/if}
      {#each revisions.data ?? [] as r (r.revision)}
        <div><small>{tr("Revision")} {r.revision}</small><p>{r.text}</p></div>
      {/each}
      {#if revisions.data?.length === 0}<small>{tr("No earlier revisions.")}</small>{/if}
      {#each alternatives as a, i (i)}
        <details>
          <summary>{tr("Alternative hypothesis · ")}{a.engine}</summary>
          <p>{a.text || tr("The second recognizer returned no text here.")}</p>
        </details>
      {/each}
    </div>
  {/if}
</article>
