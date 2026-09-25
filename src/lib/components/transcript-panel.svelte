<script lang="ts">
  import { onMount } from "svelte";
  import type {
    TranscriptSettings,
    TranscriptSessionSummary,
    TranscriptExportFormat,
  } from "$lib/domain/transcript-settings";
  import {
    getTranscriptStatus,
    listTranscriptSessions,
    saveTranscriptSettings,
    readTranscriptSession,
    deleteTranscriptSession,
    exportTranscriptSession,
    openTranscriptExports,
    commandErrorMessage,
  } from "$lib/tauri/commands";
  type SaveState =
    | { status: "saved" | "saving" }
    | { status: "error"; message: string };
  let transcriptSettings = $state<TranscriptSettings | null>(null);
  let transcriptSessions = $state<TranscriptSessionSummary[]>([]);
  let viewedTranscript = $state<{ id: number; text: string } | null>(null);
  let deleteConfirmation = $state<number | null>(null);
  let transcriptNotice = $state<string | null>(null);
  let transcriptPoll: ReturnType<typeof setInterval> | undefined;

  let transcriptSaveState = $state<SaveState>({ status: "saved" });
  let transcriptSaveRequestId = 0;
  let transcriptHistoryState = $state<
    | { status: "idle" | "loading" | "copied" }
    | { status: "exported"; path: string }
    | { status: "error"; message: string }
  >({ status: "idle" });
  onMount(() => {
    void syncTranscriptStatus();
    void refreshTranscriptSessions();
    transcriptPoll = setInterval(() => void syncTranscriptStatus(), 1000);
    return () => clearInterval(transcriptPoll);
  });
  async function autosaveTranscriptSettings(
    settingsSnapshot: TranscriptSettings,
    requestId: number,
  ) {
    try {
      const savedSettings = await saveTranscriptSettings(settingsSnapshot);

      if (requestId !== transcriptSaveRequestId) {
        return;
      }

      transcriptSettings = savedSettings;
      transcriptSaveState = { status: "saved" };
    } catch (error) {
      if (requestId !== transcriptSaveRequestId) {
        return;
      }

      transcriptSaveState = {
        status: "error",
        message: commandErrorMessage(error),
      };
    }
  }
  function updateTranscriptSaving(savingEnabled: boolean) {
    const settings = transcriptSettings;

    if (!settings) {
      return;
    }

    transcriptSaveState = { status: "saving" };
    void autosaveTranscriptSettings(
      { savingEnabled },
      ++transcriptSaveRequestId,
    );
  }
  async function syncTranscriptStatus() {
    if (transcriptSaveState.status === "saving") return;
    const requestId = transcriptSaveRequestId;
    try {
      const status = await getTranscriptStatus();
      if (requestId !== transcriptSaveRequestId) return;
      transcriptSettings = { savingEnabled: status.savingEnabled };
      transcriptNotice = status.error;
    } catch {
      transcriptNotice =
        "Transcript status unavailable. Check the main window.";
    }
  }
  async function viewTranscript(session: TranscriptSessionSummary) {
    transcriptHistoryState = { status: "loading" };
    try {
      viewedTranscript = {
        id: session.id,
        text: await readTranscriptSession(session.id),
      };
      transcriptHistoryState = { status: "idle" };
    } catch (error) {
      transcriptHistoryState = {
        status: "error",
        message: commandErrorMessage(error),
      };
    }
  }
  async function copyTranscript() {
    if (!viewedTranscript) return;
    try {
      await navigator.clipboard.writeText(viewedTranscript.text);
      transcriptHistoryState = { status: "copied" };
    } catch {
      transcriptHistoryState = {
        status: "error",
        message: "Could not copy. Select the text and copy it manually.",
      };
    }
  }
  async function deleteTranscript(sessionId: number) {
    transcriptHistoryState = { status: "loading" };
    try {
      await deleteTranscriptSession(sessionId);
      if (viewedTranscript?.id === sessionId) viewedTranscript = null;
      deleteConfirmation = null;
      transcriptHistoryState = { status: "idle" };
      await refreshTranscriptSessions();
    } catch (error) {
      transcriptHistoryState = {
        status: "error",
        message: commandErrorMessage(error),
      };
    }
  }
  async function refreshTranscriptSessions() {
    transcriptHistoryState = { status: "loading" };

    try {
      transcriptSessions = await listTranscriptSessions();
      transcriptHistoryState = { status: "idle" };
    } catch (error) {
      transcriptHistoryState = {
        status: "error",
        message: commandErrorMessage(error),
      };
    }
  }
  async function exportTranscript(
    session: TranscriptSessionSummary,
    format: TranscriptExportFormat,
  ) {
    transcriptHistoryState = { status: "loading" };

    try {
      const path = await exportTranscriptSession(session.id, format);
      transcriptHistoryState = { status: "exported", path };
    } catch (error) {
      transcriptHistoryState = {
        status: "error",
        message: commandErrorMessage(error),
      };
    }
  }
  function formatSessionTime(milliseconds: number): string {
    return new Date(milliseconds).toLocaleString();
  }
  function saveStatusText(state: SaveState): string {
    if (state.status === "saving") {
      return "Saving";
    }

    if (state.status === "error") {
      return state.message;
    }

    return "Saved";
  }
</script>

