<script module lang="ts">
  import { api } from "../api";
  import type { SpeechSegment } from "./transcriptModel";

  export async function loadTranscript(id: string, signal?: AbortSignal) {
    const result: SpeechSegment[] = [];
    for (let offset = 0; ; offset += 200) {
      signal?.throwIfAborted();
      const page = await api<SpeechSegment[]>(`/meetings/${id}/transcript?limit=200&offset=${offset}`);
      result.push(...page);
      if (page.length < 200) break;
    }
    return result;
  }
</script>

<script lang="ts">
  // Port of TranscriptExperience from features/TranscriptExperience.tsx: the
  // whole transcript loaded once, searched in the browser, 80 passages a page.
  import { ArrowLeft, ArrowRight, Search, X } from "@lucide/svelte";
  import { tr } from "../translations.svelte";
  import Utterance from "./Utterance.svelte";

  let {
    segments,
    activeId,
    jumpId,
    readOnly,
    seek,
    save,
    busy,
  }: {
    jumpId?: string;
    segments: SpeechSegment[];
    activeId?: string;
    readOnly: boolean;
    seek: (s: SpeechSegment) => void;
    save: (s: SpeechSegment, text: string, speaker: string | null) => Promise<void>;
    busy: boolean;
  } = $props();

  let search = $state("");
  let page = $state(0);
  let follow = $state(false);

  const filtered = $derived(segments.filter((s) => !search || s.text.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase())));
  const pages = $derived(Math.ceil(filtered.length / 80));
  const safePage = $derived(Math.min(page, Math.max(0, pages - 1)));
  const visible = $derived(filtered.slice(safePage * 80, (safePage + 1) * 80));
  const speakers = $derived(Array.from(new Set(segments.map((s) => s.speaker).filter((s): s is string => !!s))));

  // The four effects mirror the original's useEffect dependency lists.
  $effect(() => {
    // [jumpId, segments]
    const id = jumpId,
      list = segments;
    if (id) {
      search = "";
      const index = list.findIndex((s) => s.id === id);
      if (index >= 0) page = Math.floor(index / 80);
    }
  });
  $effect(() => {
    // [jumpId, safePage]
    const id = jumpId;
    safePage;
    if (id) document.getElementById("utterance-" + id)?.scrollIntoView({ block: "center", behavior: "smooth" });
  });
  $effect(() => {
    // [follow, activeId, segments, search]
    const on = follow,
      id = activeId,
      list = segments,
      query = search;
    if (on && id && !query) {
      const index = list.findIndex((s) => s.id === id);
      if (index >= 0) page = Math.floor(index / 80);
    }
  });
  $effect(() => {
    // [follow, activeId, safePage, search]
    const on = follow,
      id = activeId,
      query = search;
    safePage;
    if (on && id && !query) document.getElementById("utterance-" + id)?.scrollIntoView({ block: "center", behavior: "smooth" });
  });
</script>

<section class="transcript-document" aria-label={tr("Transcript")}>
  <div class="transcript-tools">
    <div class="transcript-search">
      <Search size={17} /><input
        aria-label={tr("Search transcript")}
        placeholder={tr("Search transcript")}
        value={search}
        oninput={(e) => {
          search = e.currentTarget.value;
          page = 0;
        }}
      />{#if search}<button class="icon-button" aria-label={tr("Clear search")} onclick={() => (search = "")}><X size={15} /></button>{/if}
    </div>
    <label class="follow-control"><input type="checkbox" bind:checked={follow} />{tr("Follow audio")}</label>
  </div>
  {#if search}<p class="search-count" role="status">{filtered.length} {tr("matching passages")}</p>{/if}
  <div class="conversation">
    {#each visible as s (s.id)}
      <Utterance segment={s} active={s.id === activeId} query={search.trim()} {readOnly} {seek} {save} {speakers} {busy} />
    {/each}
  </div>
  {#if !filtered.length}<p class="empty-transcript">{tr(search ? "No matching passages." : "No transcript available.")}</p>{/if}
  {#if pages > 1}
    <nav class="transcript-pagination" aria-label={tr("Transcript navigation")}>
      <button class="textbutton" disabled={!safePage} onclick={() => (page = safePage - 1)}><ArrowLeft size={16} />{tr("Earlier conversation")}</button><span
        >{safePage + 1} / {pages}</span
      ><button class="textbutton" disabled={safePage + 1 >= pages} onclick={() => (page = safePage + 1)}>{tr("Continue reading")}<ArrowRight size={16} /></button>
    </nav>
  {/if}
</section>
