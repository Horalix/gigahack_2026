use crate::app_error::AppError;
use serde::{Deserialize, Serialize};
use std::{fs, path::PathBuf};

const FILE_NAME: &str = "performance-settings.json";

#[derive(Debug, Clone)]
pub struct PerformanceSettingsService {
    path: PathBuf,
}

impl PerformanceSettingsService {
    pub fn new(data_dir: PathBuf) -> Self {
        Self {
            path: data_dir.join(FILE_NAME),
        }
    }

    pub fn load(&self) -> Result<PerformanceSettings, AppError> {
        if !self.path.exists() {
            return Ok(PerformanceSettings::default().normalized());
        }

        let content = fs::read_to_string(&self.path)?;
        let content = content.trim_start_matches('\u{feff}');
        if content.trim().is_empty() {
            return Ok(PerformanceSettings::default().normalized());
        }

        let settings = serde_json::from_str::<PerformanceSettings>(content).map_err(|error| {
            AppError::Io(format!(
                "could not read performance settings at {}: {error}",
                self.path.display()
            ))
        })?;

        Ok(settings.normalized())
    }

    pub fn save(&self, settings: PerformanceSettings) -> Result<PerformanceSettings, AppError> {
        let settings = settings.normalized();

        if let Some(parent) = self.path.parent() {
            fs::create_dir_all(parent)?;
        }

        let content = serde_json::to_string_pretty(&settings)
            .map_err(|error| AppError::Io(error.to_string()))?;
        crate::persistence::write_bytes(&self.path, content.as_bytes())?;

        Ok(settings)
    }
}

#[derive(Debug, Clone, Copy, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum PerformancePreset {
    LowResource,
    #[default]
    Balanced,
    Accuracy,
    Custom,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct PerformanceSettings {
    #[serde(default)]
    pub preset: PerformancePreset,
    #[serde(default = "default_min_transcribe_seconds")]
    pub min_transcribe_seconds: f32,
    #[serde(default = "default_max_transcribe_seconds")]
    pub max_transcribe_seconds: f32,
    #[serde(default = "default_transcribe_interval_ms")]
    pub transcribe_interval_ms: u64,
    #[serde(default = "default_asr_queue_capacity")]
    pub asr_queue_capacity: usize,
    #[serde(default = "default_vad_speech_level_threshold")]
    pub vad_speech_level_threshold: f32,
    #[serde(default = "default_vad_silence_level_threshold")]
    pub vad_silence_level_threshold: f32,
    #[serde(default = "default_vad_speech_frames")]
    pub vad_speech_frames: u8,
    #[serde(default = "default_vad_silence_frames")]
    pub vad_silence_frames: u8,
    #[serde(default)]
    pub resource_impact: String,
}

impl PerformanceSettings {
    pub fn normalized(self) -> Self {
        let mut settings = match self.preset {
            PerformancePreset::LowResource => Self {
                preset: PerformancePreset::LowResource,
                min_transcribe_seconds: 5.0,
                max_transcribe_seconds: 10.0,
                transcribe_interval_ms: 2400,
                asr_queue_capacity: 2,
                vad_speech_level_threshold: 0.045,
                vad_silence_level_threshold: 0.024,
                vad_speech_frames: 3,
                vad_silence_frames: 8,
                resource_impact: String::new(),
            },
            PerformancePreset::Balanced => Self::balanced(),
            PerformancePreset::Accuracy => Self {
                preset: PerformancePreset::Accuracy,
                min_transcribe_seconds: 2.0,
                max_transcribe_seconds: 12.0,
                transcribe_interval_ms: 900,
                asr_queue_capacity: 6,
                vad_speech_level_threshold: 0.025,
                vad_silence_level_threshold: 0.014,
                vad_speech_frames: 2,
                vad_silence_frames: 10,
                resource_impact: String::new(),
            },
            PerformancePreset::Custom => Self {
                preset: PerformancePreset::Custom,
                min_transcribe_seconds: clamp_f32(self.min_transcribe_seconds, 1.0, 10.0),
                max_transcribe_seconds: clamp_f32(self.max_transcribe_seconds, 2.0, 20.0),
                transcribe_interval_ms: self.transcribe_interval_ms.clamp(500, 5000),
                asr_queue_capacity: self.asr_queue_capacity.clamp(1, 8),
                vad_speech_level_threshold: clamp_f32(self.vad_speech_level_threshold, 0.01, 0.12),
                vad_silence_level_threshold: clamp_f32(
                    self.vad_silence_level_threshold,
                    0.005,
                    0.08,
                ),
                vad_speech_frames: self.vad_speech_frames.clamp(1, 8),
                vad_silence_frames: self.vad_silence_frames.clamp(2, 24),
                resource_impact: String::new(),
            },
        };

        if settings.max_transcribe_seconds < settings.min_transcribe_seconds {
            settings.max_transcribe_seconds = settings.min_transcribe_seconds + 1.0;
        }

        if settings.vad_silence_level_threshold > settings.vad_speech_level_threshold {
            settings.vad_silence_level_threshold = settings.vad_speech_level_threshold * 0.5;
        }

        settings.resource_impact = settings.impact_label().to_string();
        settings
    }

