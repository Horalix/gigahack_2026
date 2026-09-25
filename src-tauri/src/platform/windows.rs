use crate::{
    app_error::AppError,
    platform::{
        AudioCaptureProvider, PlatformCapabilityProvider, SourceEnumerator, SourcePreviewProvider,
    },
    source::{
        AudioEndpointFlow, AudioSource, CssPreviewMetadata, MockPreviewTemplate,
        PlatformCapabilities, SourceKind, SourceMetadata, SourcePreview,
    },
};

fn application_capture_supported() -> bool {
    #[cfg(target_os = "windows")]
    {
        crate::application_audio::is_supported()
    }
    #[cfg(not(target_os = "windows"))]
    {
        false
    }
}

#[cfg(target_os = "windows")]
use std::{collections::HashSet, mem::size_of, path::Path};

#[cfg(target_os = "windows")]
use windows::{
    core::{BOOL, PWSTR},
    Win32::{
        Devices::FunctionDiscovery::PKEY_Device_FriendlyName,
        Foundation::{CloseHandle, HWND, LPARAM, RECT, RPC_E_CHANGED_MODE},
        Graphics::Dwm::{DwmGetWindowAttribute, DWMWA_CLOAKED},
        Media::Audio::{
            eCapture, eConsole, eRender, EDataFlow, IMMDevice, IMMDeviceEnumerator,
            MMDeviceEnumerator, DEVICE_STATE_ACTIVE,
        },
        System::{
            Com::StructuredStorage::{PropVariantClear, PROPVARIANT},
            Com::{
                CoCreateInstance, CoInitializeEx, CoTaskMemFree, CLSCTX_INPROC_SERVER,
                COINIT_APARTMENTTHREADED, STGM_READ,
            },
            Threading::{
                GetCurrentProcessId, OpenProcess, QueryFullProcessImageNameW, PROCESS_NAME_WIN32,
                PROCESS_QUERY_LIMITED_INFORMATION,
            },
            Variant::VT_LPWSTR,
        },
        UI::WindowsAndMessaging::{
            EnumWindows, GetClassNameW, GetShellWindow, GetWindowLongPtrW, GetWindowRect,
            GetWindowTextLengthW, GetWindowTextW, GetWindowThreadProcessId, IsIconic,
            IsWindowVisible, GWL_EXSTYLE, WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW,
        },
    },
};

pub struct WindowsPlatformProvider;

impl SourceEnumerator for WindowsPlatformProvider {
    fn list_sources(&self) -> Result<Vec<AudioSource>, AppError> {
        Ok(list_windows_sources())
    }
}

impl SourcePreviewProvider for WindowsPlatformProvider {
    fn source_previews(&self) -> Result<Vec<SourcePreview>, AppError> {
        Ok(list_windows_sources()
            .into_iter()
            .filter(|source| source.kind == SourceKind::Window)
            .map(window_preview)
            .collect())
    }
}

impl AudioCaptureProvider for WindowsPlatformProvider {
    fn capture_provider_name(&self) -> &'static str {
        "wasapi-enumeration"
    }
}

impl PlatformCapabilityProvider for WindowsPlatformProvider {
    fn capabilities(&self) -> PlatformCapabilities {
        PlatformCapabilities {
            platform: "windows".to_string(),
            source_enumeration_available: true,
            window_capture_available: false,
            system_audio_capture_available: true,
            microphone_capture_available: true,
            live_preview_available: false,
            supports_system_audio: true,
            supports_application_audio: cfg!(target_os = "windows")
                && application_capture_supported(),
            supports_microphone: true,
            supports_live_preview: false,
            supports_loopback_capture: true,
        }
    }
}

#[cfg(target_os = "windows")]
fn list_windows_sources() -> Vec<AudioSource> {
    let mut sources = enumerate_windows();
    sources.push(system_audio_source());
    sources.extend(enumerate_audio_endpoints());
    sources
}

#[cfg(not(target_os = "windows"))]
fn list_windows_sources() -> Vec<AudioSource> {
    Vec::new()
}

