<script lang="ts">
  import { onMount } from "svelte";
  import SourcePreviewThumbnail from "$lib/components/source-preview-thumbnail.svelte";
  import {
    createApplicationSelection,
    createMicrophoneSelection,
    createSystemSelection,
    getSourceModeLabel,
    sourceInitials,
    type AudioSource,
    type SourceMode,
    type SourcePreview,
    type SourceSelection,
  } from "$lib/domain/source-selection";
  import {
    commandErrorMessage,
    getSourcePreviews,
    listAvailableSources,
  } from "$lib/tauri/commands";

  type Props = {
    selection: SourceSelection | null;
    onApply: (selection: SourceSelection) => void;
    onCancel: () => void;
  };

  type PickerState =
    | { status: "loading" }
    | { status: "ready"; sources: AudioSource[]; previews: SourcePreview[] }
    | { status: "error"; message: string };

  const tabs: SourceMode[] = ["applications", "system", "microphone"];

  let { selection, onApply, onCancel }: Props = $props();
  let activeTab = $state<SourceMode>("applications");
  let selectedApplications = $state<string[]>([]);
  let selectedSystemSourceId = $state("");
  let selectedDeviceId = $state("");
  let pickerState = $state<PickerState>({ status: "loading" });
  let dialog: HTMLDialogElement;

  let sources = $derived(
    pickerState.status === "ready" ? pickerState.sources : [],
  );
  let applicationSources = $derived(
    sources.filter(
      (source) => source.kind === "application" || source.kind === "window",
    ),
  );
  let systemSources = $derived(
    sources.filter((source) => source.kind === "system_audio"),
  );
  let deviceSources = $derived(
    sources.filter((source) => source.kind === "microphone"),
  );
  let previewBySourceId = $derived(
    new Map(
      pickerState.status === "ready"
        ? pickerState.previews.map((preview) => [preview.sourceId, preview])
        : [],
    ),
  );
  let draftSelection = $derived(
    buildDraftSelection(
      activeTab,
      sources,
      selectedApplications,
      selectedSystemSourceId,
      selectedDeviceId,
    ),
  );

  onMount(() => {
    dialog.showModal();
    hydrateDraft(selection);
    void loadPickerData();
  });

  async function loadPickerData() {
    try {
      const [availableSources, sourcePreviews] = await Promise.all([
        listAvailableSources(),
        getSourcePreviews(),
      ]);
      pickerState = {
        status: "ready",
        sources: availableSources,
        previews: sourcePreviews,
      };
    } catch (error) {
      pickerState = {
        status: "error",
        message: commandErrorMessage(error),
      };
    }
  }

  function hydrateDraft(sourceSelection: SourceSelection | null) {
    activeTab = sourceSelection?.mode ?? "applications";
    selectedApplications =
      sourceSelection?.mode === "applications"
        ? [...sourceSelection.selectedApplications]
        : [];
    selectedSystemSourceId =
      sourceSelection?.mode === "system"
        ? (sourceSelection.selectedSourceId ?? "")
        : "";
    selectedDeviceId =
      sourceSelection?.mode === "microphone"
        ? (sourceSelection.selectedDeviceId ?? "")
        : "";
  }

  function selectTab(tab: SourceMode) {
    activeTab = tab;
  }

  function cancel() {
    dialog.close();
    onCancel();
  }

  function navigateTabs(event: KeyboardEvent) {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const current = tabs.indexOf(activeTab);
    const next =
      event.key === "Home"
        ? 0
        : event.key === "End"
          ? tabs.length - 1
          : (current + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) %
            tabs.length;
    activeTab = tabs[next];
    (event.currentTarget as HTMLElement).parentElement
      ?.querySelectorAll<HTMLButtonElement>("button")
      [next]?.focus();
  }

  function toggleApplication(applicationId: string) {
    if (!sources.find((source) => source.id === applicationId)?.isAvailable) {
      return;
    }

    activeTab = "applications";
    selectedSystemSourceId = "";
    selectedDeviceId = "";
    selectedApplications = selectedApplications.includes(applicationId)
      ? []
      : [applicationId];
  }

  function selectSystemAudio(sourceId: string) {
    activeTab = "system";
    selectedSystemSourceId = sourceId;
    selectedApplications = [];
    selectedDeviceId = "";
  }

  function selectDevice(deviceId: string) {
    activeTab = "microphone";
    selectedDeviceId = deviceId;
    selectedApplications = [];
    selectedSystemSourceId = "";
  }

  function applySelection() {
    if (!draftSelection) {
      return;
    }

    dialog.close();
    onApply(draftSelection);
  }

  function previewFor(source: AudioSource): SourcePreview {
    return (
      previewBySourceId.get(source.id) ?? {
        sourceId: source.id,
        title: source.displayName,
        kind: source.kind,
        thumbnailUrl: null,
        thumbnailData: null,
        isLivePreviewAvailable: false,
        cssPreview: null,
        mockTemplate: null,
      }
    );
  }

  function deviceKindLabel(source: AudioSource): string {
    return source.kind === "output_device" ? "Output" : "Microphone";
  }

  function sourcePrimaryLabel(source: AudioSource): string {
    return (
      source.metadata?.appName ??
      source.metadata?.processName?.replace(/\.exe$/i, "") ??
      source.displayName
    );
  }

  function sourceSecondaryLabel(source: AudioSource): string {
    const title = source.metadata?.windowTitle ?? source.displayName;
    const process = source.metadata?.processName;

    if (title !== sourcePrimaryLabel(source)) {
      return title;
    }

    return process ?? "Window";
  }

  function sourceActionLabel(source: AudioSource): string {
    if (!source.isAvailable) {
      return "Use system audio";
    }

    return selectedApplications.includes(source.id) ? "Selected" : "Select";
  }

  function buildDraftSelection(
    mode: SourceMode,
    availableSources: AudioSource[],
    applicationIds: string[],
    systemSourceId: string,
    deviceId: string,
  ): SourceSelection | null {
    if (mode === "applications") {
      return createApplicationSelection(availableSources, applicationIds);
    }

    if (mode === "system") {
      const source = availableSources.find(
        (candidate) =>
          candidate.kind === "system_audio" && candidate.id === systemSourceId,
      );
      return createSystemSelection(source);
    }

    return createMicrophoneSelection(availableSources, deviceId);
  }
