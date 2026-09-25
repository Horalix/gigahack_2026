use crate::{
    app_error::{AppError, CommandResult},
    app_state::AppState,
    asr::{run_asr_diagnostic, run_system_audio_asr_diagnostic, AsrDiagnosticResult},
    caption_settings::CaptionSettings,
    model_settings::{ModelSettingsStore, ModelStatus},
    overlay_settings::{OverlayPlacement, OverlayProfileId, OverlaySettings, OverlaySettingsStore},
    performance_settings::PerformanceSettings,
    platform,
    platform::{PlatformCapabilityProvider, SourceEnumerator, SourcePreviewProvider},
    source::{AudioSource, PlatformCapabilities, SourcePreview},
    transcript::{
        TranscriptExportFormat, TranscriptSegment, TranscriptSessionSummary, TranscriptSettings,
    },
    translation::{
        run_translation_diagnostic, TranslationDiagnosticResult, TranslationEngineStatus,
        TranslationSettings,
    },
};
use serde::Serialize;
use tauri::{AppHandle, State};

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AppStatus {
    pub state: SessionState,
    pub message: String,
    pub selected_source: Option<String>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AppMetadata {
    pub product_name: String,
    pub version: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum SessionState {
    Idle,
    Starting,
    Listening,
    Error,
}

#[tauri::command]
pub fn get_app_metadata() -> AppMetadata {
    AppMetadata {
        product_name: "FeelSay".to_string(),
        version: env!("CARGO_PKG_VERSION").to_string(),
    }
}

#[tauri::command]
pub fn get_app_status() -> AppStatus {
    AppStatus {
        state: SessionState::Idle,
        message: "Ready to configure captions.".to_string(),
        selected_source: None,
    }
}

#[tauri::command]
pub fn start_audio_meter(
    app: AppHandle,
    state: State<'_, AppState>,
    source_ids: Vec<String>,
    source_label: Option<String>,
) -> CommandResult<()> {
    let asr_config = state.asr_runtime_config_for_source(source_label)?;
    if asr_config.is_none() {
        return Err(AppError::Asr("missing model; download the speech model first".into()).into());
    }

    state
        .audio_meter()
        .start_capture(app, source_ids, asr_config)?;
    Ok(())
}

#[tauri::command]
pub async fn stop_audio_meter(app: AppHandle) -> CommandResult<()> {
    use tauri::Manager;
    tauri::async_runtime::spawn_blocking(move || {
        let state = app.state::<AppState>();
        state.audio_meter().stop()?;
        state.clear_caption_text();
        Ok::<_, AppError>(())
    })
    .await
    .map_err(|_| AppError::Audio("Audio capture cleanup was interrupted".into()))?
    .map_err(Into::into)
}

#[tauri::command]
pub fn open_caption_window(state: State<'_, AppState>) -> CommandResult<()> {
    state.open_caption_process()?;
    Ok(())
}

#[tauri::command]
pub fn close_caption_window(state: State<'_, AppState>) -> CommandResult<()> {
    state
        .close_caption_process()
        .map_err(|error| AppError::Window(error.to_string()))?;
    Ok(())
}

#[tauri::command]
pub fn is_caption_window_open(state: State<'_, AppState>) -> CommandResult<bool> {
    Ok(state
        .caption_process_is_running()
        .map_err(|error| AppError::Window(error.to_string()))?)
}

#[tauri::command]
pub fn get_overlay_settings(state: State<'_, AppState>) -> CommandResult<OverlaySettings> {
    Ok(state.overlay_settings().load()?)
}

#[tauri::command]
pub fn save_overlay_settings(
    state: State<'_, AppState>,
    settings: OverlaySettings,
) -> CommandResult<OverlaySettings> {
    Ok(state.overlay_settings().save(settings)?)
}

#[tauri::command]
pub fn get_overlay_settings_store(
    state: State<'_, AppState>,
) -> CommandResult<OverlaySettingsStore> {
    Ok(state.overlay_settings().load_store()?)
}

#[tauri::command]
pub fn save_overlay_settings_store(
    state: State<'_, AppState>,
    store: OverlaySettingsStore,
) -> CommandResult<OverlaySettingsStore> {
    Ok(state.overlay_settings().save_store(store)?)
}

#[tauri::command]
pub fn select_overlay_settings_profile(
    state: State<'_, AppState>,
    profile_id: OverlayProfileId,
) -> CommandResult<OverlaySettingsStore> {
    Ok(state.overlay_settings().select_profile(profile_id)?)
}

#[tauri::command]
pub fn patch_overlay_settings(
    state: State<'_, AppState>,
    profile_id: OverlayProfileId,
    patch: serde_json::Value,
) -> CommandResult<OverlaySettingsStore> {
    Ok(state.overlay_settings().patch(Some(profile_id), patch)?)
}

#[tauri::command]
pub fn start_overlay_placement(
    state: State<'_, AppState>,
    settings: OverlaySettings,
) -> CommandResult<OverlayPlacement> {
    Ok(state.start_overlay_placement(settings)?)
}

#[tauri::command]
pub fn get_overlay_placement(
    state: State<'_, AppState>,
) -> CommandResult<Option<OverlayPlacement>> {
    Ok(state.get_overlay_placement()?)
}

#[tauri::command]
pub fn stop_overlay_placement(state: State<'_, AppState>) -> CommandResult<()> {
    state
        .stop_overlay_placement()
        .map_err(|error| AppError::Window(error.to_string()))?;
    Ok(())
}

#[tauri::command]
pub fn get_platform_capabilities() -> PlatformCapabilities {
    platform::current_provider().capabilities()
}

#[tauri::command]
pub fn list_available_sources() -> CommandResult<Vec<AudioSource>> {
    Ok(platform::current_provider().list_sources()?)
}

#[tauri::command]
pub fn get_source_previews() -> CommandResult<Vec<SourcePreview>> {
    Ok(platform::current_provider().source_previews()?)
}

#[tauri::command]
pub fn get_model_settings_store(state: State<'_, AppState>) -> CommandResult<ModelSettingsStore> {
    Ok(state.model_settings().load()?)
}

#[tauri::command]
pub fn save_model_settings_store(
    state: State<'_, AppState>,
    store: ModelSettingsStore,
) -> CommandResult<ModelSettingsStore> {
    Ok(state.model_settings().save(store)?)
}

#[tauri::command]
pub fn get_model_status(state: State<'_, AppState>) -> CommandResult<ModelStatus> {
    Ok(state.model_settings().status()?)
}

#[tauri::command]
pub async fn install_default_asr_assets(
    state: State<'_, AppState>,
) -> CommandResult<ModelSettingsStore> {
    let service = state.model_settings().clone();
    tauri::async_runtime::spawn_blocking(move || service.install_default_assets())
        .await
        .map_err(|_| AppError::Io("Speech model setup was interrupted.".into()))?
        .map_err(Into::into)
}

#[tauri::command]
pub fn run_asr_model_diagnostic(state: State<'_, AppState>) -> CommandResult<AsrDiagnosticResult> {
    let Some(config) = state.asr_runtime_config()? else {
        return Err(AppError::Asr("ASR model is not ready".to_string()).into());
    };

    Ok(run_asr_diagnostic(config)?)
}

#[tauri::command]
pub fn run_caption_flow_diagnostic(
    state: State<'_, AppState>,
) -> CommandResult<AsrDiagnosticResult> {
    let Some(config) = state.asr_runtime_config()? else {
        return Err(AppError::Asr("ASR model is not ready".to_string()).into());
    };

    state.open_caption_process()?;
    let result = run_system_audio_asr_diagnostic(config);
    state
        .close_caption_process()
        .map_err(|error| AppError::Window(error.to_string()))?;

    Ok(result?)
}

#[tauri::command]
pub fn get_caption_settings(state: State<'_, AppState>) -> CommandResult<CaptionSettings> {
    Ok(state.caption_settings().load()?)
}

#[tauri::command]
pub fn save_caption_settings(
    state: State<'_, AppState>,
    settings: CaptionSettings,
) -> CommandResult<CaptionSettings> {
    Ok(state.caption_settings().save(settings)?)
}

#[tauri::command]
pub fn get_translation_settings(state: State<'_, AppState>) -> CommandResult<TranslationSettings> {
    Ok(state.translation_settings().load()?)
}

#[tauri::command]
pub fn save_translation_settings(
    state: State<'_, AppState>,
    settings: TranslationSettings,
) -> CommandResult<TranslationSettings> {
    Ok(state.translation_settings().save(settings)?)
}

#[tauri::command]
pub fn get_translation_engine_status(state: State<'_, AppState>) -> TranslationEngineStatus {
    state.translation_settings().status()
}

#[tauri::command]
pub fn run_translation_engine_diagnostic(
    state: State<'_, AppState>,
) -> CommandResult<TranslationDiagnosticResult> {
    let caption_settings = state.caption_settings().load()?;
    let translation_settings = state.translation_settings().load()?;

    Ok(run_translation_diagnostic(
        translation_settings,
        caption_settings.translation_source_language,
        caption_settings.translation_target_language,
    )?)
}

#[tauri::command]
pub fn get_performance_settings(state: State<'_, AppState>) -> CommandResult<PerformanceSettings> {
    Ok(state.performance_settings().load()?)
}

#[tauri::command]
pub fn save_performance_settings(
    state: State<'_, AppState>,
    settings: PerformanceSettings,
) -> CommandResult<PerformanceSettings> {
    Ok(state.performance_settings().save(settings)?)
}

#[tauri::command]
pub fn get_transcript_settings(state: State<'_, AppState>) -> CommandResult<TranscriptSettings> {
    Ok(state.transcripts().load_settings()?)
}

#[tauri::command]
pub fn get_transcript_status(state: State<'_, AppState>) -> crate::transcript::TranscriptStatus {
    state.transcripts().status()
}

#[tauri::command]
pub fn read_transcript_session(
    state: State<'_, AppState>,
    session_id: i64,
) -> CommandResult<String> {
    Ok(state.transcripts().read_session(session_id)?)
}

#[tauri::command]
pub fn delete_transcript_session(state: State<'_, AppState>, session_id: i64) -> CommandResult<()> {
    Ok(state.transcripts().delete_session(session_id)?)
}

#[tauri::command]
pub fn save_transcript_settings(
    state: State<'_, AppState>,
    settings: TranscriptSettings,
) -> CommandResult<TranscriptSettings> {
    Ok(state.transcripts().save_settings(settings)?)
}

#[tauri::command]
pub fn start_transcript_session(
    state: State<'_, AppState>,
    source_summary: String,
) -> CommandResult<Option<i64>> {
    Ok(state.transcripts().start_session(source_summary)?)
}

#[tauri::command]
pub fn append_transcript_segment(
    state: State<'_, AppState>,
    segment: TranscriptSegment,
) -> CommandResult<()> {
    state.transcripts().append_segment(segment)?;
    Ok(())
}

#[tauri::command]
pub fn finish_transcript_session(state: State<'_, AppState>) -> CommandResult<()> {
    state.transcripts().finish_session()?;
    Ok(())
}

#[tauri::command]
pub fn list_transcript_sessions(
    state: State<'_, AppState>,
    limit: u32,
) -> CommandResult<Vec<TranscriptSessionSummary>> {
    Ok(state.transcripts().list_sessions(limit)?)
}

#[tauri::command]
pub fn export_transcript_session(
    state: State<'_, AppState>,
    session_id: i64,
    format: TranscriptExportFormat,
) -> CommandResult<String> {
    Ok(state.transcripts().export_session(session_id, format)?)
}

#[tauri::command]
pub fn open_transcript_exports(state: State<'_, AppState>) -> CommandResult<()> {
    let directory = state.transcripts().exports_directory()?;
    #[cfg(target_os = "windows")]
    {
        std::process::Command::new("explorer.exe")
            .arg(directory)
            .spawn()
            .map_err(AppError::from)?;
    }
    #[cfg(not(target_os = "windows"))]
    {
        let _ = directory;
        return Err(
            AppError::Io("Open the exports directory using your file manager.".into()).into(),
        );
    }
    Ok(())
}