#[cfg(target_os = "windows")]
fn enumerate_windows() -> Vec<AudioSource> {
    let mut windows = Vec::<WindowSource>::new();
    let lparam = LPARAM((&mut windows as *mut Vec<WindowSource>) as isize);

    unsafe {
        let _ = EnumWindows(Some(enum_window), lparam);
    }

    let mut seen = HashSet::new();
    let mut sources = windows
        .into_iter()
        .filter(|window| seen.insert((window.process_id, window.title.to_lowercase())))
        .map(window_source)
        .collect::<Vec<_>>();
    sources.sort_by(|left, right| {
        source_sort_key(left)
            .to_lowercase()
            .cmp(&source_sort_key(right).to_lowercase())
    });
    sources
}

#[cfg(target_os = "windows")]
unsafe extern "system" fn enum_window(hwnd: HWND, lparam: LPARAM) -> BOOL {
    let windows = unsafe { &mut *(lparam.0 as *mut Vec<WindowSource>) };

    if let Some(source) = visible_window(hwnd) {
        windows.push(source);
    }

    true.into()
}

#[cfg(target_os = "windows")]
fn visible_window(hwnd: HWND) -> Option<WindowSource> {
    unsafe {
        if hwnd == GetShellWindow() || !IsWindowVisible(hwnd).as_bool() {
            return None;
        }

        if has_ignored_extended_style(hwnd) {
            return None;
        }

        let is_minimized = IsIconic(hwnd).as_bool();
        if !is_minimized && is_useless_window_rect(window_rect(hwnd)?) {
            return None;
        }

        let title = window_text(hwnd)?;
        if is_useless_title(&title) {
            return None;
        }

        let class_name = window_class(hwnd);
        if is_useless_window_class(&class_name) || is_cloaked(hwnd) {
            return None;
        }

        let mut process_id = 0;
        GetWindowThreadProcessId(hwnd, Some(&mut process_id));

        if process_id == 0 || process_id == GetCurrentProcessId() {
            return None;
        }

        let process_path = process_path(process_id);
        if is_feelsay_process(&title, process_path.as_deref())
            || is_system_process(process_path.as_deref())
        {
            return None;
        }

        Some(WindowSource {
            hwnd,
            title,
            process_id,
            process_path,
        })
    }
}

#[cfg(target_os = "windows")]
fn source_sort_key(source: &AudioSource) -> String {
    source
        .metadata
        .as_ref()
        .and_then(|metadata| metadata.app_name.as_deref())
        .unwrap_or(&source.display_name)
        .to_string()
}

#[cfg(target_os = "windows")]
fn has_ignored_extended_style(hwnd: HWND) -> bool {
    let style = unsafe { GetWindowLongPtrW(hwnd, GWL_EXSTYLE) as u32 };
    style & (WS_EX_TOOLWINDOW.0 | WS_EX_NOACTIVATE.0) != 0
}

#[cfg(target_os = "windows")]
fn window_rect(hwnd: HWND) -> Option<RECT> {
    unsafe {
        let mut rect = RECT::default();
        GetWindowRect(hwnd, &mut rect).ok()?;
        Some(rect)
    }
}

#[cfg(target_os = "windows")]
fn is_useless_window_rect(rect: RECT) -> bool {
    let width = rect.right - rect.left;
    let height = rect.bottom - rect.top;
    width < 120 || height < 80 || rect.right <= -32_000 || rect.bottom <= -32_000
}

#[cfg(target_os = "windows")]
fn window_text(hwnd: HWND) -> Option<String> {
    unsafe {
        let length = GetWindowTextLengthW(hwnd);
        if length <= 0 {
            return None;
        }

        let mut buffer = vec![0; length as usize + 1];
        let copied = GetWindowTextW(hwnd, &mut buffer);
        if copied <= 0 {
            return None;
        }

        let text = String::from_utf16_lossy(&buffer[..copied as usize])
            .trim()
            .to_string();
        (!text.is_empty()).then_some(text)
    }
}

#[cfg(target_os = "windows")]
fn window_class(hwnd: HWND) -> String {
    unsafe {
        let mut buffer = vec![0; 256];
        let copied = GetClassNameW(hwnd, &mut buffer);
        String::from_utf16_lossy(&buffer[..copied as usize])
    }
}

