<script lang="ts">
  import { onMount } from "svelte";
  import TranscriptPanel from "$lib/components/transcript-panel.svelte";
  import {
    translationLanguageOptions,
    type CaptionSettings,
    type CaptionMode,
    type TranslationLanguage,
  } from "$lib/domain/caption-settings";
  import {
    colorPickerValue,
    rgbaPreviewColor,
    type OverlaySettings,
    type OverlaySettingsStore,
    type OverlayProfileId,
  } from "$lib/domain/overlay-settings";
  import type { ModelStatus } from "$lib/domain/model-settings";
  import {
    getOverlaySettingsStore,
    patchOverlaySettings,
    selectOverlaySettingsProfile,
    getCaptionSettings,
    saveCaptionSettings,
    getModelStatus,
    installDefaultAsrAssets,
    commandErrorMessage,
  } from "$lib/tauri/commands";

  let { onClose }: { onClose: () => void } = $props();
  let dialog: HTMLDialogElement;
  let store = $state<OverlaySettingsStore | null>(null);
  let captions = $state<CaptionSettings | null>(null);
  let model = $state<ModelStatus | null>(null);
  let tab = $state("appearance");
  let error = $state("");
  let saving = $state(false);
  let installing = $state(false);
  let revision = 0;
  let pending: Promise<unknown> = Promise.resolve();
  let poll: ReturnType<typeof setInterval>;
  const fonts = [
    "Segoe UI",
    "Arial",
    "Verdana",
    "Tahoma",
    "Georgia",
    "Consolas",
  ];
  let appearance = $derived(
    store?.profiles.find((profile) => profile.id === store?.activeProfileId)
      ?.settings,
  );

  onMount(() => {
    dialog.showModal();
    void load();
    poll = setInterval(() => {
      void syncAppearance();
      void getModelStatus()
        .then((status) => (model = status))
        .catch(() => {});
    }, 1000);
    return () => clearInterval(poll);
  });

  async function load() {
    try {
      [store, captions, model] = await Promise.all([
        getOverlaySettingsStore(),
        getCaptionSettings(),
        getModelStatus(),
      ]);
    } catch (reason) {
      error = commandErrorMessage(reason);
    }
  }

  async function syncAppearance() {
    if (saving) return;
    const started = revision;
    try {
      const current = await getOverlaySettingsStore();
      if (started === revision) store = current;
    } catch {
      /* Keep the last visible settings; explicit edits report failures. */
    }
  }

  function queueSave(update: () => Promise<OverlaySettingsStore>) {
    const current = ++revision;
    saving = true;
    error = "";
    pending = pending
      .catch(() => {})
      .then(update)
      .then((saved) => {
        if (current === revision) {
          store = saved;
          saving = false;
        }
      })
      .catch((reason) => {
        if (current === revision) {
          error = commandErrorMessage(reason);
          saving = false;
        }
      });
  }

  function updateAppearance(patch: Partial<OverlaySettings>) {
    if (!store) return;
    const profileId = store.activeProfileId;
    store = {
      ...store,
      profiles: store.profiles.map((profile) =>
        profile.id === store?.activeProfileId
          ? { ...profile, settings: { ...profile.settings, ...patch } }
          : profile,
      ),
    };
    queueSave(() => patchOverlaySettings(profileId, patch));
  }

  function selectProfile(activeProfileId: OverlayProfileId) {
    if (!store) return;
    store = { ...store, activeProfileId };
    queueSave(() => selectOverlaySettingsProfile(activeProfileId));
  }

  async function updateCaptions(patch: Partial<CaptionSettings>) {
    if (!captions) return;
    captions = { ...captions, ...patch };
    const snapshot = $state.snapshot(captions);
    pending = pending
      .catch(() => {})
      .then(() => saveCaptionSettings(snapshot))
      .catch((reason) => {
        error = commandErrorMessage(reason);
      });
    await pending;
  }

  async function setupModel() {
    installing = true;
    error = "";
    try {
      await installDefaultAsrAssets();
      model = await getModelStatus();
    } catch (reason) {
      error = commandErrorMessage(reason);
    } finally {
      installing = false;
    }
  }

  async function close() {
    await pending;
    dialog.close();
    onClose();
  }
</script>

<dialog
  bind:this={dialog}
  aria-labelledby="settings-title"
  oncancel={(event) => {
    event.preventDefault();
    void close();
  }}
