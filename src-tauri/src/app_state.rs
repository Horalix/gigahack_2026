use crate::{
    asr::{write_caption_state, AsrRuntimeConfig},
    audio_capture::AudioMeterService,
    caption_settings::{CaptionMode, CaptionSettingsService},
    model_settings::ModelSettingsService,
    overlay_settings::{OverlayPlacement, OverlaySettings, OverlaySettingsService},
    performance_settings::PerformanceSettingsService,
    transcript::TranscriptService,
    translation::{TranslationRuntimeConfig, TranslationSettingsService},
};
use std::{
    fs, io,
    path::PathBuf,
    process::{Child, Command, Stdio},
    sync::Mutex,
};

pub struct AppState {
    pub overlay_control: Mutex<Option<crate::overlay_control::OverlayControlEndpoint>>,
    audio_meter_service: AudioMeterService,
    caption_settings_service: CaptionSettingsService,
    model_settings_service: ModelSettingsService,
    overlay_settings_service: OverlaySettingsService,
    performance_settings_service: PerformanceSettingsService,
    transcript_service: TranscriptService,
    translation_settings_service: TranslationSettingsService,
    caption_process: Mutex<Option<Child>>,
    placement_process: Mutex<Option<Child>>,
    placement_file: PathBuf,
    caption_file: PathBuf,
    caption_file_guard: Mutex<Option<fs::File>>,
}

impl AppState {
    pub fn new(data_dir: PathBuf) -> Self {
        let _ = fs::remove_file(data_dir.join("caption-runtime.json"));
        Self {
            overlay_control: Mutex::new(None),
            audio_meter_service: AudioMeterService::default(),
            caption_settings_service: CaptionSettingsService::new(data_dir.clone()),
            model_settings_service: ModelSettingsService::new(data_dir.clone()),
            overlay_settings_service: OverlaySettingsService::new(data_dir.clone()),
            performance_settings_service: PerformanceSettingsService::new(data_dir.clone()),
            transcript_service: TranscriptService::new(data_dir.clone()),
            translation_settings_service: TranslationSettingsService::new(data_dir.clone()),
            caption_process: Mutex::new(None),
            placement_process: Mutex::new(None),
            placement_file: std::env::temp_dir().join(format!(
                "feelsay-overlay-placement-{}.json",
                std::process::id()
            )),
            caption_file: std::env::temp_dir()
                .join(format!("feelsay-caption-{}.json", std::process::id())),
            caption_file_guard: Mutex::new(None),
        }
    }

    pub fn audio_meter(&self) -> &AudioMeterService {
        &self.audio_meter_service
    }

    pub fn clear_caption_text(&self) {
        drop(self.caption_file_guard.lock().unwrap().take());
        let _ = fs::remove_file(&self.caption_file);
    }

    fn ensure_caption_file(&self) -> io::Result<()> {
        let mut guard = self.caption_file_guard.lock().unwrap();
        if guard.is_none() {
            *guard = Some(crate::persistence::open_ephemeral(&self.caption_file)?);
        }
        Ok(())
    }

    pub fn caption_settings(&self) -> &CaptionSettingsService {
        &self.caption_settings_service
    }

    pub fn overlay_settings(&self) -> &OverlaySettingsService {
        &self.overlay_settings_service
    }

    pub fn model_settings(&self) -> &ModelSettingsService {
        &self.model_settings_service
    }

    pub fn performance_settings(&self) -> &PerformanceSettingsService {
        &self.performance_settings_service
    }

    pub fn transcripts(&self) -> &TranscriptService {
        &self.transcript_service
    }

    pub fn translation_settings(&self) -> &TranslationSettingsService {
        &self.translation_settings_service
    }

    pub fn asr_runtime_config(
        &self,
    ) -> Result<Option<AsrRuntimeConfig>, crate::app_error::AppError> {
        self.asr_runtime_config_for_source(None)
    }

    pub fn asr_runtime_config_for_source(
        &self,
        source_label: Option<String>,
    ) -> Result<Option<AsrRuntimeConfig>, crate::app_error::AppError> {
        let caption_settings = self.caption_settings_service.load()?;
        let caption_mode = caption_settings.mode;
        let status = self.model_settings_service.status()?;
        let Some(model) = status.active_model else {
            return Ok(None);
        };

        if !model.is_installed {
            return Ok(None);
        }

        if matches!(
            caption_mode,
            CaptionMode::Translate | CaptionMode::OriginalAndTranslation
        ) && !model.supports_translation
        {
            return Err(crate::app_error::AppError::Asr(
                "translation requires a multilingual Whisper model".to_string(),
            ));
        }

        let executable_path = model
            .executable_path
            .as_deref()
            .map(PathBuf::from)
            .filter(|path| path.exists());

        #[cfg(not(feature = "local-asr"))]
        if executable_path.is_none() {
            return Ok(None);
        }

        self.ensure_caption_file()?;
        Ok(Some(AsrRuntimeConfig {
            preferences: self.caption_settings_service.runtime(),
            model_path: model.path.into(),
            executable_path,
            caption_path: self.caption_file.clone(),
            transcript: self.transcript_service.runtime_config(),
            caption_mode,
            translation: if matches!(
                caption_mode,
                CaptionMode::Translate | CaptionMode::OriginalAndTranslation
            ) {
                Some(TranslationRuntimeConfig::new(
                    self.translation_settings_service.load()?,
                    caption_settings.translation_source_language,
                    caption_settings.translation_target_language,
                ))
            } else {
                None
            },
            performance: self.performance_settings_service.load()?.runtime(),
            source_label: source_label.and_then(normalize_source_label),
            speaker_labels_enabled: caption_settings.speaker_labels_enabled,
        }))
    }

