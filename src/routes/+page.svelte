<script lang="ts">
  import { listen, type UnlistenFn } from "@tauri-apps/api/event";
  import { onMount } from "svelte";
  import AppTitlebar from "$lib/components/app-titlebar.svelte";
  import OverlaySettingsPanel from "$lib/components/overlay-settings-panel.svelte";
  import SourcePicker from "$lib/components/source-picker.svelte";
  import type { AudioLevelEvent } from "$lib/domain/audio-meter";
  import type { ModelStatus } from "$lib/domain/model-settings";
  import type { SourceSelection } from "$lib/domain/source-selection";
  import {
    closeCaptionWindow,
    commandErrorMessage,
    getModelStatus,
    installDefaultAsrAssets,
    getTranscriptStatus,
    isCaptionWindowOpen,
    openCaptionWindow,
    startAudioMeter,
    startTranscriptSession,
    stopAudioMeter,
    finishTranscriptSession,
  } from "$lib/tauri/commands";

  type CaptionFlowState =
    | { status: "idle" }
    | { status: "starting" }
    | { status: "captioning" }
    | { status: "stopping" }
    | { status: "error"; message: string };

  let captionFlowState = $state<CaptionFlowState>({ status: "idle" });
  let captionRequest = 0;
  let modelStatus = $state<ModelStatus | null>(null);
  let selectedSource = $state<SourceSelection | null>(null);
  let meterState = $state<AudioLevelEvent>({
    level: 0,
    status: "idle",
    sourceIds: [],
    isMock: false,
    speechDetected: false,
  });
  let isSourcePickerOpen = $state(false);
  let isSettingsOpen = $state(false);
  let isOverlayVisible = $state(false);
  let transcriptStatus = $state<{
    savingEnabled: boolean;
    error: string | null;
  }>({ savingEnabled: false, error: null });
  let unlistenAudioLevel: UnlistenFn | undefined;
  let unlistenControls: UnlistenFn[] = [];
  let captionWindowPoll: ReturnType<typeof setInterval> | undefined;

  let isBusy = $derived(
    captionFlowState.status === "starting" ||
      captionFlowState.status === "stopping",
  );
  let isCaptioning = $derived(captionFlowState.status === "captioning");
  let canUsePrimaryAction = $derived(
    !isBusy && (selectedSource !== null || isCaptioning),
  );
  let primaryActionLabel = $derived(getPrimaryActionLabel(captionFlowState));
  let statusMessage = $derived(
    captionFlowState.status === "error" ? captionFlowState.message : "",
  );
  let meterPercent = $derived(Math.round(meterState.level * 100));
  let meterLabel = $derived(
    isCaptioning && !isOverlayVisible
      ? "Overlay hidden"
      : getMeterLabel(meterState),
  );
  onMount(() => {
    void loadModelStatus();
    const transcriptPoll = setInterval(() => {
      if (
        captionFlowState.status === "starting" ||
        modelStatus?.downloadProgress != null
      )
        void loadModelStatus();
      void getTranscriptStatus()
        .then((status) => (transcriptStatus = status))
        .catch(() => {});
    }, 1000);

    void listen<AudioLevelEvent>("audio-level", (event) => {
      meterState = event.payload;
      if (
        event.payload.status === "active" &&
        captionFlowState.status === "starting"
      )
        captionFlowState = { status: "captioning" };
      if (
        event.payload.status === "error" &&
        (captionFlowState.status === "starting" ||
          captionFlowState.status === "captioning")
      ) {
        const message =
          event.payload.message ??
          "Audio capture stopped. Select the source again.";
        void stopCaptions().then(() => {
          captionFlowState = { status: "error", message };
        });
      }
    }).then((unlisten) => {
      unlistenAudioLevel = unlisten;
    });

    void Promise.all([
      listen("control-toggle-captions", () => {
        void handlePrimaryAction();
      }),
      listen("control-toggle-overlay", () => {
        void toggleOverlayVisibility();
      }),
      listen("control-open-settings", () => {
        isSettingsOpen = true;
      }),
      listen<boolean>("control-click-through-toggled", () => {
        // Settings reload on next open; running overlay reads the runtime file.
      }),
    ]).then((unlisten) => {
      unlistenControls = unlisten;
    });

    return () => {
      clearInterval(transcriptPoll);
      stopCaptionWindowPolling();
      cleanupMeter();
      cleanupControls();
    };
  });

  function getPrimaryActionLabel(state: CaptionFlowState): string {
    if (state.status === "captioning") {
      return "Stop";
    }

    if (state.status === "starting") {
      return "Starting";
    }

    if (state.status === "stopping") {
      return "Stopping";
    }

    return "Start";
  }

  function getMeterLabel(state: AudioLevelEvent): string {
    if (state.status === "error") {
      return state.message ?? "Audio error";
    }

    if (state.status === "active") {
      return state.speechDetected ? "Speech" : "Silence";
    }

    if (state.status === "starting") {
      return "Starting";
    }

    return "Ready";
  }

  async function loadModelStatus() {
    try {
      modelStatus = await getModelStatus();
    } catch {
      modelStatus = null;
    }
  }

  async function applySourceSelection(selection: SourceSelection) {
    const restart = isCaptioning;
    if (restart) await stopCaptions();
    selectedSource = selection;
    meterState = {
      level: 0,
      status: "idle",
      sourceIds: getSourceIds(selection),
      isMock: false,
      speechDetected: false,
    };
    isSourcePickerOpen = false;
    if (restart) {
      await startCaptions();
      return;
    }

    if (captionFlowState.status === "error") {
      captionFlowState = { status: "idle" };
    }
  }

  async function handlePrimaryAction() {
    if (captionFlowState.status === "captioning") {
      await stopCaptions();
      return;
    }

    await startCaptions();
  }

  async function startCaptions() {
    if (!selectedSource || isBusy || isCaptioning) {
      return;
    }

    captionFlowState = { status: "starting" };
    const request = ++captionRequest;
    await loadModelStatus();

    try {
      if (!modelStatus?.isReady) {
        await installDefaultAsrAssets();
        await loadModelStatus();
      }
      await startTranscriptSession(selectedSource.displayLabel);
      await startAudioMeter(
        getSourceIds(selectedSource),
        selectedSource.displayLabel,
      );
      if (request !== captionRequest) return;
      await openCaptionWindow();
      if (request !== captionRequest) {
        await closeCaptionWindow();
        return;
      }
      isOverlayVisible = true;
      startCaptionWindowPolling();
    } catch (error) {
      await Promise.allSettled([closeCaptionWindow(), stopAudioMeter()]);
      await finishTranscriptSession().catch(() => {});
      captionFlowState = {
        status: "error",
        message: commandErrorMessage(error),
      };
    }
  }

  async function stopCaptions() {
    captionRequest += 1;
    captionFlowState = { status: "stopping" };

    try {
      await closeCaptionWindow();
      isOverlayVisible = false;
      stopCaptionWindowPolling();
      await stopAudioMeter();
      await finishTranscriptSession();
      captionFlowState = { status: "idle" };
    } catch (error) {
      captionFlowState = {
        status: "error",
        message: commandErrorMessage(error),
      };
    }
  }

  function getSourceIds(selection: SourceSelection): string[] {
    if (selection.mode === "applications") {
      return selection.selectedApplications;
    }

    return [
      selection.selectedSourceId ?? selection.selectedDeviceId ?? "",
    ].filter(Boolean);
  }

  function cleanupMeter() {
    unlistenAudioLevel?.();
    unlistenAudioLevel = undefined;
    void stopAudioMeter();
  }

  function cleanupControls() {
    for (const unlisten of unlistenControls) {
      unlisten();
    }

    unlistenControls = [];
  }

  function startCaptionWindowPolling() {
    stopCaptionWindowPolling();
    captionWindowPoll = setInterval(() => {
      void syncCaptionWindowState();
    }, 750);
  }

  function stopCaptionWindowPolling() {
    if (captionWindowPoll) {
      clearInterval(captionWindowPoll);
      captionWindowPoll = undefined;
    }
  }

  async function syncCaptionWindowState() {
    if (captionFlowState.status !== "captioning") {
      return;
    }

    try {
      if (await isCaptionWindowOpen()) {
        return;
      }

      stopCaptionWindowPolling();
      isOverlayVisible = false;
      await stopAudioMeter();
      await finishTranscriptSession();
      captionFlowState = { status: "idle" };
    } catch (error) {
      stopCaptionWindowPolling();
      captionFlowState = {
        status: "error",
        message: commandErrorMessage(error),
      };
    }
  }

  async function toggleOverlayVisibility() {
    if (captionFlowState.status !== "captioning") {
      captionFlowState = {
        status: "error",
        message: "Start captions before hiding the overlay.",
      };
      return;
    }

    try {
      if (await isCaptionWindowOpen()) {
        await closeCaptionWindow();
        stopCaptionWindowPolling();
        isOverlayVisible = false;
        return;
      }

      await openCaptionWindow();
      isOverlayVisible = true;
      startCaptionWindowPolling();
    } catch (error) {
      captionFlowState = {
        status: "error",
        message: commandErrorMessage(error),
      };
    }
  }
