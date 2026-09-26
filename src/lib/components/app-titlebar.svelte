<script lang="ts">
  import { getCurrentWindow } from "@tauri-apps/api/window";

  const currentWindow = getCurrentWindow();

  async function startDragging() {
    try {
      await currentWindow.startDragging();
    } catch (error) {
      console.error(error);
    }
  }

  async function minimizeWindow() {
    try {
      await currentWindow.minimize();
    } catch (error) {
      console.error(error);
    }
  }

  async function toggleMaximizeWindow() {
    try {
      await currentWindow.toggleMaximize();
    } catch (error) {
      console.error(error);
    }
  }

  async function closeWindow() {
    try {
      await currentWindow.close();
    } catch (error) {
      console.error(error);
    }
  }
</script>

<header class="titlebar">
  <button
    class="drag-region"
    type="button"
    tabindex="-1"
    aria-label="Move window"
    onpointerdown={startDragging}
  >
    <img class="app-symbol" src="/brand/symbol.svg" alt="" />
    <span>Notavra</span>
  </button>

  <div class="window-controls" aria-label="Window controls">
    <button type="button" aria-label="Minimize" onclick={minimizeWindow}>
      <span class="control-icon minimize" aria-hidden="true"></span>
    </button>
    <button type="button" aria-label="Maximize" onclick={toggleMaximizeWindow}>
      <span class="control-icon maximize" aria-hidden="true"></span>
    </button>
    <button
      class="close"
      type="button"
      aria-label="Close"
      onclick={closeWindow}
    >
      <span class="control-icon close-icon" aria-hidden="true"></span>
    </button>
  </div>
</header>

<style>
  .titlebar {
    display: grid;
    grid-template-columns: 1fr auto;
    height: 34px;
    border-bottom: 3px solid oklch(35.12% 0.0246 262.79);
    background: oklch(23.13% 0.012 270.86);
    color: var(--fgColor-default);
    user-select: none;
  }

  .drag-region {
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
    border: 0;
    padding: 0 10px;
    background: transparent;
    color: var(--fgColor-muted);
    cursor: default;
    font-size: 0.8125rem;
    font-weight: 650;
    text-align: left;
  }

  .app-symbol {
    width: 18px;
    height: 18px;
    flex: 0 0 auto;
  }

  .window-controls {
    display: flex;
    height: 100%;
  }

  .window-controls button {
    display: grid;
    width: 46px;
    height: 34px;
    place-items: center;
    border: 0;
    background: transparent;
    color: var(--fgColor-muted);
    cursor: default;
  }

  .window-controls button:hover {
    background: oklch(29.25% 0.0196 264.21);
    color: var(--fgColor-default);
  }

  .window-controls button.close:hover {
    background: oklch(29.25% 0.0196 264.21);
    color: var(--fgColor-default);
  }

  .window-controls button:active {
    background: oklch(68.75% 0.141 250.36);
    color: oklch(100% 0 89.88);
  }

  .control-icon {
    position: relative;
    display: block;
    width: 12px;
    height: 12px;
  }

  .minimize::before {
    position: absolute;
    top: 6px;
    left: 1px;
    width: 10px;
    height: 1px;
    background: currentColor;
    content: "";
  }

  .maximize {
    box-sizing: border-box;
    border: 1px solid currentColor;
  }

  .close-icon::before,
  .close-icon::after {
    position: absolute;
    top: 5px;
    left: 0;
    width: 12px;
    height: 1px;
    background: currentColor;
    content: "";
  }

  .close-icon::before {
    transform: rotate(45deg);
  }

  .close-icon::after {
    transform: rotate(-45deg);
  }
</style>