{#if transcriptSettings}
  <fieldset>
    <legend>Transcripts</legend>
    <label class="checkbox-row">
      <input
        type="checkbox"
        checked={transcriptSettings.savingEnabled}
        disabled={transcriptSaveState.status === "saving"}
        onchange={(event) =>
          updateTranscriptSaving(
            (event.currentTarget as HTMLInputElement).checked,
          )}
      />
      <span>
        <strong>Save transcripts</strong>
        <small
          >Off by default. Only new finalized speech is saved on this device.</small
        >
      </span>
    </label>
    {#if transcriptSettings.savingEnabled}<p class="model-hint" role="status">
        ● Saving locally when captions are running
      </p>{/if}
    {#if transcriptNotice}<p class="model-hint error" role="alert">
        {transcriptNotice}
      </p>{/if}
    {#if transcriptSaveState.status !== "saved"}
      <p
        class:error={transcriptSaveState.status === "error"}
        class="model-hint"
        role={transcriptSaveState.status === "error" ? "alert" : undefined}
      >
        {saveStatusText(transcriptSaveState)}
      </p>
    {/if}
    <div class="transcript-history">
      <p class="model-hint">
        Up to 100 transcripts, 64 MB of text and 64 MB of exports. Saving stops
        when full. Enabling starts a new speech segment.
      </p>
      <div class="section-row">
        <strong>History</strong>
        <button
          type="button"
          class="secondary-action small-action"
          onclick={() => void refreshTranscriptSessions()}
        >
          Refresh
        </button>
      </div>

      {#if transcriptSessions.length === 0}
        <p class="model-hint">No saved transcripts yet.</p>
      {:else}
        <div class="transcript-list">
          {#each transcriptSessions as session}
            <article class="transcript-session">
              <div>
                <strong>{session.sourceSummary}</strong>
                <small>
                  {formatSessionTime(session.startedAtMs)} ·
                  {session.segmentCount} segments
                </small>
              </div>
              <div class="export-actions">
                <button
                  type="button"
                  class="secondary-action small-action"
                  onclick={() => void viewTranscript(session)}>View</button
                >
                <button
                  type="button"
                  class="secondary-action small-action"
                  onclick={() => (deleteConfirmation = session.id)}
                  >Delete</button
                >
                {#each ["txt", "srt", "vtt", "json"] as format}
                  <button
                    type="button"
                    class="secondary-action small-action"
                    onclick={() =>
                      void exportTranscript(
                        session,
                        format as TranscriptExportFormat,
                      )}
                  >
                    {format.toUpperCase()}
                  </button>
                {/each}
              </div>
              {#if deleteConfirmation === session.id}
                <p class="model-hint">
                  Delete this transcript and its app-managed exports? Copies you
                  made elsewhere remain.
                </p>
                <div class="export-actions">
                  <button
                    type="button"
                    class="secondary-action small-action"
                    onclick={() => void deleteTranscript(session.id)}
                    >Delete permanently</button
                  >
                  <button
                    type="button"
                    class="secondary-action small-action"
                    onclick={() => (deleteConfirmation = null)}>Cancel</button
                  >
                </div>
              {/if}
            </article>
          {/each}
        </div>
      {/if}

      {#if viewedTranscript}
        <label
          >Saved transcript<textarea
            readonly
            rows="10"
            value={viewedTranscript.text}
          ></textarea></label
        >
        <div class="export-actions">
          <button
            type="button"
            class="secondary-action small-action"
            onclick={() => void copyTranscript()}>Copy text</button
          >
          <button
            type="button"
            class="secondary-action small-action"
            onclick={() => (viewedTranscript = null)}>Close transcript</button
          >
        </div>
      {/if}

      {#if transcriptHistoryState.status === "loading"}
        <p class="model-hint">Working</p>
      {:else if transcriptHistoryState.status === "exported"}
        <p class="model-hint">
          Exported to {transcriptHistoryState.path}
        </p>
        <button
          type="button"
          class="secondary-action small-action"
          onclick={() =>
            void openTranscriptExports().catch((error) => {
              transcriptHistoryState = {
                status: "error",
                message: commandErrorMessage(error),
              };
            })}>Open exports folder</button
        >
      {:else if transcriptHistoryState.status === "copied"}
        <p class="model-hint" role="status">Copied to clipboard.</p>
      {:else if transcriptHistoryState.status === "error"}
        <p class="model-hint error" role="alert">
          {transcriptHistoryState.message}
        </p>
      {/if}
    </div>
  </fieldset>
{/if}

<style>
  fieldset {
    border: 0;
    padding: 0;
    margin: 0;
    min-width: 0;
  }
  legend {
    font-weight: 650;
    margin-bottom: 16px;
  }
  .checkbox-row {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .checkbox-row span,
  .transcript-session > div:first-child {
    display: grid;
    gap: 4px;
  }
  .model-hint,
  small {
    color: var(--fgColor-muted);
    font-size: 13px;
    line-height: 1.55;
  }
  .error {
    color: #ffb4b4;
  }
  .transcript-history {
    margin-top: 20px;
  }
  .section-row,
  .export-actions {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
  }
  .section-row {
    justify-content: space-between;
  }
  .transcript-session {
    padding: 16px 0;
    border-bottom: 1px solid var(--borderColor-emphasis);
  }
  .export-actions {
    margin-top: 12px;
  }
  button {
    border: 1px solid var(--borderColor-emphasis);
    background: var(--bgColor-muted);
    color: inherit;
    border-radius: 7px;
    padding: 6px 10px;
    cursor: pointer;
    font-size: 13px;
  }
  textarea {
    box-sizing: border-box;
    width: 100%;
    resize: vertical;
    color: inherit;
    background: var(--bgColor-inset);
    border: 1px solid var(--borderColor-emphasis);
    border-radius: 8px;
    padding: 12px;
    font: inherit;
    margin-top: 8px;
  }
  input {
    accent-color: var(--fgColor-accent);
  }
</style>