#[cfg(target_os = "windows")]
fn is_cloaked(hwnd: HWND) -> bool {
    unsafe {
        let mut cloaked = 0u32;
        DwmGetWindowAttribute(
            hwnd,
            DWMWA_CLOAKED,
            (&mut cloaked as *mut u32).cast(),
            size_of::<u32>() as u32,
        )
        .is_ok()
            && cloaked != 0
    }
}

#[cfg(target_os = "windows")]
fn process_path(process_id: u32) -> Option<String> {
    unsafe {
        let process = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, false, process_id).ok()?;
        let mut buffer = vec![0; 32768];
        let mut length = buffer.len() as u32;
        let result = QueryFullProcessImageNameW(
            process,
            PROCESS_NAME_WIN32,
            PWSTR(buffer.as_mut_ptr()),
            &mut length,
        );
        let _ = CloseHandle(process);

        result
            .ok()
            .map(|_| String::from_utf16_lossy(&buffer[..length as usize]))
    }
}

#[cfg(target_os = "windows")]
fn enumerate_audio_endpoints() -> Vec<AudioSource> {
    let init = unsafe { CoInitializeEx(None, COINIT_APARTMENTTHREADED) };
    if init.is_err() && init != RPC_E_CHANGED_MODE {
        return Vec::new();
    }

    let enumerator = unsafe {
        CoCreateInstance::<_, IMMDeviceEnumerator>(
            &MMDeviceEnumerator,
            None::<&windows::core::IUnknown>,
            CLSCTX_INPROC_SERVER,
        )
    };

    let Ok(enumerator) = enumerator else {
        return Vec::new();
    };

    let default_render = default_endpoint_id(&enumerator, eRender);
    let default_capture = default_endpoint_id(&enumerator, eCapture);
    let mut sources = audio_endpoints_for_flow(
        &enumerator,
        eRender,
        SourceKind::OutputDevice,
        default_render.as_deref(),
    );
    sources.extend(audio_endpoints_for_flow(
        &enumerator,
        eCapture,
        SourceKind::Microphone,
        default_capture.as_deref(),
    ));
    sources
}

#[cfg(target_os = "windows")]
fn audio_endpoints_for_flow(
    enumerator: &IMMDeviceEnumerator,
    flow: EDataFlow,
    kind: SourceKind,
    default_id: Option<&str>,
) -> Vec<AudioSource> {
    let collection = unsafe { enumerator.EnumAudioEndpoints(flow, DEVICE_STATE_ACTIVE) };
    let Ok(collection) = collection else {
        return Vec::new();
    };

    let count = unsafe { collection.GetCount() }.unwrap_or(0);
    (0..count)
        .filter_map(|index| unsafe { collection.Item(index).ok() })
        .filter_map(|device| audio_endpoint(device, kind, default_id))
        .collect()
}

#[cfg(target_os = "windows")]
fn audio_endpoint(
    device: IMMDevice,
    kind: SourceKind,
    default_id: Option<&str>,
) -> Option<AudioSource> {
    let endpoint_id = endpoint_id(&device)?;
    let display_name = endpoint_display_name(&device).unwrap_or_else(|| endpoint_id.clone());
    let flow = match kind {
        SourceKind::Microphone => AudioEndpointFlow::Capture,
        _ => AudioEndpointFlow::Render,
    };
    let is_default = default_id == Some(endpoint_id.as_str());

    Some(AudioSource {
        id: format!(
            "{}:{}",
            match flow {
                AudioEndpointFlow::Capture => "capture",
                AudioEndpointFlow::Render => "render",
            },
            endpoint_id
        ),
        display_name,
        kind,
        is_available: true,
        platform: "windows".to_string(),
        metadata: Some(SourceMetadata {
            app_name: None,
            process_name: None,
            process_id: None,
            process_path: None,
            window_title: None,
            endpoint_id: Some(endpoint_id),
            endpoint_flow: Some(flow),
            is_default: Some(is_default),
        }),
    })
}

