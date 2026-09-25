// @ts-nocheck -- This isolated browser fixture supplies the native IPC globals at runtime.
import { test, expect } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    const callbacks = new Map();
    const listeners = new Map();
    let next = 1;
    let ready = false;
    let open = false;
    let saving = false;
    const appearance = {
      alwaysOnTop: true,
      fontFamily: "Segoe UI",
      fontSize: 42,
      fontWeight: "bold",
      originalLineScale: 0.8,
      textColor: "#ffffff",
      backgroundColor: "#000000",
      backgroundOpacity: 0.47,
      outlineColor: "#000000",
      outlineWidth: 2,
      startWidth: 900,
      startHeight: 180,
      startX: null,
      startY: null,
      clickThrough: false,
    };
    let store = {
      activeProfileId: "profile1",
      profiles: [1, 2, 3, 4, 5].map((id) => ({
        id: `profile${id}`,
        name: `Preset ${id}`,
        settings: { ...appearance },
      })),
    };
    let captions = {
      mode: "captions",
      speakerLabelsEnabled: false,
      translationSourceLanguage: "auto",
      translationTargetLanguage: "english",
    };
    let history = [
      {
        id: 1,
        startedAtMs: 1788610000000,
        endedAtMs: 1788610040000,
        sourceSummary: "Saved meeting",
        segmentCount: 2,
      },
    ];
    const commands = [];
    const emit = (event, payload) => {
      for (const id of listeners.get(event) ?? [])
        callbacks.get(id)?.({ event, payload, id });
    };
    window.__productTest = {
      commands,
      emit,
      setSaving(value) {
        saving = value;
      },
    };
    window.__TAURI_EVENT_PLUGIN_INTERNALS__ = { unregisterListener() {} };
    window.__TAURI_INTERNALS__ = {
      metadata: {
        currentWindow: { label: "main" },
        currentWebview: { label: "main" },
      },
      transformCallback(callback) {
        const id = next++;
        callbacks.set(id, callback);
        return id;
      },
      unregisterCallback(id) {
        callbacks.delete(id);
      },
      async invoke(command, args = {}) {
        commands.push(command);
        if (command === "plugin:event|listen") {
          const ids = listeners.get(args.event) ?? [];
          ids.push(args.handler);
          listeners.set(args.event, ids);
          return args.handler;
        }
        if (command.startsWith("plugin:")) return;
        switch (command) {
          case "get_model_status":
            return {
              isReady: ready,
              activeModel: { supportsTranslation: true },
              modelsDir: "fixture",
              message: "",
            };
          case "install_default_asr_assets":
            ready = true;
            return {};
          case "get_overlay_settings_store":
            return structuredClone(store);
          case "save_overlay_settings_store":
            store = args.store;
            return structuredClone(store);
          case "patch_overlay_settings":
            store = {
              ...store,
              profiles: store.profiles.map((profile) =>
                profile.id === args.profileId
                  ? {
                      ...profile,
                      settings: { ...profile.settings, ...args.patch },
                    }
                  : profile,
              ),
            };
            return structuredClone(store);
          case "select_overlay_settings_profile":
            store.activeProfileId = args.profileId;
            return structuredClone(store);
          case "get_caption_settings":
            return captions;
          case "save_caption_settings":
            captions = args.settings;
            return captions;
          case "get_transcript_status":
            return { savingEnabled: saving, error: null };
          case "save_transcript_settings":
            saving = args.settings.savingEnabled;
            return { savingEnabled: saving };
          case "list_transcript_sessions":
            return history;
          case "read_transcript_session":
            return "Saved meeting\n[00:00:01.000] These are finalized words.";
          case "delete_transcript_session":
            history = history.filter(
              (session) => session.id !== args.sessionId,
            );
            return;
          case "export_transcript_session":
            return "local/transcript.txt";
          case "open_transcript_exports":
            return;
          case "start_transcript_session":
            return saving ? 2 : null;
          case "finish_transcript_session":
            return;
          case "start_audio_meter":
            setTimeout(
              () =>
                emit("audio-level", {
                  level: 0.2,
                  status: "active",
                  sourceIds: args.sourceIds,
                  isMock: false,
                  speechDetected: true,
                }),
              50,
            );
            return;
          case "stop_audio_meter":
            return;
          case "open_caption_window":
            open = true;
            return;
          case "close_caption_window":
            open = false;
            return;
          case "is_caption_window_open":
            return open;
          case "list_available_sources":
            return [
              {
                id: "system-audio",
                displayName: "All system audio",
                kind: "system_audio",
                isAvailable: true,
                platform: "windows",
              },
            ];
          case "get_source_previews":
            return [];
          default:
            throw new Error(`Unexpected command: ${command}`);
        }
      },
    };
  });
  await page.goto("/");
});