    pub fn open_caption_process(&self) -> Result<(), crate::app_error::AppError> {
        self.ensure_caption_file()?;
        let mut caption_process = self.caption_process.lock().expect("caption process lock");

        if let Some(child) = caption_process.as_mut() {
            if child.try_wait()?.is_none() {
                return Ok(());
            }
        }

        let settings = self.overlay_settings_service.prepare_overlay()?;
        write_caption_state(&self.caption_file, "", "Listening")?;
        let settings = serde_json::to_string(&settings)
            .map_err(|error| crate::app_error::AppError::Window(error.to_string()))?;
        let mut command = Command::new(std::env::current_exe()?);
        if let Some(endpoint) = self.overlay_control.lock().unwrap().as_ref() {
            command
                .env("FEELSAY_OVERLAY_CONTROL", &endpoint.address)
                .env("FEELSAY_OVERLAY_TOKEN", &endpoint.token);
        }
        let child = command
            .arg("--caption-window-child")
            .env("FEELSAY_PARENT_PID", std::process::id().to_string())
            .env("FEELSAY_OVERLAY_SETTINGS", settings)
            .env(
                "FEELSAY_OVERLAY_SETTINGS_FILE",
                self.overlay_settings_service.runtime_settings_path(),
            )
            .env("FEELSAY_CAPTION_TEXT_FILE", &self.caption_file)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()?;

        *caption_process = Some(child);
        Ok(())
    }

    pub fn close_caption_process(&self) -> std::io::Result<()> {
        let mut caption_process = self.caption_process.lock().expect("caption process lock");

        if let Some(child) = caption_process.as_mut() {
            if child.try_wait()?.is_none() {
                child.kill()?;
                let _ = child.wait();
            }
        }

        *caption_process = None;
        Ok(())
    }

    pub fn caption_process_is_running(&self) -> std::io::Result<bool> {
        let mut caption_process = self.caption_process.lock().expect("caption process lock");

        if let Some(child) = caption_process.as_mut() {
            if child.try_wait()?.is_none() {
                return Ok(true);
            }
        }

        *caption_process = None;
        Ok(false)
    }

    pub fn toggle_active_profile_click_through(&self) -> Result<bool, crate::app_error::AppError> {
        self.overlay_settings_service.toggle_click_through()
    }

    pub fn start_overlay_placement(
        &self,
        settings: OverlaySettings,
    ) -> Result<OverlayPlacement, crate::app_error::AppError> {
        self.stop_overlay_placement()?;

        let settings = settings.normalized();
        let placement = OverlayPlacement::from_settings(&settings);
        self.write_overlay_placement(placement)?;

        let settings = serde_json::to_string(&settings)
            .map_err(|error| crate::app_error::AppError::Window(error.to_string()))?;
        let child = Command::new(std::env::current_exe()?)
            .arg("--caption-placement-child")
            .env("FEELSAY_OVERLAY_SETTINGS", settings)
            .env("FEELSAY_OVERLAY_PLACEMENT_FILE", &self.placement_file)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()?;

        let mut placement_process = self
            .placement_process
            .lock()
            .expect("placement process lock");
        *placement_process = Some(child);

        Ok(placement)
    }

    pub fn get_overlay_placement(
        &self,
    ) -> Result<Option<OverlayPlacement>, crate::app_error::AppError> {
        let is_running = self.placement_process_is_running()?;

        if !self.placement_file.exists() {
            return Ok(None);
        }

        let content = fs::read_to_string(&self.placement_file)?;
        let placement = serde_json::from_str::<OverlayPlacement>(&content)
            .map_err(|error| crate::app_error::AppError::Io(error.to_string()))?;

        if !is_running && !placement.is_accepted {
            let _ = fs::remove_file(&self.placement_file);
            return Ok(None);
        }

        Ok(Some(placement))
    }

    pub fn stop_overlay_placement(&self) -> std::io::Result<()> {
        let mut placement_process = self
            .placement_process
            .lock()
            .expect("placement process lock");

        if let Some(child) = placement_process.as_mut() {
            if child.try_wait()?.is_none() {
                child.kill()?;
                let _ = child.wait();
            }
        }

        *placement_process = None;

        match fs::remove_file(&self.placement_file) {
            Ok(()) => Ok(()),
            Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(()),
            Err(error) => Err(error),
        }
    }

    fn placement_process_is_running(&self) -> std::io::Result<bool> {
        let mut placement_process = self
            .placement_process
            .lock()
            .expect("placement process lock");

        if let Some(child) = placement_process.as_mut() {
            if child.try_wait()?.is_none() {
                return Ok(true);
            }
        }

        *placement_process = None;
        Ok(false)
    }

    fn write_overlay_placement(&self, placement: OverlayPlacement) -> std::io::Result<()> {
        if let Some(parent) = self.placement_file.parent() {
            fs::create_dir_all(parent)?;
        }

        let content = serde_json::to_string(&placement).map_err(io::Error::other)?;
        fs::write(&self.placement_file, content)
    }
}

fn normalize_source_label(label: String) -> Option<String> {
    let label = label.split_whitespace().collect::<Vec<_>>().join(" ");
    (!label.is_empty()).then_some(label)
}

impl Default for AppState {
    fn default() -> Self {
        Self::new(std::env::temp_dir().join("feelsay"))
    }
}