>
  <header>
    <h2 id="settings-title">Settings</h2>
    <button
      class="close"
      onclick={() => void close()}
      aria-label="Close settings">×</button
    >
  </header>
  <nav aria-label="Settings sections">
    {#each [["appearance", "Appearance"], ["captions", "Captions"], ["transcripts", "Transcripts"]] as [id, label]}
      <button
        class:chosen={tab === id}
        aria-pressed={tab === id}
        onclick={() => (tab = id)}>{label}</button
      >
    {/each}
  </nav>
  <div class="content">
    {#if error}<p class="error" role="alert">{error}</p>{/if}
    {#if tab === "appearance" && appearance && store}
      <label
        >Appearance preset<select
          value={store.activeProfileId}
          onchange={(event) =>
            selectProfile(event.currentTarget.value as OverlayProfileId)}
        >
          {#each store.profiles as profile}<option value={profile.id}
              >{profile.name}</option
            >{/each}
        </select></label
      >
      <div
        class="preview"
        style={`background:${rgbaPreviewColor(appearance.backgroundColor, appearance.backgroundOpacity)};color:${appearance.textColor};font-family:${appearance.fontFamily};font-weight:${appearance.fontWeight};font-size:${Math.min(appearance.fontSize, 40)}px`}
        aria-label="Caption appearance preview"
      >
        Every word, a little clearer.
      </div>
      <div class="grid">
        <label
          >Font<select
            value={appearance.fontFamily}
            onchange={(event) =>
              updateAppearance({ fontFamily: event.currentTarget.value })}
            >{#each fonts as font}<option>{font}</option>{/each}</select
          ></label
        >
        <label
          >Text size <output>{appearance.fontSize}</output><input
            aria-label="Text size"
            type="range"
            min="18"
            max="96"
            step="2"
            value={appearance.fontSize}
            oninput={(event) =>
              updateAppearance({ fontSize: +event.currentTarget.value })}
          /></label
        >
        <label
          >Text color<input
            type="color"
            value={colorPickerValue(appearance.textColor)}
            oninput={(event) =>
              updateAppearance({ textColor: event.currentTarget.value })}
          /></label
        >
        <label
          >Background color<input
            type="color"
            value={colorPickerValue(appearance.backgroundColor)}
            oninput={(event) =>
              updateAppearance({ backgroundColor: event.currentTarget.value })}
          /></label
        >
      </div>
      <label
        >Background opacity <output
          >{Math.round(appearance.backgroundOpacity * 100)}%</output
        ><input
          aria-label="Background opacity"
          type="range"
          min="0"
          max="1"
          step="0.05"
          value={appearance.backgroundOpacity}
          oninput={(event) =>
            updateAppearance({ backgroundOpacity: +event.currentTarget.value })}
        /></label
      >
      <label class="check"
        ><input
          type="checkbox"
          checked={appearance.fontWeight === "bold"}
          onchange={(event) =>
            updateAppearance({
              fontWeight: event.currentTarget.checked ? "bold" : "normal",
            })}
        />Bold text</label
      >
      <label class="check"
        ><input
          type="checkbox"
          checked={appearance.clickThrough}
          onchange={(event) =>
            updateAppearance({ clickThrough: event.currentTarget.checked })}
        />Let clicks pass through the overlay</label
      >
      <label class="check"
        ><input
          type="checkbox"
          checked={appearance.alwaysOnTop}
          onchange={(event) =>
            updateAppearance({ alwaysOnTop: event.currentTarget.checked })}
        />Keep captions above other windows</label
      >
      <p class="hint">
        Drag the caption box to move it; drag an edge to resize. Use
        Ctrl+Shift+X to restore interaction when clicks pass through.
      </p>
      <p class="hint" role="status">
        {saving
          ? "Saving…"
          : "Changes apply immediately and are saved automatically."}
      </p>
    {:else if tab === "captions" && captions}
      <label
        >Spoken language<select
          value={captions.translationSourceLanguage}
          onchange={(event) =>
            void updateCaptions({
              translationSourceLanguage: event.currentTarget
                .value as TranslationLanguage,
            })}
        >
          {#each translationLanguageOptions as option}<option
              value={option.value}
              >{option.value === "auto"
                ? "Detect automatically"
                : option.label}</option
            >{/each}
        </select></label
      >
      <label
        >Show<select
          value={captions.mode}
          onchange={(event) =>
            void updateCaptions({
              mode: event.currentTarget.value as CaptionMode,
            })}
        >
          <option value="captions">Original speech</option><option
            value="translate">English translation</option
          ><option value="original_and_translation">Original + English</option>
        </select></label
      >
      <p class="hint">
        Language changes apply to the next caption update. Original + English
        uses more processing power. Speaker identification is not available.
      </p>
      <section class="model">
        <h3>Offline speech recognition</h3>
        <p>
          {model?.isReady
            ? "Ready to caption on this device."
            : "Download the speech model once to get started."}
        </p>
        <p class="hint">
          About 142 MB. Internet is needed only for setup. Audio and captions
          stay on your computer.
        </p>
        <button
          disabled={installing || model?.downloadProgress != null}
          onclick={() => void setupModel()}
          >{model?.downloadProgress != null
            ? `Downloading and checking: ${model.downloadProgress}%`
            : installing
              ? "Checking…"
              : model?.isReady
                ? "Check / repair speech model"
                : "Download speech model"}</button
        >
      </section>
    {:else if tab === "transcripts"}
      <TranscriptPanel />
    {:else}<p role="status">Loading settings…</p>{/if}
  </div>
  <footer>
    <span>FeelSay · Local captions</span><button onclick={() => void close()}
      >Done</button
    >
  </footer>
</dialog>

<style>
  dialog {
    box-sizing: border-box;
    width: min(620px, calc(100vw - 32px));
    max-height: calc(100vh - 32px);
    padding: 0;
    border: 1px solid var(--borderColor-emphasis);
    border-radius: 14px;
    background: var(--bgColor-default);
    color: var(--fgColor-default);
    box-shadow: var(--shadow-soft);
  }
  dialog::backdrop {
    background: rgb(0 0 0 / 0.45);
  }
  header,
  footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 24px;
    gap: 16px;
  }
  h2 {
    font-size: 20px;
    margin: 0;
  }
  h3 {
    font-size: 16px;
  }
  nav {
    display: flex;
    padding: 0 24px 12px;
    gap: 8px;
    border-bottom: 1px solid var(--borderColor-emphasis);
  }
  button,
  select {
    font: inherit;
    color: inherit;
    background: var(--bgColor-muted);
    border: 1px solid var(--borderColor-emphasis);
    border-radius: 8px;
    padding: 8px 12px;
  }
  button {
    cursor: pointer;
  }
  button:hover {
    background: var(--bgColor-inset);
  }
  button:disabled {
    opacity: 0.65;
    cursor: wait;
  }
  .close {
    background: none;
    border: 0;
    font-size: 25px;
    padding: 0 5px;
  }
  .chosen {
    color: var(--fgColor-accent);
    border-color: var(--borderColor-accent);
  }
  .content {
    padding: 24px;
    min-height: 180px;
  }
  label {
    display: grid;
    gap: 8px;
    margin-bottom: 18px;
    font-size: 14px;
  }
  select {
    min-width: 0;
    width: 100%;
  }
  input {
    accent-color: var(--fgColor-accent);
  }
  input[type="color"] {
    width: 100%;
    height: 36px;
    padding: 2px;
    border: 1px solid var(--borderColor-emphasis);
    background: none;
    border-radius: 6px;
  }
  input[type="range"] {
    width: 100%;
  }
  .grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0 20px;
  }
  .check {
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .preview {
    border-radius: 10px;
    padding: 20px;
    text-align: center;
    margin: 20px 0;
    min-height: 60px;
    display: grid;
    place-items: center;
  }
  .hint,
  footer {
    color: var(--fgColor-muted);
    font-size: 13px;
    line-height: 1.6;
  }
  .error {
    color: #ffb4b4;
  }
  footer {
    border-top: 1px solid var(--borderColor-emphasis);
  }
  .model {
    margin-top: 24px;
    padding-top: 8px;
    border-top: 1px solid var(--borderColor-emphasis);
  }
  @media (max-width: 440px) {
    .grid {
      grid-template-columns: 1fr;
    }
    header,
    footer,
    .content {
      padding: 16px;
    }
    nav {
      padding: 0 16px 12px;
      gap: 4px;
    }
    nav button {
      padding: 8px;
      font-size: 13px;
    }
  }
</style>
