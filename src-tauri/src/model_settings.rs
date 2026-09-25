use crate::app_error::AppError;
use serde::{Deserialize, Serialize};
use std::{
    fs,
    io::{Read, Write},
    path::{Path, PathBuf},
    sync::{
        atomic::{AtomicU64, Ordering},
        Arc, Mutex,
    },
    time::Duration,
};

const FILE_NAME: &str = "model-settings.json";
const DEFAULT_MODEL_FILE: &str = "ggml-base.bin";
const DEFAULT_MODEL_URL: &str =
    "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin";
const DEFAULT_MODEL_SHA256: &str =
    "60ed5bc3dd14eea856493d334349b405782ddcaf0028d4b5df4088345fba2efe";
const DEFAULT_MODEL_BYTES: u64 = 147_951_465;

#[derive(Debug, Clone)]
pub struct ModelSettingsService {
    path: PathBuf,
    models_dir: PathBuf,
    install_lock: Arc<Mutex<()>>,
    download_progress: Arc<AtomicU64>,
}

impl ModelSettingsService {
    pub fn new(data_dir: PathBuf) -> Self {
        Self {
            path: data_dir.join(FILE_NAME),
            models_dir: data_dir.join("models"),
            install_lock: Arc::new(Mutex::new(())),
            download_progress: Arc::new(AtomicU64::new(u64::MAX)),
        }
    }

    pub fn load(&self) -> Result<ModelSettingsStore, AppError> {
        if !self.path.exists() {
            return Ok(ModelSettingsStore::default_for(&self.models_dir));
        }

        let content = fs::read_to_string(&self.path)?;
        let content = content.trim_start_matches('\u{feff}');
        let store = serde_json::from_str::<ModelSettingsStore>(content).map_err(|error| {
            AppError::Io(format!(
                "could not read model settings at {}: {error}",
                self.path.display()
            ))
        })?;

        Ok(store.normalized(&self.models_dir))
    }

    pub fn save(&self, store: ModelSettingsStore) -> Result<ModelSettingsStore, AppError> {
        let store = store.normalized(&self.models_dir);

        if let Some(parent) = self.path.parent() {
            fs::create_dir_all(parent)?;
        }

        let content = serde_json::to_string_pretty(&store)
            .map_err(|error| AppError::Io(error.to_string()))?;
        crate::persistence::write_bytes(&self.path, content.as_bytes())?;

        Ok(store)
    }

    pub fn status(&self) -> Result<ModelStatus, AppError> {
        let store = self.load()?;
        let mut status = ModelStatus::from_store(store);
        let progress = self.download_progress.load(Ordering::Relaxed);
        status.download_progress = (progress != u64::MAX).then_some(progress.min(100) as u8);
        Ok(status)
    }

    pub fn install_default_assets(&self) -> Result<ModelSettingsStore, AppError> {
        let _guard = self
            .install_lock
            .try_lock()
            .map_err(|_| AppError::Io("Speech model setup is already running.".into()))?;
        struct ResetProgress<'a>(&'a AtomicU64);
        impl Drop for ResetProgress<'_> {
            fn drop(&mut self) {
                self.0.store(u64::MAX, Ordering::Relaxed);
            }
        }
        self.download_progress.store(0, Ordering::Relaxed);
        let _progress = ResetProgress(&self.download_progress);
        fs::create_dir_all(&self.models_dir)?;
        let model_path = self.models_dir.join(DEFAULT_MODEL_FILE);
        if !valid_default_model(&model_path) {
            download_file(DEFAULT_MODEL_URL, &model_path, &self.download_progress)?;
        }

        let mut store = self.load()?;
        let model_index = store
            .models
            .iter()
            .position(|model| model.id == "whisper-base")
            .or(if store.models.is_empty() {
                None
            } else {
                Some(0)
            })
            .ok_or_else(|| AppError::Io("no model slot is available".to_string()))?;
        let model = &mut store.models[model_index];

        model.id = "whisper-base".to_string();
        model.name = "Whisper Base Multilingual".to_string();
        model.language = Some("Multilingual".to_string());
        model.path = model_path.to_string_lossy().to_string();
        model.executable_path = None;
        model.checksum_sha256 = Some(DEFAULT_MODEL_SHA256.into());
        model.is_installed = true;
        model.file_size_bytes = file_size(&model.path);
        store.active_model_id = model.id.clone();

        self.save(store)
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ModelSettingsStore {
    pub active_model_id: String,
    pub models_dir: String,
    pub models: Vec<ModelMetadata>,
}

