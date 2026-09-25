use crate::app_error::AppError;
use serde::{Deserialize, Serialize};
use std::{fs, path::PathBuf, process::Command};

const FILE_NAME: &str = "translation-settings.json";
const DEFAULT_ARGOS_EXECUTABLE: &str = "argos-translate";

pub trait TranslationEngine {
    fn engine_id(&self) -> &'static str;
}

#[derive(Debug, Clone)]
pub struct TranslationSettingsService {
    path: PathBuf,
}

impl TranslationSettingsService {
    pub fn new(data_dir: PathBuf) -> Self {
        Self {
            path: data_dir.join(FILE_NAME),
        }
    }

    pub fn load(&self) -> Result<TranslationSettings, AppError> {
        if !self.path.exists() {
            return Ok(TranslationSettings::default());
        }

        let content = fs::read_to_string(&self.path)?;
        let content = content.trim_start_matches('\u{feff}');
        if content.trim().is_empty() {
            return Ok(TranslationSettings::default());
        }

        let settings = serde_json::from_str::<TranslationSettings>(content).map_err(|error| {
            AppError::Io(format!(
                "could not read translation settings at {}: {error}",
                self.path.display()
            ))
        })?;

        Ok(settings.normalized())
    }

    pub fn save(&self, settings: TranslationSettings) -> Result<TranslationSettings, AppError> {
        let settings = settings.normalized();

        if let Some(parent) = self.path.parent() {
            fs::create_dir_all(parent)?;
        }

        let content = serde_json::to_string_pretty(&settings)
            .map_err(|error| AppError::Io(error.to_string()))?;
        crate::persistence::write_bytes(&self.path, content.as_bytes())?;

        Ok(settings)
    }

    pub fn status(&self) -> TranslationEngineStatus {
        self.load()
            .map(|settings| settings.status())
            .unwrap_or_else(|error| TranslationEngineStatus {
                engine: TranslationEngineKind::ArgosCli,
                executable_path: DEFAULT_ARGOS_EXECUTABLE.to_string(),
                is_available: false,
                message: error.to_string(),
            })
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub struct TranslationSettings {
    #[serde(default)]
    pub engine: TranslationEngineKind,
    #[serde(default = "default_argos_executable_path")]
    pub executable_path: String,
}

impl TranslationSettings {
    pub fn normalized(mut self) -> Self {
        self.executable_path = self.executable_path.trim().to_string();
        if self.executable_path.is_empty() {
            self.executable_path = DEFAULT_ARGOS_EXECUTABLE.to_string();
        }
        self
    }

    pub fn status(&self) -> TranslationEngineStatus {
        let settings = self.clone().normalized();
        let output = Command::new(&settings.executable_path)
            .arg("--help")
            .output();

        match output {
            Ok(output) if output.status.success() => TranslationEngineStatus {
                engine: settings.engine,
                executable_path: settings.executable_path,
                is_available: true,
                message: "Ready".to_string(),
            },
            Ok(output) => TranslationEngineStatus {
                engine: settings.engine,
                executable_path: settings.executable_path,
                is_available: false,
                message: String::from_utf8_lossy(&output.stderr).trim().to_string(),
            },
            Err(error) => TranslationEngineStatus {
                engine: settings.engine,
                executable_path: settings.executable_path,
                is_available: false,
                message: error.to_string(),
            },
        }
    }
}

impl Default for TranslationSettings {
    fn default() -> Self {
        Self {
            engine: TranslationEngineKind::ArgosCli,
            executable_path: DEFAULT_ARGOS_EXECUTABLE.to_string(),
        }
    }
}

#[derive(Debug, Clone, Copy, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum TranslationEngineKind {
    #[default]
    ArgosCli,
}

#[derive(Debug, Clone, Copy, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum TranslationLanguage {
    #[default]
    Auto,
    English,
    Spanish,
    French,
    German,
    Italian,
    Portuguese,
    Japanese,
    Korean,
    Chinese,
    Arabic,
    Polish,
    Dutch,
    Ukrainian,
}

impl TranslationLanguage {
    pub fn code(self) -> Option<&'static str> {
        match self {
            Self::Auto => None,
            Self::English => Some("en"),
            Self::Spanish => Some("es"),
            Self::French => Some("fr"),
            Self::German => Some("de"),
            Self::Italian => Some("it"),
            Self::Portuguese => Some("pt"),
            Self::Japanese => Some("ja"),
            Self::Korean => Some("ko"),
            Self::Chinese => Some("zh"),
            Self::Arabic => Some("ar"),
            Self::Polish => Some("pl"),
            Self::Dutch => Some("nl"),
            Self::Ukrainian => Some("uk"),
        }
    }

    pub fn is_english(self) -> bool {
        self == Self::English
    }
}

#[derive(Debug, Clone)]
pub struct TranslationRuntimeConfig {
    settings: TranslationSettings,
    source_language: TranslationLanguage,
    target_language: TranslationLanguage,
}

impl TranslationRuntimeConfig {
    pub fn new(
        settings: TranslationSettings,
        source_language: TranslationLanguage,
        target_language: TranslationLanguage,
    ) -> Self {
        Self {
            settings: settings.normalized(),
            source_language,
            target_language,
        }
    }

    pub fn target_language(&self) -> TranslationLanguage {
        self.target_language
    }

