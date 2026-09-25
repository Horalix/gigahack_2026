import { invoke } from "@tauri-apps/api/core";
import type { AudioLevelEvent } from "$lib/domain/audio-meter";
import type { CaptionSettings } from "$lib/domain/caption-settings";
import type {
  AsrDiagnosticResult,
  ModelSettingsStore,
  ModelStatus,
} from "$lib/domain/model-settings";
import type {
  OverlayProfileId,
  OverlayPlacement,
  OverlaySettings,
  OverlaySettingsStore,
} from "$lib/domain/overlay-settings";
import type { PerformanceSettings } from "$lib/domain/performance-settings";
import type {
  AudioSource,
  PlatformCapabilities,
  SourcePreview,
} from "$lib/domain/source-selection";
import type {
  TranscriptExportFormat,
  TranscriptSegment,
  TranscriptSettings,
  TranscriptSessionSummary,
} from "$lib/domain/transcript-settings";
import type {
  TranslationDiagnosticResult,
  TranslationEngineStatus,
  TranslationSettings,
} from "$lib/domain/translation-settings";

export type SessionState = "idle" | "starting" | "listening" | "error";

export type AppStatus = {
  state: SessionState;
  message: string;
  selectedSource: string | null;
};

export type AppMetadata = {
  productName: string;
  version: string;
};

export function getAppMetadata(): Promise<AppMetadata> {
  return invoke<AppMetadata>("get_app_metadata");
}

export function getAppStatus(): Promise<AppStatus> {
  return invoke<AppStatus>("get_app_status");
}

export function startAudioMeter(
  sourceIds: string[],
  sourceLabel?: string,
): Promise<void> {
  return invoke<void>("start_audio_meter", { sourceIds, sourceLabel });
}

export function stopAudioMeter(): Promise<void> {
  return invoke<void>("stop_audio_meter");
}

export function openCaptionWindow(): Promise<void> {
  return invoke<void>("open_caption_window");
}

export function closeCaptionWindow(): Promise<void> {
  return invoke<void>("close_caption_window");
}

export function isCaptionWindowOpen(): Promise<boolean> {
  return invoke<boolean>("is_caption_window_open");
}

export function getOverlaySettings(): Promise<OverlaySettings> {
  return invoke<OverlaySettings>("get_overlay_settings");
}

export function saveOverlaySettings(
  settings: OverlaySettings,
): Promise<OverlaySettings> {
  return invoke<OverlaySettings>("save_overlay_settings", { settings });
}

export function getOverlaySettingsStore(): Promise<OverlaySettingsStore> {
  return invoke<OverlaySettingsStore>("get_overlay_settings_store");
}

export function saveOverlaySettingsStore(
  store: OverlaySettingsStore,
): Promise<OverlaySettingsStore> {
  return invoke<OverlaySettingsStore>("save_overlay_settings_store", { store });
}

export function selectOverlaySettingsProfile(
  profileId: OverlayProfileId,
): Promise<OverlaySettingsStore> {
  return invoke<OverlaySettingsStore>("select_overlay_settings_profile", {
    profileId,
  });
}

export function patchOverlaySettings(
  profileId: OverlayProfileId,
  patch: Partial<OverlaySettings>,
): Promise<OverlaySettingsStore> {
  return invoke<OverlaySettingsStore>("patch_overlay_settings", {
    profileId,
    patch,
  });
}

export function startOverlayPlacement(
  settings: OverlaySettings,
): Promise<OverlayPlacement> {
  return invoke<OverlayPlacement>("start_overlay_placement", { settings });
}

export function getOverlayPlacement(): Promise<OverlayPlacement | null> {
  return invoke<OverlayPlacement | null>("get_overlay_placement");
}

export function stopOverlayPlacement(): Promise<void> {
  return invoke<void>("stop_overlay_placement");
}

export type { AudioLevelEvent };

export function getPlatformCapabilities(): Promise<PlatformCapabilities> {
  return invoke<PlatformCapabilities>("get_platform_capabilities");
}

export function listAvailableSources(): Promise<AudioSource[]> {
  return invoke<AudioSource[]>("list_available_sources");
}

export function getSourcePreviews(): Promise<SourcePreview[]> {
  return invoke<SourcePreview[]>("get_source_previews");
}