</script>

<svelte:head>
  <title>FeelSay</title>
</svelte:head>

<div class="app-window">
  <AppTitlebar />

  <main class="utility-shell">
    <section class="utility-stack" aria-labelledby="app-title">
      <div class="identity">
        <h1 id="app-title">FeelSay</h1>
        <p>Live captions and translation</p>
      </div>

      <button
        class="select-source-button"
        type="button"
        disabled={isBusy}
        onclick={() => (isSourcePickerOpen = true)}
      >
        Select Source
      </button>

      <p class="source-summary" aria-live="polite">
        {selectedSource?.displayLabel ?? "No source selected"}
      </p>

      {#if selectedSource}
        <div class="meter-stack">
          <div
            class:active-meter={meterState.status === "active"}
            class="audio-meter"
            aria-label="Audio level"
            aria-valuemin="0"
            aria-valuemax="100"
            aria-valuenow={meterPercent}
            role="meter"
          >
            <span style={`width: ${meterPercent}%`}></span>
          </div>
          <p class="meter-status">{meterLabel}</p>
        </div>
      {/if}

      <button
        class:stop-action={isCaptioning}
        class="primary-action"
        type="button"
        disabled={!canUsePrimaryAction}
        aria-busy={isBusy}
        onclick={handlePrimaryAction}
      >
        {primaryActionLabel}
      </button>

      <button
        class="settings-action"
        type="button"
        onclick={() => (isSettingsOpen = true)}
      >
        Settings
      </button>

      {#if !modelStatus?.isReady}
        <p class="meter-status" role="status">
          {isBusy
            ? modelStatus?.downloadProgress != null
              ? `Speech model: ${modelStatus.downloadProgress}% downloaded`
              : "Preparing the speech model..."
            : "First Start downloads a 142 MB speech model. Captions then work offline."}
        </p>
      {/if}
      {#if statusMessage}
        <p class="error-message" role="alert">{statusMessage}</p>
      {/if}
      {#if transcriptStatus.error}
        <p class="error-message" role="alert">{transcriptStatus.error}</p>
      {:else if isCaptioning && transcriptStatus.savingEnabled}
        <p class="meter-status" role="status">● Saving transcript locally</p>
      {/if}
    </section>

    {#if isSourcePickerOpen}
      <SourcePicker
        selection={selectedSource}
        onApply={applySourceSelection}
        onCancel={() => (isSourcePickerOpen = false)}
      />
    {/if}

    {#if isSettingsOpen}
      <OverlaySettingsPanel
        onClose={() => {
          isSettingsOpen = false;
          void loadModelStatus();
        }}
      />
    {/if}
  </main>
</div>

<style>
  .app-window {
    display: grid;
    grid-template-rows: auto 1fr;
    min-height: 100vh;
    background: var(--bgColor-default);
  }

  h1,
  p {
    margin: 0;
  }

  .utility-shell {
    display: grid;
    min-height: 0;
    box-sizing: border-box;
    place-items: center;
    padding: 48px 24px 72px;
  }

  .utility-stack {
    display: grid;
    width: min(360px, 100%);
    justify-items: center;
    gap: 18px;
    text-align: center;
  }

  .identity {
    display: grid;
    gap: 6px;
    margin-bottom: 14px;
  }

  h1 {
    color: var(--fgColor-default);
    font-size: 2rem;
    line-height: 1.1;
    letter-spacing: 0;
  }

  .identity p {
    color: var(--fgColor-muted);
    font-size: 1rem;
  }

  .select-source-button,
  .primary-action {
    width: 180px;
    min-height: 42px;
    border-radius: var(--radius-default);
    padding: 0 18px;
    font-weight: 700;
    transition:
      background-color 140ms ease,
      color 140ms ease,
      transform 140ms ease;
  }

  .select-source-button {
    border: 1px solid var(--borderColor-muted);
    background: var(--bgColor-muted);
    color: var(--fgColor-default);
    cursor: pointer;
  }

  .select-source-button:hover {
    background: var(--button-secondary-bgColor-hover);
    color: var(--fgColor-default);
  }

  .source-summary {
    min-height: 24px;
    color: var(--fgColor-muted);
    font-size: 0.9375rem;
    overflow-wrap: anywhere;
  }

  .audio-meter {
    width: 180px;
    height: 6px;
    overflow: hidden;
    border-radius: 999px;
    background: var(--bgColor-muted);
  }

  .meter-stack {
    display: grid;
    justify-items: center;
    gap: 8px;
  }

  .audio-meter span {
    display: block;
    height: 100%;
    border-radius: inherit;
    background: var(--borderColor-muted);
    transition:
      width 120ms linear,
      background-color 140ms ease;
  }

  .audio-meter.active-meter span {
    background: var(--button-primary-bgColor-rest);
  }

  .meter-status {
    color: var(--fgColor-muted);
    font-size: 0.75rem;
  }

  .primary-action {
    border: 1px solid transparent;
    background: var(--button-primary-bgColor-rest);
    color: var(--fgColor-onEmphasis);
    cursor: pointer;
    font-weight: 700;
  }

  .primary-action:not(:disabled):hover {
    background: var(--button-primary-bgColor-hover);
  }

  .select-source-button:active,
  .primary-action:not(:disabled):active {
    transform: translateY(1px);
  }

  .primary-action.stop-action {
    border-color: var(--borderColor-muted);
    background: transparent;
    color: var(--fgColor-default);
  }

  .primary-action.stop-action:not(:disabled):hover {
    background: var(--button-secondary-bgColor-hover);
  }

  .primary-action:disabled {
    cursor: default;
    opacity: 0.45;
  }

  .settings-action {
    border: 0;
    background: transparent;
    color: var(--fgColor-muted);
    cursor: pointer;
    font-size: 0.875rem;
  }

  .settings-action:hover {
    color: var(--fgColor-default);
  }

  .error-message {
    max-width: 32ch;
    color: oklch(76% 0.15 25);
    font-size: 0.875rem;
  }

  @media (max-width: 520px) {
    .utility-shell {
      padding: 40px 20px 56px;
    }

    .select-source-button,
    .primary-action,
    .audio-meter,
    .meter-stack {
      width: 100%;
    }
  }
</style>
