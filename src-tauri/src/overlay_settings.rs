use crate::app_error::AppError;
use serde::{Deserialize, Serialize};
use std::{
    fs,
    path::PathBuf,
    sync::{Arc, Mutex},
};

const FILE_NAME: &str = "overlay-settings.json";
const RUNTIME_FILE_NAME: &str = "overlay-settings-runtime.json";
const PROFILE_COUNT: usize = 5;
fn default_always_on_top() -> bool {
    true
}

#[derive(Debug, Clone)]
pub struct OverlaySettingsService {
    path: PathBuf,
    runtime_path: PathBuf,
    writer: Arc<Mutex<()>>,
}

impl OverlaySettingsService {
    pub fn new(data_dir: PathBuf) -> Self {
        Self {
            path: data_dir.join(FILE_NAME),
            runtime_path: data_dir.join(RUNTIME_FILE_NAME),
            writer: Arc::new(Mutex::new(())),
        }
    }

    pub fn load(&self) -> Result<OverlaySettings, AppError> {
        Ok(self.load_store()?.active_settings().clone())
    }

    pub fn save(&self, settings: OverlaySettings) -> Result<OverlaySettings, AppError> {
        let _guard = self.writer.lock().unwrap();
        let mut store = self.load_store()?;
        store.set_active_settings(settings);
        let store = self.write_store(store)?;
        Ok(store.active_settings().clone())
    }

    pub fn load_store(&self) -> Result<OverlaySettingsStore, AppError> {
        if !self.path.exists() {
            return Ok(OverlaySettingsStore::default());
        }

        let content = fs::read_to_string(&self.path)?;

        if let Ok(store) = serde_json::from_str::<OverlaySettingsStore>(&content) {
            return Ok(store.normalized());
        }

        let settings = serde_json::from_str::<OverlaySettings>(&content)
            .map_err(|error| AppError::Io(error.to_string()))?;

        Ok(OverlaySettingsStore::from_legacy_settings(settings))
    }

    pub fn save_store(
        &self,
        store: OverlaySettingsStore,
    ) -> Result<OverlaySettingsStore, AppError> {
        let _guard = self.writer.lock().unwrap();
        self.write_store(store)
    }

    fn write_store(&self, store: OverlaySettingsStore) -> Result<OverlaySettingsStore, AppError> {
        let store = store.normalized();

        if let Some(parent) = self.path.parent() {
            fs::create_dir_all(parent)?;
        }

        let content = serde_json::to_string_pretty(&store)
            .map_err(|error| AppError::Io(error.to_string()))?;
        crate::persistence::write_bytes(&self.path, content.as_bytes())?;
        self.write_runtime_settings(store.active_settings())?;

        Ok(store)
    }

    pub fn select_profile(
        &self,
        profile_id: OverlayProfileId,
    ) -> Result<OverlaySettingsStore, AppError> {
        let _guard = self.writer.lock().unwrap();
        let mut store = self.load_store()?;
        store.active_profile_id = profile_id;
        self.write_store(store)
    }

    pub fn patch(
        &self,
        profile_id: Option<OverlayProfileId>,
        patch: serde_json::Value,
    ) -> Result<OverlaySettingsStore, AppError> {
        let _guard = self.writer.lock().unwrap();
        let mut store = self.load_store()?;
        let id = profile_id.unwrap_or(store.active_profile_id);
        let profile = store
            .profiles
            .iter_mut()
            .find(|profile| profile.id == id)
            .ok_or_else(|| AppError::Io("Overlay profile is unavailable.".into()))?;
        let mut settings = serde_json::to_value(&profile.settings)
            .map_err(|error| AppError::Io(error.to_string()))?;
        let fields = patch
            .as_object()
            .ok_or_else(|| AppError::Io("Invalid overlay settings change.".into()))?;
        for (key, value) in fields {
            let target = settings
                .get_mut(key)
                .ok_or_else(|| AppError::Io("Unknown overlay setting.".into()))?;
            *target = value.clone();
        }
        profile.settings = serde_json::from_value::<OverlaySettings>(settings)
            .map_err(|error| AppError::Io(error.to_string()))?
            .normalized();
        self.write_store(store)
    }

    pub fn toggle_click_through(&self) -> Result<bool, AppError> {
        let _guard = self.writer.lock().unwrap();
        let mut store = self.load_store()?;
        let mut settings = store.active_settings().clone();
        settings.click_through = !settings.click_through;
        let enabled = settings.click_through;
        store.set_active_settings(settings);
        self.write_store(store)?;
        Ok(enabled)
    }

    pub fn runtime_settings_path(&self) -> &std::path::Path {
        &self.runtime_path
    }

    pub fn prepare_overlay(&self) -> Result<OverlaySettings, AppError> {
        let _guard = self.writer.lock().unwrap();
        let settings = self.load()?;
        self.write_runtime_settings(&settings)?;
        Ok(settings)
    }

