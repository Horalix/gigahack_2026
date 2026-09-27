<script lang="ts">
  // The two ways to give Notavra a meeting: record it now, or hand over a
  // recording (click or drop). Either one starts the whole flow.
  import { Mic, Upload } from "@lucide/svelte";
  import { tr } from "../translations.svelte";

  let { record, file, busy = false }: { record: () => void; file: (f: File) => void; busy?: boolean } = $props();

  const ACCEPT = ".wav,.mp3,.m4a,.ogg,.flac,.webm";
  let dragging = $state(false);

  function drop(e: DragEvent) {
    e.preventDefault();
    dragging = false;
    const f = e.dataTransfer?.files?.[0];
    if (f && !busy) file(f);
  }
</script>

<div class="audio-start">
  <button class="start-option start-record" onclick={record} disabled={busy}>
    <span class="start-icon" aria-hidden="true"><Mic size={24} /></span>
    <span class="start-text"><strong>{tr("Record the meeting")}</strong><small>{tr("Starts right away. Minutes are drafted when you stop.")}</small></span>
  </button>
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <label
    class="start-option start-upload"
    class:dragging
    class:disabled={busy}
    ondragover={(e) => {
      e.preventDefault();
      dragging = true;
    }}
    ondragleave={() => (dragging = false)}
    ondrop={drop}
  >
    <input
      class="sr-only"
      type="file"
      accept={ACCEPT}
      aria-label={tr("Upload a recording")}
      disabled={busy}
      onchange={(e) => {
        const f = e.currentTarget.files?.[0];
        e.currentTarget.value = "";
        if (f) file(f);
      }}
    />
    <span class="start-icon" aria-hidden="true"><Upload size={24} /></span>
    <span class="start-text"
      ><strong>{tr("Upload a recording")}</strong><small>{tr("Drop a file here or choose one. WAV, MP3, M4A, OGG, FLAC or WebM.")}</small></span
    >
  </label>
</div>