impl ModelSettingsStore {
    fn default_for(models_dir: &Path) -> Self {
        let default_path = models_dir.join(DEFAULT_MODEL_FILE);

        Self {
            active_model_id: "whisper-base".to_string(),
            models_dir: models_dir.to_string_lossy().to_string(),
            models: vec![ModelMetadata {
                id: "whisper-base".to_string(),
                name: "Whisper Base Multilingual".to_string(),
                runtime: "whisper.cpp".to_string(),
                language: Some("Multilingual".to_string()),
                path: default_path.to_string_lossy().to_string(),
                checksum_sha256: None,
                executable_path: None,
                file_size_bytes: None,
                is_installed: default_path.exists(),
                is_default: true,
                supports_translation: true,
            }],
        }
    }

    fn normalized(mut self, models_dir: &Path) -> Self {
        let fallback = Self::default_for(models_dir);

        if self.models_dir.trim().is_empty() {
            self.models_dir = fallback.models_dir;
        }

        if self.models.is_empty() {
            self.models = fallback.models;
        }

        for model in &mut self.models {
            let default_path = models_dir.join(DEFAULT_MODEL_FILE);
            let default_path = default_path.to_string_lossy();
            model.id = normalize_text(&model.id, "whisper-base");
            model.name = normalize_text(&model.name, "Whisper Base Multilingual");
            model.runtime = normalize_text(&model.runtime, "whisper.cpp");
            model.path = normalize_text(&model.path, &default_path);
            model.executable_path = normalize_optional_path(model.executable_path.as_deref());
            model.is_installed = Path::new(&model.path).exists();
            model.file_size_bytes = file_size(&model.path);
            model.supports_translation = model_supports_translation(model);
        }

        if !self
            .models
            .iter()
            .any(|model| model.id == self.active_model_id)
        {
            self.active_model_id = self.models[0].id.clone();
        }

        self
    }