    pub fn runtime(&self) -> PerformanceRuntimeConfig {
        let settings = self.clone().normalized();

        PerformanceRuntimeConfig {
            min_transcribe_samples: seconds_to_samples(settings.min_transcribe_seconds),
            max_transcribe_samples: seconds_to_samples(settings.max_transcribe_seconds),
            transcribe_interval_ms: settings.transcribe_interval_ms as u128,
            asr_queue_capacity: settings.asr_queue_capacity,
            vad: VadRuntimeConfig {
                speech_level_threshold: settings.vad_speech_level_threshold,
                silence_level_threshold: settings.vad_silence_level_threshold,
                speech_frames: settings.vad_speech_frames,
                silence_frames: settings.vad_silence_frames,
            },
        }
    }

    fn balanced() -> Self {
        Self {
            preset: PerformancePreset::Balanced,
            min_transcribe_seconds: default_min_transcribe_seconds(),
            max_transcribe_seconds: default_max_transcribe_seconds(),
            transcribe_interval_ms: default_transcribe_interval_ms(),
            asr_queue_capacity: default_asr_queue_capacity(),
            vad_speech_level_threshold: default_vad_speech_level_threshold(),
            vad_silence_level_threshold: default_vad_silence_level_threshold(),
            vad_speech_frames: default_vad_speech_frames(),
            vad_silence_frames: default_vad_silence_frames(),
            resource_impact: String::new(),
        }
    }

    fn impact_label(&self) -> &'static str {
        match self.preset {
            PerformancePreset::LowResource => "Lowest CPU use. Slower updates.",
            PerformancePreset::Balanced => "Good default. Moderate CPU use.",
            PerformancePreset::Accuracy => "More responsive captions. Higher CPU use.",
            PerformancePreset::Custom => "Custom tuning.",
        }
    }
}

impl Default for PerformanceSettings {
    fn default() -> Self {
        Self::balanced()
    }
}

#[derive(Debug, Clone)]
pub struct PerformanceRuntimeConfig {
    pub min_transcribe_samples: usize,
    pub max_transcribe_samples: usize,
    pub transcribe_interval_ms: u128,
    pub asr_queue_capacity: usize,
    pub vad: VadRuntimeConfig,
}

impl Default for PerformanceRuntimeConfig {
    fn default() -> Self {
        PerformanceSettings::default().runtime()
    }
}

#[derive(Debug, Clone, Copy)]
pub struct VadRuntimeConfig {
    pub speech_level_threshold: f32,
    pub silence_level_threshold: f32,
    pub speech_frames: u8,
    pub silence_frames: u8,
}

impl Default for VadRuntimeConfig {
    fn default() -> Self {
        PerformanceSettings::default().runtime().vad
    }
}

fn seconds_to_samples(seconds: f32) -> usize {
    (16_000.0 * seconds).round() as usize
}

fn clamp_f32(value: f32, min: f32, max: f32) -> f32 {
    if value.is_finite() {
        value.clamp(min, max)
    } else {
        min
    }
}

fn default_min_transcribe_seconds() -> f32 {
    1.5
}

fn default_max_transcribe_seconds() -> f32 {
    6.0
}

fn default_transcribe_interval_ms() -> u64 {
    1400
}

fn default_asr_queue_capacity() -> usize {
    4
}

fn default_vad_speech_level_threshold() -> f32 {
    0.006
}

fn default_vad_silence_level_threshold() -> f32 {
    0.0035
}

fn default_vad_speech_frames() -> u8 {
    2
}

fn default_vad_silence_frames() -> u8 {
    8
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn balanced_uses_short_live_chunks() {
        let runtime = PerformanceSettings::default().normalized().runtime();

        assert_eq!(runtime.min_transcribe_samples, 24_000);
        assert_eq!(runtime.max_transcribe_samples, 16_000 * 6);
        assert_eq!(runtime.transcribe_interval_ms, 1400);
        assert_eq!(runtime.asr_queue_capacity, 4);
    }

    #[test]
    fn custom_settings_are_clamped() {
        let settings = PerformanceSettings {
            preset: PerformancePreset::Custom,
            min_transcribe_seconds: -1.0,
            max_transcribe_seconds: 1.0,
            transcribe_interval_ms: 10,
            asr_queue_capacity: 99,
            vad_speech_level_threshold: f32::NAN,
            vad_silence_level_threshold: 1.0,
            vad_speech_frames: 0,
            vad_silence_frames: 1,
            resource_impact: String::new(),
        }
        .normalized();

        assert_eq!(settings.min_transcribe_seconds, 1.0);
        assert_eq!(settings.max_transcribe_seconds, 2.0);
        assert_eq!(settings.transcribe_interval_ms, 500);
        assert_eq!(settings.asr_queue_capacity, 8);
        assert_eq!(settings.vad_speech_level_threshold, 0.01);
        assert_eq!(settings.vad_speech_frames, 1);
        assert_eq!(settings.vad_silence_frames, 2);
    }
}