export function getModelSettingsStore(): Promise<ModelSettingsStore> {
  return invoke<ModelSettingsStore>("get_model_settings_store");
}

export function saveModelSettingsStore(
  store: ModelSettingsStore,
): Promise<ModelSettingsStore> {
  return invoke<ModelSettingsStore>("save_model_settings_store", { store });
}

export function getModelStatus(): Promise<ModelStatus> {
  return invoke<ModelStatus>("get_model_status");
}

export function installDefaultAsrAssets(): Promise<ModelSettingsStore> {
  return invoke<ModelSettingsStore>("install_default_asr_assets");
}

export function runAsrModelDiagnostic(): Promise<AsrDiagnosticResult> {
  return invoke<AsrDiagnosticResult>("run_asr_model_diagnostic");
}

export function runCaptionFlowDiagnostic(): Promise<AsrDiagnosticResult> {
  return invoke<AsrDiagnosticResult>("run_caption_flow_diagnostic");
}

export function getCaptionSettings(): Promise<CaptionSettings> {
  return invoke<CaptionSettings>("get_caption_settings");
}

export function saveCaptionSettings(
  settings: CaptionSettings,
): Promise<CaptionSettings> {
  return invoke<CaptionSettings>("save_caption_settings", { settings });
}

export function getTranslationSettings(): Promise<TranslationSettings> {
  return invoke<TranslationSettings>("get_translation_settings");
}

export function saveTranslationSettings(
  settings: TranslationSettings,
): Promise<TranslationSettings> {
  return invoke<TranslationSettings>("save_translation_settings", { settings });
}

export function getTranslationEngineStatus(): Promise<TranslationEngineStatus> {
  return invoke<TranslationEngineStatus>("get_translation_engine_status");
}

export function runTranslationEngineDiagnostic(): Promise<TranslationDiagnosticResult> {
  return invoke<TranslationDiagnosticResult>(
    "run_translation_engine_diagnostic",
  );
}

export function getPerformanceSettings(): Promise<PerformanceSettings> {
  return invoke<PerformanceSettings>("get_performance_settings");
}

export function savePerformanceSettings(
  settings: PerformanceSettings,
): Promise<PerformanceSettings> {
  return invoke<PerformanceSettings>("save_performance_settings", { settings });
}

export function getTranscriptSettings(): Promise<TranscriptSettings> {
  return invoke<TranscriptSettings>("get_transcript_settings");
}

export function getTranscriptStatus(): Promise<
  TranscriptSettings & { error: string | null }
> {
  return invoke("get_transcript_status");
}

export function readTranscriptSession(sessionId: number): Promise<string> {
  return invoke("read_transcript_session", { sessionId });
}

export function deleteTranscriptSession(sessionId: number): Promise<void> {
  return invoke("delete_transcript_session", { sessionId });
}

export function saveTranscriptSettings(
  settings: TranscriptSettings,
): Promise<TranscriptSettings> {
  return invoke<TranscriptSettings>("save_transcript_settings", { settings });
}

export function startTranscriptSession(
  sourceSummary: string,
): Promise<number | null> {
  return invoke<number | null>("start_transcript_session", { sourceSummary });
}

export function appendTranscriptSegment(
  segment: TranscriptSegment,
): Promise<void> {
  return invoke<void>("append_transcript_segment", { segment });
}

export function finishTranscriptSession(): Promise<void> {
  return invoke<void>("finish_transcript_session");
}

export function listTranscriptSessions(
  limit = 100,
): Promise<TranscriptSessionSummary[]> {
  return invoke<TranscriptSessionSummary[]>("list_transcript_sessions", {
    limit,
  });
}

export function exportTranscriptSession(
  sessionId: number,
  format: TranscriptExportFormat,
): Promise<string> {
  return invoke<string>("export_transcript_session", { sessionId, format });
}

export function openTranscriptExports(): Promise<void> {
  return invoke<void>("open_transcript_exports");
}

export function commandErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }

  if (typeof error === "object" && error !== null) {
    const message = Reflect.get(error, "message");
    if (typeof message === "string") {
      return message;
    }
  }

  if (typeof error === "string" && error.length > 0) {
    return error;
  }

  return "The app could not complete that action.";
}