    pub fn source_language(&self) -> TranslationLanguage {
        self.source_language
    }

    pub fn translate_text(&self, text: &str) -> Result<String, AppError> {
        ArgosCliTranslationEngine::new(self.settings.executable_path.clone()).translate(
            self.source_language,
            self.target_language,
            text,
        )
    }
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct TranslationEngineStatus {
    pub engine: TranslationEngineKind,
    pub executable_path: String,
    pub is_available: bool,
    pub message: String,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct TranslationDiagnosticResult {
    pub translated_text: String,
}

struct ArgosCliTranslationEngine {
    executable_path: String,
}

impl ArgosCliTranslationEngine {
    fn new(executable_path: String) -> Self {
        Self { executable_path }
    }

    fn translate(
        &self,
        source_language: TranslationLanguage,
        target_language: TranslationLanguage,
        text: &str,
    ) -> Result<String, AppError> {
        let text = text.trim();
        if text.is_empty() {
            return Ok(String::new());
        }

        if source_language == target_language && source_language.code().is_some() {
            return Ok(text.to_string());
        }

        let source_code = source_language.code().ok_or_else(|| {
            AppError::Translation(
                "text translation needs a source language in Settings -> Translation".to_string(),
            )
        })?;
        let target_code = target_language.code().ok_or_else(|| {
            AppError::Translation(
                "text translation needs a target language in Settings -> Translation".to_string(),
            )
        })?;

        let output = Command::new(&self.executable_path)
            .arg("--from-lang")
            .arg(source_code)
            .arg("--to-lang")
            .arg(target_code)
            .arg(text)
            .output()
            .map_err(|error| {
                AppError::Translation(format!("could not run Argos Translate executable: {error}"))
            })?;

        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr);
            return Err(AppError::Translation(format!(
                "Argos Translate failed: {}",
                stderr.trim()
            )));
        }

        let translated_text = String::from_utf8_lossy(&output.stdout).trim().to_string();
        if translated_text.is_empty() {
            return Err(AppError::Translation(
                "Argos Translate returned no text".to_string(),
            ));
        }

        Ok(translated_text)
    }
}

impl TranslationEngine for ArgosCliTranslationEngine {
    fn engine_id(&self) -> &'static str {
        "argos-cli"
    }
}

pub fn run_translation_diagnostic(
    settings: TranslationSettings,
    source_language: TranslationLanguage,
    target_language: TranslationLanguage,
) -> Result<TranslationDiagnosticResult, AppError> {
    let source_language = if source_language == TranslationLanguage::Auto {
        TranslationLanguage::English
    } else {
        source_language
    };
    let target_language = if target_language == TranslationLanguage::Auto {
        TranslationLanguage::Spanish
    } else {
        target_language
    };

    let runtime = TranslationRuntimeConfig::new(settings, source_language, target_language);
    let translated_text = runtime.translate_text(sample_text(source_language))?;

    Ok(TranslationDiagnosticResult { translated_text })
}

fn sample_text(language: TranslationLanguage) -> &'static str {
    match language {
        TranslationLanguage::Spanish => "Hola mundo",
        TranslationLanguage::French => "Bonjour le monde",
        TranslationLanguage::German => "Hallo Welt",
        TranslationLanguage::Italian => "Ciao mondo",
        TranslationLanguage::Portuguese => "Ola mundo",
        TranslationLanguage::Japanese => "\u{3053}\u{3093}\u{306b}\u{3061}\u{306f}\u{4e16}\u{754c}",
        TranslationLanguage::Korean => "\u{c548}\u{b155}\u{d558}\u{c138}\u{c694} \u{c138}\u{acc4}",
        TranslationLanguage::Chinese => "\u{4f60}\u{597d}\u{4e16}\u{754c}",
        TranslationLanguage::Arabic => "\u{0645}\u{0631}\u{062d}\u{0628}\u{0627} \u{0628}\u{0627}\u{0644}\u{0639}\u{0627}\u{0644}\u{0645}",
        TranslationLanguage::Polish => "Witaj swiecie",
        TranslationLanguage::Dutch => "Hallo wereld",
        TranslationLanguage::Ukrainian => "\u{041f}\u{0440}\u{0438}\u{0432}\u{0456}\u{0442} \u{0441}\u{0432}\u{0456}\u{0442}",
        TranslationLanguage::Auto | TranslationLanguage::English => "Hello world",
    }
}

fn default_argos_executable_path() -> String {
    DEFAULT_ARGOS_EXECUTABLE.to_string()
}

pub fn default_translation_source_language() -> TranslationLanguage {
    TranslationLanguage::Auto
}

pub fn default_translation_target_language() -> TranslationLanguage {
    TranslationLanguage::English
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn translation_settings_default_to_argos_cli() {
        let settings = TranslationSettings::default();

        assert_eq!(settings.engine, TranslationEngineKind::ArgosCli);
        assert_eq!(settings.executable_path, "argos-translate");
    }

    #[test]
    fn translation_language_codes_match_argos_cli() {
        assert_eq!(TranslationLanguage::English.code(), Some("en"));
        assert_eq!(TranslationLanguage::Spanish.code(), Some("es"));
        assert_eq!(TranslationLanguage::Auto.code(), None);
    }
}
