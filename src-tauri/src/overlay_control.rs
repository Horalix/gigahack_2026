//! Private, loopback-only control channel for the native overlay child.
//! This protocol carries settings/status only; never audio or transcript content.
use crate::{
    app_state::AppState,
    overlay_settings::OverlaySettings,
    transcript::{TranscriptSettings, TranscriptStatus},
};
use serde::{Deserialize, Serialize};
use std::{
    io::{BufRead, BufReader, Read, Write},
    net::{TcpListener, TcpStream},
    time::Duration,
};
use tauri::Manager;

#[derive(Clone)]
pub struct OverlayControlEndpoint {
    pub address: String,
    pub token: String,
}

#[derive(Serialize, Deserialize)]
struct Request {
    token: String,
    saving_enabled: Option<bool>,
    settings: Option<serde_json::Value>,
}

#[derive(Serialize, Deserialize)]
pub struct OverlayControlStatus {
    pub transcript: TranscriptStatus,
    pub settings: OverlaySettings,
    pub error: Option<String>,
}

#[cfg(target_os = "windows")]
pub fn start(app: tauri::AppHandle) -> Result<OverlayControlEndpoint, Box<dyn std::error::Error>> {
    let listener = TcpListener::bind("127.0.0.1:0")?;
    let endpoint = OverlayControlEndpoint {
        address: listener.local_addr()?.to_string(),
        token: format!("{:?}", windows::core::GUID::new()?),
    };
    let token = endpoint.token.clone();
    std::thread::Builder::new()
        .name("feelsay-overlay-control".into())
        .spawn(move || {
            for mut stream in listener.incoming().flatten() {
                let _ = stream.set_read_timeout(Some(Duration::from_millis(300)));
                let _ = stream.set_write_timeout(Some(Duration::from_millis(300)));
                let mut line = String::new();
                if BufReader::new((&stream).take(16_384))
                    .read_line(&mut line)
                    .is_err()
                {
                    continue;
                }
                let Ok(request) = serde_json::from_str::<Request>(&line) else {
                    continue;
                };
                if request.token != token {
                    continue;
                }
                let state = app.state::<AppState>();
                let mut error = None;
                if let Some(enabled) = request.saving_enabled {
                    if state
                        .transcripts()
                        .save_settings(TranscriptSettings {
                            saving_enabled: enabled,
                        })
                        .is_err()
                    {
                        error =
                            Some("Could not change transcript saving. Check Settings.".to_string());
                    }
                }
                if let Some(settings) = request.settings {
                    if state.overlay_settings().patch(None, settings).is_err() {
                        error = Some("Could not save overlay settings.".to_string());
                    }
                }
                let Ok(settings) = state.overlay_settings().load() else {
                    continue;
                };
                let response = OverlayControlStatus {
                    transcript: state.transcripts().status(),
                    settings,
                    error,
                };
                if let Ok(json) = serde_json::to_string(&response) {
                    let _ = writeln!(stream, "{json}");
                }
            }
        })?;
    Ok(endpoint)
}

pub fn request(
    saving_enabled: Option<bool>,
    settings: Option<serde_json::Value>,
) -> Result<OverlayControlStatus, Box<dyn std::error::Error>> {
    let address = std::env::var("FEELSAY_OVERLAY_CONTROL")?.parse()?;
    let mut stream = TcpStream::connect_timeout(&address, Duration::from_millis(100))?;
    stream.set_read_timeout(Some(Duration::from_millis(300)))?;
    stream.set_write_timeout(Some(Duration::from_millis(300)))?;
    let request = Request {
        token: std::env::var("FEELSAY_OVERLAY_TOKEN")?,
        saving_enabled,
        settings,
    };
    writeln!(stream, "{}", serde_json::to_string(&request)?)?;
    let mut response = String::new();
    BufReader::new(stream.take(16_384)).read_line(&mut response)?;
    Ok(serde_json::from_str(&response)?)
}