</script>

<dialog
  bind:this={dialog}
  oncancel={(event) => {
    event.preventDefault();
    cancel();
  }}
  class="source-picker"
  aria-modal="true"
  aria-labelledby="source-picker-title"
  tabindex="-1"
>
  <header class="picker-header">
    <h2 id="source-picker-title">Select source</h2>
    <button
      class="icon-button"
      type="button"
      aria-label="Close source picker"
      onclick={cancel}
    >
      x
    </button>
  </header>

  <div class="tabs" role="tablist" aria-label="Source categories">
    {#each tabs as tab}
      <button
        class:active={activeTab === tab}
        type="button"
        role="tab"
        aria-selected={activeTab === tab}
        tabindex={activeTab === tab ? 0 : -1}
        onkeydown={navigateTabs}
        onclick={() => selectTab(tab)}
      >
        {getSourceModeLabel(tab)}
      </button>
    {/each}
  </div>

  <div class="picker-body">
    {#if pickerState.status === "loading"}
      <p class="picker-message">Loading sources</p>
    {:else if pickerState.status === "error"}
      <p class="picker-message error">{pickerState.message}</p>
    {:else if activeTab === "applications"}
      {#if applicationSources.length > 0}
        <div class="application-grid" aria-label="Available applications">
          {#each applicationSources as source}
            <button
              class:selected={selectedApplications.includes(source.id)}
              class:unsupported={!source.isAvailable}
              class="application-tile"
              type="button"
              disabled={!source.isAvailable}
              aria-pressed={selectedApplications.includes(source.id)}
              onclick={() => toggleApplication(source.id)}
            >
              <SourcePreviewThumbnail
                fallbackInitials={sourceInitials(source.displayName)}
                preview={previewFor(source)}
              />
              <span class="tile-footer">
                <span class="tile-title">{sourcePrimaryLabel(source)}</span>
                <span class="tile-subtitle">{sourceSecondaryLabel(source)}</span
                >
                <span class="selection-mark" aria-hidden="true">
                  {sourceActionLabel(source)}
                </span>
              </span>
            </button>
          {/each}
        </div>
      {:else}
        <p class="picker-message">No applications found</p>
      {/if}
    {:else if activeTab === "system"}
      {#if systemSources.length > 0}
        {#each systemSources as source}
          <button
            class:selected={selectedSystemSourceId === source.id}
            class="wide-option"
            type="button"
            aria-pressed={selectedSystemSourceId === source.id}
            onclick={() => selectSystemAudio(source.id)}
          >
            <span>
              <strong>{source.displayName}</strong>
              <small>Captions everything playing on this computer.</small>
            </span>
            <span class="selection-mark" aria-hidden="true">
              {selectedSystemSourceId === source.id ? "Selected" : "Select"}
            </span>
          </button>
        {/each}
      {:else}
        <p class="picker-message">System audio is not available yet</p>
      {/if}
    {:else if deviceSources.length > 0}
      <div class="device-list" aria-label="Available audio devices">
        {#each deviceSources as source}
          <button
            class:selected={selectedDeviceId === source.id}
            class="wide-option"
            type="button"
            aria-pressed={selectedDeviceId === source.id}
            onclick={() => selectDevice(source.id)}
          >
            <span>
              <strong>{source.displayName}</strong>
              <small>
                {deviceKindLabel(source)}
                {source.metadata?.isDefault ? " - Default" : ""}
              </small>
            </span>
            <span class="selection-mark" aria-hidden="true">
              {selectedDeviceId === source.id ? "Selected" : "Select"}
            </span>
          </button>
        {/each}
      </div>
    {:else}
      <p class="picker-message">No devices found</p>
    {/if}
  </div>

  <footer class="picker-footer">
    <span class="draft-label">
      {draftSelection?.displayLabel ?? "Choose a source to continue"}
    </span>
    <div class="footer-actions">
      <button class="secondary-action" type="button" onclick={cancel}
        >Cancel</button
      >
      <button
        class="primary-action"
        type="button"
        disabled={!draftSelection}
        onclick={applySelection}
      >
        Use Source
      </button>
    </div>
  </footer>
</dialog>

<style>
  .source-picker::backdrop {
    background: oklch(0% 0 0 / 0.58);
  }

  .source-picker {
    padding: 0;
    margin: auto;
    display: grid;
    grid-template-rows: auto auto minmax(0, 1fr) auto;
    width: min(860px, calc(100% - 32px));
    height: fit-content;
    max-height: min(720px, calc(100vh - 48px));
    overflow: hidden;
    border: 1px solid var(--borderColor-default);
    border-radius: var(--radius-default);
    background: var(--bgColor-raised);
    box-shadow: 0 24px 70px oklch(0% 0 0 / 0.38);
  }

  .picker-header,
  .picker-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    padding: 18px 20px;
  }

  .picker-header {
    border-bottom: 1px solid var(--borderColor-muted);
  }

  .picker-footer {
    border-top: 1px solid var(--borderColor-muted);
  }

  h2,
  p {
    margin: 0;
  }

  h2 {
    color: var(--fgColor-default);
    font-size: 1.25rem;
    letter-spacing: 0;
  }

  .icon-button {
    width: 36px;
    height: 36px;
    border: 1px solid var(--borderColor-default);
    border-radius: var(--radius-default);
    background: var(--bgColor-muted);
    color: var(--fgColor-muted);
    cursor: pointer;
  }

  .icon-button:hover {
    background: var(--button-secondary-bgColor-hover);
    color: var(--fgColor-default);
  }

  .tabs {
    display: flex;
    gap: 8px;
    padding: 14px 20px 0;
  }

  .tabs button {
    border: 1px solid transparent;
    border-radius: var(--radius-default);
    padding: 9px 12px;
    background: transparent;
    color: var(--fgColor-muted);
    cursor: pointer;
    font-weight: 700;
  }

  .tabs button:hover,
  .tabs button.active {
    border-color: var(--borderColor-default);
    background: var(--bgColor-muted);
    color: var(--fgColor-default);
  }

  .picker-body {
    min-height: 0;
    overflow-y: auto;
    overscroll-behavior: contain;
    padding: 20px;
    scrollbar-width: none;
  }

  .picker-body::-webkit-scrollbar {
    width: 0;
    height: 0;
  }

  .application-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 220px));
    gap: 14px;
    justify-content: start;
  }

  .application-tile,
  .wide-option {
    border: 1px solid var(--borderColor-default);
    border-radius: var(--radius-default);
    background: var(--bgColor-muted);
    color: var(--fgColor-default);
    cursor: pointer;
    text-align: left;
    transition:
      background-color 140ms ease,
      border-color 140ms ease,
      transform 140ms ease;
  }

  .application-tile:hover,
  .wide-option:hover {
    border-color: var(--borderColor-emphasis);
    background: var(--bgColor-inset);
  }

  .application-tile:active,
  .wide-option:active {
    transform: translateY(1px);
  }

  .application-tile.selected,
  .wide-option.selected {
    border-color: var(--borderColor-accent);
    background: var(--bgColor-accent-muted);
  }

  .application-tile.unsupported {
    cursor: default;
    opacity: 0.62;
  }

  .application-tile.unsupported:hover {
    border-color: var(--borderColor-default);
    background: var(--bgColor-muted);
  }

  .application-tile {
    display: grid;
    gap: 10px;
    width: 100%;
    padding: 10px;
  }

  .application-tile :global(.preview-shell) {
    max-height: 124px;
  }

  .tile-footer {
    display: grid;
    gap: 8px;
    min-width: 0;
  }

  .tile-title,
  .tile-subtitle {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .tile-title {
    font-weight: 800;
  }

  .tile-subtitle {
    color: var(--fgColor-muted);
    font-size: 0.78rem;
  }

  .selection-mark {
    display: inline-flex;
    width: fit-content;
    border-radius: 999px;
    padding: 4px 8px;
    background: oklch(100% 0 0 / 0.08);
    color: var(--fgColor-muted);
    font-size: 0.8rem;
    font-weight: 700;
  }

  .selected .selection-mark {
    background: var(--button-primary-bgColor-rest);
    color: var(--fgColor-onEmphasis);
  }

  .device-list {
    display: grid;
    gap: 12px;
  }

  .wide-option {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    width: 100%;
    margin-bottom: 12px;
    padding: 16px;
  }

  .wide-option span:first-child {
    display: grid;
    gap: 4px;
  }

  .wide-option small {
    color: var(--fgColor-muted);
    font-size: 0.875rem;
  }

  .picker-message,
  .draft-label {
    color: var(--fgColor-muted);
    overflow-wrap: anywhere;
  }

  .picker-message {
    padding: 16px 0;
    text-align: center;
  }

  .picker-message.error {
    color: oklch(76% 0.15 25);
  }

  .footer-actions {
    display: flex;
    gap: 10px;
    flex: 0 0 auto;
  }

  .primary-action,
  .secondary-action {
    min-height: 40px;
    border: 1px solid transparent;
    border-radius: var(--radius-default);
    padding: 0 14px;
    cursor: pointer;
    font-weight: 700;
  }

  .primary-action {
    background: var(--button-primary-bgColor-rest);
    color: var(--fgColor-onEmphasis);
  }

  .primary-action:hover {
    background: var(--button-primary-bgColor-hover);
  }

  .primary-action:disabled {
    cursor: default;
    opacity: 0.52;
  }

  .secondary-action {
    border-color: var(--borderColor-default);
    background: transparent;
    color: var(--fgColor-default);
  }

  .secondary-action:hover {
    background: var(--button-secondary-bgColor-hover);
  }

  @media (max-width: 720px) {
    .application-grid {
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    }

    .tabs,
    .picker-header,
    .picker-footer {
      flex-wrap: wrap;
    }

    .footer-actions {
      width: 100%;
    }

    .footer-actions button {
      flex: 1;
    }
  }
</style>