fn system_audio_source() -> AudioSource {
    AudioSource {
        id: "system-audio".to_string(),
        display_name: "All system audio".to_string(),
        kind: SourceKind::SystemAudio,
        is_available: true,
        platform: "windows".to_string(),
        metadata: None,
    }
}

#[cfg(target_os = "windows")]
fn default_endpoint_id(enumerator: &IMMDeviceEnumerator, flow: EDataFlow) -> Option<String> {
    let device = unsafe { enumerator.GetDefaultAudioEndpoint(flow, eConsole).ok()? };
    endpoint_id(&device)
}

#[cfg(target_os = "windows")]
fn endpoint_id(device: &IMMDevice) -> Option<String> {
    unsafe {
        let id = device.GetId().ok()?;
        let text = id.to_string().ok()?;
        CoTaskMemFree(Some(id.as_ptr().cast()));
        Some(text)
    }
}

#[cfg(target_os = "windows")]
fn endpoint_display_name(device: &IMMDevice) -> Option<String> {
    unsafe {
        let store = device.OpenPropertyStore(STGM_READ).ok()?;
        let mut value: PROPVARIANT = store.GetValue(&PKEY_Device_FriendlyName).ok()?;
        let variant = &*value.Anonymous.Anonymous;

        let name = if variant.vt == VT_LPWSTR {
            let value = variant.Anonymous.pwszVal;
            (!value.is_null()).then(|| value.to_string().ok()).flatten()
        } else {
            None
        };

        let _ = PropVariantClear(&mut value);
        name
    }
}

#[cfg(target_os = "windows")]
fn window_source(window: WindowSource) -> AudioSource {
    AudioSource {
        id: format!("window:{:x}:{}", window.hwnd.0 as usize, window.process_id),
        display_name: window.title.clone(),
        kind: SourceKind::Window,
        is_available: application_capture_supported(),
        platform: "windows".to_string(),
        metadata: Some(SourceMetadata {
            app_name: window.process_path.as_deref().and_then(process_stem),
            process_name: window.process_path.as_deref().and_then(process_file_name),
            process_id: Some(window.process_id),
            process_path: window.process_path,
            window_title: Some(window.title),
            endpoint_id: None,
            endpoint_flow: None,
            is_default: None,
        }),
    }
}

fn window_preview(source: AudioSource) -> SourcePreview {
    let template = source
        .metadata
        .as_ref()
        .and_then(|metadata| preview_template_for(metadata, &source.display_name));

    SourcePreview {
        source_id: source.id,
        title: source.display_name.clone(),
        kind: source.kind,
        thumbnail_url: None,
        thumbnail_data: None,
        is_live_preview_available: false,
        css_preview: template
            .is_none()
            .then(|| css_preview_for(&source.display_name)),
        mock_template: template,
    }
}

#[cfg(target_os = "windows")]
fn preview_template_for(
    metadata: &SourceMetadata,
    display_name: &str,
) -> Option<MockPreviewTemplate> {
    let haystack = [
        metadata.app_name.as_deref(),
        metadata.process_name.as_deref(),
        metadata.window_title.as_deref(),
        Some(display_name),
    ]
    .into_iter()
    .flatten()
    .collect::<Vec<_>>()
    .join(" ")
    .to_lowercase();

    if contains_any(&haystack, &["chrome", "edge", "firefox", "browser"]) {
        return Some(MockPreviewTemplate::Browser);
    }

    if contains_any(&haystack, &["discord", "slack", "chat"]) {
        return Some(MockPreviewTemplate::Chat);
    }

    if contains_any(&haystack, &["teams", "zoom", "meet", "call"]) {
        return Some(MockPreviewTemplate::Meeting);
    }

    if contains_any(
        &haystack,
        &["vlc", "media player", "youtube", "netflix", "video"],
    ) {
        return Some(MockPreviewTemplate::Video);
    }

    if contains_any(
        &haystack,
        &["league", "steam", "game", "valorant", "minecraft"],
    ) {
        return Some(MockPreviewTemplate::Game);
    }

    None
}

#[cfg(target_os = "windows")]
fn contains_any(value: &str, needles: &[&str]) -> bool {
    needles.iter().any(|needle| value.contains(needle))
}

