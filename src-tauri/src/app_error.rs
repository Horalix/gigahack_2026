use serde::Serialize;
use std::{fmt, io};

#[derive(Debug)]
pub enum AppError {
    Asr(String),
    Audio(String),
    Io(String),
    Translation(String),
    Window(String),
}

impl AppError {
    pub fn user_message(&self) -> String {
        match self {
            Self::Audio(message) if mentions(message, &["default output changed"]) => {
                "Your playback device changed. Press Start to use the new device.".into()
            }
            Self::Audio(message) if mentions(message, &["application closed"]) => {
                "The selected application closed. Open it and select it again, or use system audio.".into()
            }
            Self::Asr(message) if mentions(message, &["translation requires", "multilingual"]) => {
                "Translation needs the multilingual speech model. Open Settings → Captions and repair the speech model.".to_string()
            }
            Self::Asr(message) if mentions(message, &["executable", "whisper.cpp"]) => {
                "Speech recognition is not ready. Open Settings → Captions and download the speech model.".to_string()
            }
            Self::Asr(message) if mentions(message, &["model file", "missing model", "does not exist"]) => {
                "The speech model is missing. Open Settings → Captions and download the speech model.".to_string()
            }
            Self::Asr(_) => {
                "Speech recognition stopped. Open Settings → Captions and repair the speech model, then try again.".to_string()
            }
            Self::Audio(message) if mentions(message, &["device", "endpoint", "not found"]) => {
                "The selected audio device is not available. Select a different source or reconnect the device.".to_string()
            }
            Self::Audio(message) if mentions(message, &["windows-only", "unsupported"]) => {
                "This capture source is not supported on this platform yet. Use microphone or system audio on Windows.".to_string()
            }
            Self::Audio(_) => {
                "Audio capture could not start. Check the selected source and try again.".to_string()
            }
            Self::Io(message) if mentions(message, &["permission", "access", "denied"]) => {
                "Feelsay could not access local app data. Check folder permissions and try again.".to_string()
            }
            Self::Io(message) if message.starts_with("Speech model ") || message.starts_with("Transcript ") => message.clone(),
            Self::Io(_) => {
                "Feelsay could not read or write local app data. Restart the app and try again.".to_string()
            }
            Self::Translation(message) if mentions(message, &["source language"]) => {
                "Choose a source language in Settings -> Translation, then try again.".to_string()
            }
            Self::Translation(message) if mentions(message, &["argos", "executable"]) => {
                "Local translation is not ready. Install Argos Translate and its language package, or set the executable in Settings -> Translation.".to_string()
            }
            Self::Translation(_) => {
                "Local translation failed. Check Settings -> Translation, then try again.".to_string()
            }
            Self::Window(_) => {
                "The caption window could not be opened or closed. Stop captions and try again.".to_string()
            }
        }
    }

    fn kind(&self) -> &'static str {
        match self {
            Self::Asr(_) => "asr",
            Self::Audio(_) => "audio",
            Self::Io(_) => "io",
            Self::Translation(_) => "translation",
            Self::Window(_) => "window",
        }
    }
}

impl fmt::Display for AppError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Asr(message) => write!(formatter, "asr error: {message}"),
            Self::Audio(message) => write!(formatter, "audio error: {message}"),
            Self::Io(message) => write!(formatter, "io error: {message}"),
            Self::Translation(message) => write!(formatter, "translation error: {message}"),
            Self::Window(message) => write!(formatter, "window error: {message}"),
        }
    }
}

impl std::error::Error for AppError {}

impl From<io::Error> for AppError {
    fn from(error: io::Error) -> Self {
        Self::Io(error.to_string())
    }
}

impl From<tauri::Error> for AppError {
    fn from(error: tauri::Error) -> Self {
        Self::Window(error.to_string())
    }
}

impl From<rusqlite::Error> for AppError {
    fn from(error: rusqlite::Error) -> Self {
        Self::Io(error.to_string())
    }
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CommandError {
    pub message: String,
}

impl From<AppError> for CommandError {
    fn from(error: AppError) -> Self {
        eprintln!("feelsay_error kind={} detail={error}", error.kind());

        Self {
            message: error.user_message(),
        }
    }
}

pub type CommandResult<T> = Result<T, CommandError>;

fn mentions(message: &str, needles: &[&str]) -> bool {
    let message = message.to_ascii_lowercase();
    needles
        .iter()
        .any(|needle| message.contains(&needle.to_ascii_lowercase()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn asr_model_errors_include_recovery_action() {
        let message = AppError::Asr("model file does not exist".to_string()).user_message();

        assert!(message.contains("Settings → Captions"));
        assert!(message.contains("download"));
    }

    #[test]
    fn audio_device_errors_include_recovery_action() {
        let message = AppError::Audio("endpoint not found".to_string()).user_message();

        assert!(message.contains("Select a different source"));
    }
}