    fn write_runtime_settings(&self, settings: &OverlaySettings) -> Result<(), AppError> {
        if let Some(parent) = self.runtime_path.parent() {
            fs::create_dir_all(parent)?;
        }

        let content = serde_json::to_string_pretty(&settings.clone().normalized())
            .map_err(|error| AppError::Io(error.to_string()))?;
        crate::persistence::write_bytes(&self.runtime_path, content.as_bytes())?;
        Ok(())
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct OverlaySettingsStore {
    pub active_profile_id: OverlayProfileId,
    pub profiles: Vec<OverlaySettingsProfile>,
}

impl OverlaySettingsStore {
    pub fn active_settings(&self) -> &OverlaySettings {
        self.profiles
            .iter()
            .find(|profile| profile.id == self.active_profile_id)
            .map(|profile| &profile.settings)
            .unwrap_or(&self.profiles[0].settings)
    }

    pub fn set_active_settings(&mut self, settings: OverlaySettings) {
        let active_profile_id = self.active_profile_id;

        if let Some(profile) = self
            .profiles
            .iter_mut()
            .find(|profile| profile.id == active_profile_id)
        {
            profile.settings = settings;
        }
    }

    fn from_legacy_settings(settings: OverlaySettings) -> Self {
        let mut store = Self::default();

        if let Some(profile) = store
            .profiles
            .iter_mut()
            .find(|profile| profile.id == OverlayProfileId::Profile1)
        {
            profile.settings = settings;
        }

        store.normalized()
    }

    fn normalized(mut self) -> Self {
        let defaults = Self::default();
        let mut profiles = Vec::with_capacity(PROFILE_COUNT);

        for default_profile in defaults.profiles {
            let mut profile = self
                .profiles
                .iter()
                .find(|profile| profile.id == default_profile.id)
                .cloned()
                .unwrap_or_else(|| default_profile.clone());

            profile.name = normalize_profile_name(&profile.name, &default_profile.name);
            profile.settings = profile.settings.normalized();
            profiles.push(profile);
        }

        self.profiles = profiles;

        if !self
            .profiles
            .iter()
            .any(|profile| profile.id == self.active_profile_id)
        {
            self.active_profile_id = OverlayProfileId::Profile1;
        }

        self
    }
}

impl Default for OverlaySettingsStore {
    fn default() -> Self {
        Self {
            active_profile_id: OverlayProfileId::Profile1,
            profiles: OverlayProfileId::all()
                .iter()
                .map(|id| OverlaySettingsProfile {
                    id: *id,
                    name: id.default_name().to_string(),
                    settings: OverlaySettings::default(),
                })
                .collect(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct OverlaySettingsProfile {
    pub id: OverlayProfileId,
    pub name: String,
    pub settings: OverlaySettings,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum OverlayProfileId {
    #[serde(rename = "profile1")]
    Profile1,
    #[serde(rename = "profile2")]
    Profile2,
    #[serde(rename = "profile3")]
    Profile3,
    #[serde(rename = "profile4")]
    Profile4,
    #[serde(rename = "profile5")]
    Profile5,
}

impl OverlayProfileId {
    pub fn all() -> [Self; PROFILE_COUNT] {
        [
            Self::Profile1,
            Self::Profile2,
            Self::Profile3,
            Self::Profile4,
            Self::Profile5,
        ]
    }

    fn default_name(self) -> &'static str {
        match self {
            Self::Profile1 => "Profile 1",
            Self::Profile2 => "Profile 2",
            Self::Profile3 => "Profile 3",
            Self::Profile4 => "Profile 4",
            Self::Profile5 => "Profile 5",
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct OverlaySettings {
    #[serde(default = "default_always_on_top")]
    pub always_on_top: bool,
    pub font_family: String,
    pub font_size: u32,
    pub font_weight: FontWeight,
    #[serde(default = "default_original_line_scale")]
    pub original_line_scale: f32,
    pub text_color: String,
    pub background_color: String,
    pub background_opacity: f32,
    pub outline_color: String,
    pub outline_width: u32,
    pub start_width: u32,
    pub start_height: u32,
    pub start_x: Option<i32>,
    pub start_y: Option<i32>,
    #[serde(default)]
    pub click_through: bool,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct OverlayPlacement {
    pub x: i32,
    pub y: i32,
    pub width: u32,
    pub height: u32,
    pub is_accepted: bool,
}

impl OverlayPlacement {
    pub fn from_settings(settings: &OverlaySettings) -> Self {
        Self {
            x: settings.start_x.unwrap_or(0),
            y: settings.start_y.unwrap_or(0),
            width: settings.start_width,
            height: settings.start_height,
            is_accepted: false,
        }
    }
}

impl Default for OverlaySettings {
    fn default() -> Self {
        Self {
            always_on_top: true,
            font_family: "Segoe UI".to_string(),
            font_size: 42,
            font_weight: FontWeight::Bold,
            original_line_scale: default_original_line_scale(),
            text_color: "#ffffff".to_string(),
            background_color: "#000000".to_string(),
            background_opacity: 0.47,
            outline_color: "#000000".to_string(),
            outline_width: 2,
            start_width: 900,
            start_height: 180,
            start_x: None,
            start_y: None,
            click_through: false,
        }
    }
}

impl OverlaySettings {
    pub fn normalized(mut self) -> Self {
        let defaults = Self::default();

        self.font_family = normalize_font_family(&self.font_family, &defaults.font_family);
        self.font_size = self.font_size.clamp(18, 96);
        self.original_line_scale = self.original_line_scale.clamp(0.6, 1.0);
        self.text_color = normalize_color(&self.text_color).unwrap_or(defaults.text_color);
        self.background_color =
            normalize_color(&self.background_color).unwrap_or(defaults.background_color);
        self.background_opacity = self.background_opacity.clamp(0.0, 1.0);
        self.outline_color = normalize_color(&self.outline_color).unwrap_or(defaults.outline_color);
        self.outline_width = self.outline_width.clamp(0, 8);
        self.start_width = self.start_width.clamp(280, 3840);
        self.start_height = self.start_height.clamp(110, 1200);

        self
    }
}

fn default_original_line_scale() -> f32 {
    0.78
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum FontWeight {
    Normal,
    Bold,
}

impl FontWeight {
    pub fn win32_weight(self) -> i32 {
        match self {
            Self::Normal => 400,
            Self::Bold => 700,
        }
    }
}

pub fn hex_to_rgb(color: &str) -> (u8, u8, u8) {
    let normalized = normalize_color(color).unwrap_or_else(|| "#ffffff".to_string());
    let value = normalized.trim_start_matches('#');
    let red = u8::from_str_radix(&value[0..2], 16).unwrap_or(255);
    let green = u8::from_str_radix(&value[2..4], 16).unwrap_or(255);
    let blue = u8::from_str_radix(&value[4..6], 16).unwrap_or(255);
    (red, green, blue)
}

fn normalize_profile_name(value: &str, fallback: &str) -> String {
    let trimmed = value.trim();

    if trimmed.is_empty() || trimmed.len() > 32 {
        fallback.to_string()
    } else {
        trimmed.to_string()
    }
}

fn normalize_font_family(value: &str, fallback: &str) -> String {
    let trimmed = value.trim();

    if trimmed.is_empty() || trimmed.len() > 80 {
        fallback.to_string()
    } else {
        trimmed.to_string()
    }
}

fn normalize_color(value: &str) -> Option<String> {
    let trimmed = value.trim();

    if let Some(hex) = normalize_hex_color(trimmed) {
        return Some(hex);
    }

    normalize_rgb_color(trimmed)
}

fn normalize_hex_color(value: &str) -> Option<String> {
    let hex = value.strip_prefix('#')?;

    if hex.len() == 3 && hex.chars().all(|character| character.is_ascii_hexdigit()) {
        let mut expanded = String::from("#");
        for character in hex.chars() {
            expanded.push(character.to_ascii_lowercase());
            expanded.push(character.to_ascii_lowercase());
        }
        return Some(expanded);
    }

    if hex.len() == 6 && hex.chars().all(|character| character.is_ascii_hexdigit()) {
        return Some(format!("#{}", hex.to_ascii_lowercase()));
    }

    None
}

fn normalize_rgb_color(value: &str) -> Option<String> {
    let lower = value.to_ascii_lowercase();
    let body = lower.strip_prefix("rgb(")?.strip_suffix(')')?;
    let mut channels = body.split(',').map(|part| part.trim().parse::<u8>());

    let red = channels.next()?.ok()?;
    let green = channels.next()?.ok()?;
    let blue = channels.next()?.ok()?;

    if channels.next().is_some() {
        return None;
    }

    Some(format!("#{red:02x}{green:02x}{blue:02x}"))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn simultaneous_geometry_and_appearance_edits_survive_reload() {
        let directory =
            std::env::temp_dir().join(format!("feelsay-overlay-patch-{}", std::process::id()));
        let service = OverlaySettingsService::new(directory.clone());
        let geometry = service.clone();
        let appearance = service.clone();
        let first = std::thread::spawn(move || {
            geometry
                .patch(None, serde_json::json!({"startX": -800, "startWidth": 600}))
                .unwrap()
        });
        let second = std::thread::spawn(move || {
            appearance
                .patch(
                    None,
                    serde_json::json!({"fontSize": 58, "textColor": "#ffff80"}),
                )
                .unwrap()
        });
        first.join().unwrap();
        second.join().unwrap();
        let saved = OverlaySettingsService::new(directory.clone())
            .load()
            .unwrap();
        assert_eq!(saved.start_x, Some(-800));
        assert_eq!(saved.start_width, 600);
        assert_eq!(saved.font_size, 58);
        assert_eq!(saved.text_color, "#ffff80");
        let runtime: OverlaySettings =
            serde_json::from_str(&fs::read_to_string(&service.runtime_path).unwrap()).unwrap();
        assert_eq!(runtime.font_size, saved.font_size);
        assert_eq!(runtime.start_x, saved.start_x);
        fs::remove_file(service.path).unwrap();
        fs::remove_file(service.runtime_path).unwrap();
        fs::remove_dir(directory).unwrap();
    }
}