fn css_preview_for(title: &str) -> CssPreviewMetadata {
    let palette = [
        (
            "oklch(63% 0.15 220)",
            "linear-gradient(135deg, oklch(23% 0.04 230), oklch(14% 0.018 250))",
        ),
        (
            "oklch(68% 0.14 165)",
            "linear-gradient(135deg, oklch(22% 0.052 168), oklch(13% 0.02 235))",
        ),
        (
            "oklch(72% 0.16 55)",
            "linear-gradient(135deg, oklch(24% 0.05 45), oklch(14% 0.016 235))",
        ),
        (
            "oklch(70% 0.13 325)",
            "linear-gradient(135deg, oklch(23% 0.055 320), oklch(13% 0.018 245))",
        ),
    ];
    let index = title.bytes().fold(0usize, |acc, byte| acc + byte as usize) % palette.len();
    let (accent_color, background) = palette[index];

    CssPreviewMetadata {
        label: title.to_string(),
        accent_color: accent_color.to_string(),
        background: background.to_string(),
    }
}

#[cfg(target_os = "windows")]
fn is_useless_title(title: &str) -> bool {
    let title = title.trim().to_lowercase();
    title.is_empty()
        || matches!(
            title.as_str(),
            "ashotplugctrl"
                | "program manager"
                | "settings"
                | "windows input experience"
                | "desktopwindowxamlsource"
        )
}

#[cfg(target_os = "windows")]
fn is_useless_window_class(class_name: &str) -> bool {
    matches!(
        class_name,
        "ASHOTPLUGCTRL"
            | "Progman"
            | "WorkerW"
            | "Shell_TrayWnd"
            | "Shell_SecondaryTrayWnd"
            | "Windows.UI.Core.CoreWindow"
            | "ApplicationFrameInputSinkWindow"
            | "Xaml_WindowedPopupClass"
    )
}

#[cfg(target_os = "windows")]
fn is_feelsay_process(title: &str, process_path: Option<&str>) -> bool {
    process_path
        .and_then(|path| Path::new(path).file_stem())
        .and_then(|name| name.to_str())
        .map(|name| name.eq_ignore_ascii_case("feelsay"))
        .unwrap_or_else(|| {
            title.eq_ignore_ascii_case("FeelSay")
                || title.eq_ignore_ascii_case("FeelSay Caption Window")
        })
}

#[cfg(all(test, target_os = "windows"))]
#[test]
fn source_filter_does_not_hide_other_apps_discussing_feelsay() {
    assert!(!is_feelsay_process(
        "FeelSay Controlled Audio Fixture",
        Some("C:/tests/FixturePlayer.exe")
    ));
    assert!(!is_feelsay_process(
        "FeelSay documentation",
        Some("C:/browser/msedge.exe")
    ));
    assert!(!is_feelsay_process("FeelSay documentation", None));
    assert!(is_feelsay_process("Captions", Some("C:/app/FeelSay.exe")));
    assert!(is_feelsay_process("FeelSay Caption Window", None));
}

#[cfg(target_os = "windows")]
fn is_system_process(process_path: Option<&str>) -> bool {
    let Some(path) = process_path else {
        return false;
    };
    let Some(file_name) = Path::new(path).file_name().and_then(|name| name.to_str()) else {
        return false;
    };

    matches!(
        file_name.to_lowercase().as_str(),
        "dwm.exe"
            | "lockapp.exe"
            | "searchhost.exe"
            | "shellexperiencehost.exe"
            | "startmenuexperiencehost.exe"
            | "systemsettings.exe"
            | "textinputhost.exe"
    )
}

#[cfg(target_os = "windows")]
fn process_file_name(path: &str) -> Option<String> {
    Path::new(path)
        .file_name()
        .and_then(|name| name.to_str())
        .map(str::to_string)
}

#[cfg(target_os = "windows")]
fn process_stem(path: &str) -> Option<String> {
    Path::new(path)
        .file_stem()
        .and_then(|name| name.to_str())
        .map(str::to_string)
}

#[cfg(target_os = "windows")]
struct WindowSource {
    hwnd: HWND,
    title: String,
    process_id: u32,
    process_path: Option<String>,
}