async function startCaptions(page) {
  await page
    .getByRole("button", { name: "Select Source", exact: true })
    .click();
  await page.getByRole("tab", { name: "Entire System", exact: true }).click();
  await page.getByRole("button", { name: /All system audio Captions/ }).click();
  await page.getByRole("button", { name: "Use Source", exact: true }).click();
  await page.getByRole("button", { name: "Start", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Stop", exact: true }),
  ).toBeEnabled();
}

test("first Start prepares local speech; transcript toggles do not restart capture", async ({
  page,
}, info) => {
  await expect(
    page.getByRole("button", { name: "Start", exact: true }),
  ).toBeDisabled();
  await startCaptions(page);
  await page.screenshot({ path: info.outputPath("main.png") });
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await page.getByRole("button", { name: "Transcripts", exact: true }).click();
  const toggle = page.getByRole("checkbox", { name: /Save transcripts/ });
  await expect(toggle).not.toBeChecked();
  await toggle.check();
  await expect(toggle).toBeChecked();
  await toggle.uncheck();
  await expect(toggle).not.toBeChecked();
  await page.evaluate(() => window.__productTest.setSaving(true));
  await expect(toggle).toBeChecked();
  const commands = await page.evaluate(() => window.__productTest.commands);
  expect(
    commands.filter((command) => command === "start_audio_meter"),
  ).toHaveLength(1);
  expect(
    commands.filter((command) => command === "install_default_asr_assets"),
  ).toHaveLength(1);
  await page.getByRole("button", { name: "Done", exact: true }).click();
  await page.getByRole("button", { name: "Stop", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Start", exact: true }),
  ).toBeEnabled();
});

test("history can be viewed, exported and deleted; narrow settings remain usable", async ({
  page,
}, info) => {
  await page.setViewportSize({ width: 420, height: 600 });
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await page.screenshot({ path: info.outputPath("settings-narrow.png") });
  await page.getByRole("button", { name: "Transcripts", exact: true }).click();
  await page.getByRole("button", { name: "View", exact: true }).click();
  await expect(
    page.getByRole("textbox", { name: "Saved transcript" }),
  ).toHaveValue(/finalized words/);
  await page.getByRole("button", { name: "TXT", exact: true }).click();
  await expect(
    page.getByText("Exported to local/transcript.txt"),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Open exports folder", exact: true })
    .click();
  expect(
    await page.evaluate(() =>
      window.__productTest.commands.includes("open_transcript_exports"),
    ),
  ).toBe(true);
  await page.getByRole("button", { name: "Delete", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Delete permanently", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Delete permanently", exact: true })
    .click();
  await expect(page.getByText("No saved transcripts yet.")).toBeVisible();
  await expect(
    page.getByRole("textbox", { name: "Saved transcript" }),
  ).toHaveCount(0);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: "Settings" })).toHaveCount(0);
});

test("capture failures clean up and offer a retry", async ({ page }) => {
  await startCaptions(page);
  await page.evaluate(() =>
    window.__productTest.emit("audio-level", {
      status: "error",
      level: 0,
      isMock: false,
      speechDetected: false,
      sourceIds: ["system-audio"],
      message: "The selected device disconnected.",
    }),
  );
  await expect(page.getByRole("alert")).toHaveText(
    "The selected device disconnected.",
  );
  await expect(
    page.getByRole("button", { name: "Start", exact: true }),
  ).toBeEnabled();
  expect(
    await page.evaluate(() =>
      window.__productTest.commands.includes("stop_audio_meter"),
    ),
  ).toBe(true);
});

test("keyboard source navigation and live settings survive reopening", async ({
  page,
}) => {
  await page
    .getByRole("button", { name: "Select Source", exact: true })
    .click();
  await page.getByRole("tab", { name: "Applications", exact: true }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(
    page.getByRole("tab", { name: "Entire System", exact: true }),
  ).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("button", { name: "Select Source", exact: true }),
  ).toBeFocused();
  await startCaptions(page);
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await page.getByRole("slider", { name: "Text size", exact: true }).focus();
  await page.keyboard.press("End");
  await expect(
    page.getByRole("slider", { name: "Text size", exact: true }),
  ).toHaveValue("96");
  await page.getByRole("button", { name: "Captions", exact: true }).click();
  await page
    .getByRole("combobox", { name: "Show", exact: true })
    .selectOption("original_and_translation");
  await page.getByRole("button", { name: "Done", exact: true }).click();
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await expect(
    page.getByRole("slider", { name: "Text size", exact: true }),
  ).toHaveValue("96");
  await page.getByRole("button", { name: "Captions", exact: true }).click();
  await expect(
    page.getByRole("combobox", { name: "Show", exact: true }),
  ).toHaveValue("original_and_translation");
  expect(
    await page.evaluate(
      () =>
        window.__productTest.commands.filter(
          (command) => command === "start_audio_meter",
        ).length,
    ),
  ).toBe(1);
});