    pub fn active_model(&self) -> Option<&ModelMetadata> {
        self.models
            .iter()
            .find(|model| model.id == self.active_model_id)
            .or_else(|| self.models.first())
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ModelMetadata {
    pub id: String,
    pub name: String,
    pub runtime: String,
    pub language: Option<String>,
    pub path: String,
    pub checksum_sha256: Option<String>,
    #[serde(default)]
    pub executable_path: Option<String>,
    pub file_size_bytes: Option<u64>,
    pub is_installed: bool,
    pub is_default: bool,
    #[serde(default)]
    pub supports_translation: bool,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ModelStatus {
    pub download_progress: Option<u8>,
    pub active_model: Option<ModelMetadata>,
    pub models_dir: String,
    pub is_ready: bool,
    pub message: String,
}

impl ModelStatus {
    fn from_store(store: ModelSettingsStore) -> Self {
        let active_model = store.active_model().cloned();
        let is_ready = active_model
            .as_ref()
            .map(model_runtime_ready)
            .unwrap_or(false);
        let message = match (is_ready, active_model.as_ref()) {
            (true, Some(model)) => format!("{} is ready.", model.name),
            (false, Some(model)) if model.is_installed && missing_runtime(model) => {
                "Missing whisper.cpp executable.".to_string()
            }
            (false, Some(model)) => format!("Missing model: {}", model.name),
            _ => "No ASR model configured.".to_string(),
        };

        Self {
            active_model,
            download_progress: None,
            models_dir: store.models_dir,
            is_ready,
            message,
        }
    }
}

fn normalize_text(value: &str, fallback: &str) -> String {
    let value = value.trim();
    if value.is_empty() {
        fallback.to_string()
    } else {
        value.to_string()
    }
}

fn normalize_optional_path(value: Option<&str>) -> Option<String> {
    let value = value?.trim();
    if value.is_empty() {
        None
    } else {
        Some(value.to_string())
    }
}

fn file_size(path: &str) -> Option<u64> {
    fs::metadata(path).ok().map(|metadata| metadata.len())
}

pub fn model_supports_translation(model: &ModelMetadata) -> bool {
    let joined = [
        model.id.as_str(),
        model.name.as_str(),
        model.language.as_deref().unwrap_or(""),
        Path::new(&model.path)
            .file_name()
            .and_then(|file_name| file_name.to_str())
            .unwrap_or(""),
    ]
    .join(" ")
    .to_ascii_lowercase();

    !joined.contains(".en.")
        && !joined.contains(" english")
        && !joined.contains("english ")
        && !joined.ends_with("english")
        && !joined.contains("-en")
}

fn valid_default_model(path: &Path) -> bool {
    use sha2::{Digest, Sha256};
    let Ok(mut file) = fs::File::open(path) else {
        return false;
    };
    if file
        .metadata()
        .map_or(true, |meta| meta.len() != DEFAULT_MODEL_BYTES)
    {
        return false;
    }
    let mut hash = Sha256::new();
    let mut buffer = [0u8; 65_536];
    loop {
        match file.read(&mut buffer) {
            Ok(0) => break,
            Ok(count) => hash.update(&buffer[..count]),
            Err(_) => return false,
        }
    }
    format!("{:x}", hash.finalize()) == DEFAULT_MODEL_SHA256
}

fn download_file(url: &str, path: &Path, progress: &AtomicU64) -> Result<(), AppError> {
    let temporary = path.with_extension("download");
    let result = (|| -> Result<(), AppError> {
        let client = reqwest::blocking::Client::builder()
            .connect_timeout(Duration::from_secs(20))
            .timeout(Duration::from_secs(600))
            .https_only(true)
            .build()
            .map_err(|error| AppError::Io(error.to_string()))?;
        let mut response = client
            .get(url)
            .send()
            .and_then(|response| response.error_for_status())
            .map_err(|_| {
                AppError::Io(
                    "Speech model download failed. Check your connection and try again.".into(),
                )
            })?;
        let mut output = fs::File::create(&temporary)?;
        let mut copied = 0;
        let mut buffer = [0u8; 65_536];
        loop {
            let count = response.read(&mut buffer)?;
            if count == 0 {
                break;
            }
            copied += count as u64;
            if copied > DEFAULT_MODEL_BYTES {
                return Err(AppError::Io(
                    "Speech model download had an unexpected size. Please try again.".into(),
                ));
            }
            output.write_all(&buffer[..count])?;
            progress.store(copied * 100 / DEFAULT_MODEL_BYTES, Ordering::Relaxed);
        }
        output.flush()?;
        output.sync_all()?;
        drop(output);
        if copied != DEFAULT_MODEL_BYTES || !valid_default_model(&temporary) {
            return Err(AppError::Io(
                "Speech model download was incomplete. Please try again.".into(),
            ));
        }
        fs::rename(&temporary, path)?;
        Ok(())
    })();
    if temporary.exists() {
        let _ = fs::remove_file(&temporary);
    }
    result
}

fn model_runtime_ready(model: &ModelMetadata) -> bool {
    if !model.is_installed {
        return false;
    }

    #[cfg(feature = "local-asr")]
    {
        true
    }

    #[cfg(not(feature = "local-asr"))]
    {
        !missing_runtime(model)
    }
}

fn missing_runtime(model: &ModelMetadata) -> bool {
    !model
        .executable_path
        .as_deref()
        .map(|path| Path::new(path).exists())
        .unwrap_or(false)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    #[ignore = "downloads the official model; requires FEELSAY_RUN_DOWNLOAD_TEST=1"]
    fn default_model_setup_repairs_and_reuses_verified_download() {
        assert_eq!(
            std::env::var("FEELSAY_RUN_DOWNLOAD_TEST").as_deref(),
            Ok("1")
        );
        let suffix = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!(
            "feelsay-model-download-test-{}-{suffix}",
            std::process::id()
        ));
        assert!(!root.exists());
        let service = ModelSettingsService::new(root.clone());
        fs::create_dir_all(&service.models_dir).unwrap();
        let model = service.models_dir.join(DEFAULT_MODEL_FILE);
        fs::write(&model, b"incomplete model fixture").unwrap();
        println!(
            "Downloading and verifying the official speech model into an isolated test directory."
        );
        service.install_default_assets().unwrap();
        assert!(valid_default_model(&model));
        assert!(service.status().unwrap().is_ready);
        assert!(service.status().unwrap().download_progress.is_none());
        let modified = fs::metadata(&model).unwrap().modified().unwrap();
        service.install_default_assets().unwrap();
        assert_eq!(
            fs::metadata(&model).unwrap().modified().unwrap(),
            modified,
            "verified cache must be reused"
        );
        assert!(
            ModelSettingsService::new(root.clone())
                .status()
                .unwrap()
                .is_ready
        );
        assert!(!model.with_extension("download").exists());
        fs::remove_file(model).unwrap();
        fs::remove_file(&service.path).unwrap();
        fs::remove_dir(&service.models_dir).unwrap();
        fs::remove_dir(root).unwrap();
    }

    fn model(path: &str, language: Option<&str>) -> ModelMetadata {
        ModelMetadata {
            id: "test".to_string(),
            name: "Test model".to_string(),
            runtime: "whisper.cpp".to_string(),
            language: language.map(str::to_string),
            path: path.to_string(),
            checksum_sha256: None,
            executable_path: None,
            file_size_bytes: None,
            is_installed: false,
            is_default: false,
            supports_translation: false,
        }
    }

    #[test]
    fn english_only_models_do_not_support_translation() {
        assert!(!model_supports_translation(&model(
            "C:/models/ggml-base.en.bin",
            Some("English"),
        )));
    }

    #[test]
    fn multilingual_models_support_translation() {
        assert!(model_supports_translation(&model(
            "C:/models/ggml-base.bin",
            Some("Multilingual"),
        )));
    }
}
