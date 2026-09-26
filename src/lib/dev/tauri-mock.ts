// Development-only stand-in for the Tauri desktop runtime.
//
// The legacy caption screen at "/" calls native commands while it mounts, so in
// a plain browser it throws and renders nothing. This fake answers those
// commands with fixture data so the screen can be viewed in a browser.
//
// Installed from hooks.client.ts only when VITE_TAURI_MOCK=1 in a dev build,
// and never when the real runtime is present. Ported from the browser fixture
// in tests/ui/product.spec.js; keep the two in step if commands change.
//
// The new doctor pages must not depend on this. PBI-007 requires the browser
// path to work without any Tauri IPC.

type Callback = (message: unknown) => void;

export function installTauriMock(): void {
  const callbacks = new Map<number, Callback>();
  const listeners = new Map<string, number[]>();
  let next = 1;
  let ready = false;
  let open = false;
  let saving = false;
  let meter: ReturnType<typeof setInterval> | null = null;

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

  const emit = (event: string, payload: unknown) => {
    for (const id of listeners.get(event) ?? []) callbacks.get(id)?.({ event, payload, id });
  };

  const w = window as unknown as Record<string, unknown>;
  w.__TAURI_EVENT_PLUGIN_INTERNALS__ = { unregisterListener() {} };
  w.__TAURI_INTERNALS__ = {
    metadata: {
      currentWindow: { label: "main" },
      currentWebview: { label: "main" },
    },
    transformCallback(callback: Callback) {
      const id = next++;
      callbacks.set(id, callback);
      return id;
    },
    unregisterCallback(id: number) {
      callbacks.delete(id);
    },
    async invoke(command: string, args: Record<string, any> = {}) {
      if (command === "plugin:event|listen") {
        const ids = listeners.get(args.event) ?? [];
        ids.push(args.handler);
        listeners.set(args.event, ids);
        return args.handler;
      }
      // Window controls (minimise, close, drag) have nothing to act on here.
      if (command.startsWith("plugin:")) return null;

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
                ? { ...profile, settings: { ...profile.settings, ...args.patch } }
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
          history = history.filter((session) => session.id !== args.sessionId);
          return null;
        case "export_transcript_session":
          return "local/transcript.txt";
        case "open_transcript_exports":
          return null;
        case "start_transcript_session":
          return saving ? 2 : null;
        case "finish_transcript_session":
          return null;
        case "start_audio_meter":
          // Unlike the test fixture, keep the meter moving so the level
          // indicator looks alive while previewing.
          if (meter) clearInterval(meter);
          meter = setInterval(
            () =>
              emit("audio-level", {
                level: 0.15 + Math.random() * 0.5,
                status: "active",
                sourceIds: args.sourceIds,
                isMock: true,
                speechDetected: Math.random() > 0.3,
              }),
            120,
          );
          return null;
        case "stop_audio_meter":
          if (meter) clearInterval(meter);
          meter = null;
          return null;
        case "open_caption_window":
          open = true;
          return null;
        case "close_caption_window":
          open = false;
          return null;
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
          // Warn rather than throw: an unmocked command should show up in the
          // console without taking the whole preview down.
          console.warn(`[tauri-mock] unmocked command: ${command}`, args);
          return null;
      }
    },
  };

  console.info("[tauri-mock] Fake Tauri runtime installed (dev preview only).");
}
