// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    #[cfg(target_os = "windows")]
    unsafe {
        let _ = windows::Win32::UI::HiDpi::SetProcessDpiAwarenessContext(
            windows::Win32::UI::HiDpi::DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2,
        );
    }
    #[cfg(target_os = "windows")]
    if diagnostic_arg_value("--overlay-render-test").is_some() {
        let caption_file =
            std::env::var_os("FEELSAY_CAPTION_TEXT_FILE").map(std::path::PathBuf::from);
        run_caption_window_child(overlay_settings_from_env(), None, None, caption_file);
        return;
    }
    if std::env::args().any(|arg| arg == "--asr-diagnostic") {
        run_asr_diagnostic_command(AsrDiagnosticMode::Direct);
        return;
    }

    if let Some(audio_path) = diagnostic_arg_value("--asr-file-diagnostic") {
        run_asr_file_diagnostic_command(audio_path);
        return;
    }

    if std::env::args().any(|arg| arg == "--asr-pipeline-diagnostic") {
        run_asr_diagnostic_command(AsrDiagnosticMode::Pipeline);
        return;
    }

    if std::env::args().any(|arg| arg == "--system-audio-asr-diagnostic") {
        run_asr_diagnostic_command(AsrDiagnosticMode::SystemAudio);
        return;
    }

    if std::env::args().any(|arg| arg == "--caption-flow-diagnostic") {
        run_asr_diagnostic_command(AsrDiagnosticMode::CaptionFlow);
        return;
    }

    if std::env::args().any(|arg| arg == "--caption-placement-child") {
        let settings = overlay_settings_from_env();
        let placement_file =
            std::env::var_os("FEELSAY_OVERLAY_PLACEMENT_FILE").map(std::path::PathBuf::from);
        run_caption_window_child(settings, placement_file, None, None);
        return;
    }

    if std::env::args().any(|arg| arg == "--caption-window-child") {
        let settings_file =
            std::env::var_os("FEELSAY_OVERLAY_SETTINGS_FILE").map(std::path::PathBuf::from);
        let caption_file =
            std::env::var_os("FEELSAY_CAPTION_TEXT_FILE").map(std::path::PathBuf::from);
        run_caption_window_child(
            overlay_settings_from_env(),
            None,
            settings_file,
            caption_file,
        );
        return;
    }

    feelsay_lib::run()
}

fn diagnostic_arg_value(name: &str) -> Option<std::path::PathBuf> {
    let mut args = std::env::args();

    while let Some(arg) = args.next() {
        if arg == name {
            return args.next().map(std::path::PathBuf::from);
        }
    }

    None
}

fn run_asr_file_diagnostic_command(audio_path: std::path::PathBuf) {
    let data_dir = match app_data_dir() {
        Ok(data_dir) => data_dir,
        Err(error) => {
            eprintln!("{error}");
            std::process::exit(1);
        }
    };
    let state = feelsay_lib::app_state::AppState::new(data_dir);
    let config = match state.asr_runtime_config() {
        Ok(Some(config)) => config,
        Ok(None) => {
            eprintln!("ASR model is not ready");
            std::process::exit(1);
        }
        Err(error) => {
            eprintln!("{error}");
            std::process::exit(1);
        }
    };

    match feelsay_lib::asr::run_asr_file_diagnostic(config, audio_path) {
        Ok(result) => println!("{}", result.text),
        Err(error) => {
            eprintln!("{error}");
            std::process::exit(1);
        }
    }
}

enum AsrDiagnosticMode {
    Direct,
    Pipeline,
    SystemAudio,
    CaptionFlow,
}

fn run_asr_diagnostic_command(mode: AsrDiagnosticMode) {
    let data_dir = match app_data_dir() {
        Ok(data_dir) => data_dir,
        Err(error) => {
            eprintln!("{error}");
            std::process::exit(1);
        }
    };
    let state = feelsay_lib::app_state::AppState::new(data_dir);
    let config = match state.asr_runtime_config() {
        Ok(Some(config)) => config,
        Ok(None) => {
            eprintln!("ASR model is not ready");
            std::process::exit(1);
        }
        Err(error) => {
            eprintln!("{error}");
            std::process::exit(1);
        }
    };

    let result = match mode {
        AsrDiagnosticMode::Direct => feelsay_lib::asr::run_asr_diagnostic(config),
        AsrDiagnosticMode::Pipeline => feelsay_lib::asr::run_asr_pipeline_diagnostic(config),
        AsrDiagnosticMode::SystemAudio => feelsay_lib::asr::run_system_audio_asr_diagnostic(config),
        AsrDiagnosticMode::CaptionFlow => run_caption_flow_diagnostic(&state, config),
    };

    match result {
        Ok(result) => println!("{}", result.text),
        Err(error) => {
            eprintln!("{error}");
            std::process::exit(1);
        }
    }
}

fn run_caption_flow_diagnostic(
    state: &feelsay_lib::app_state::AppState,
    config: feelsay_lib::asr::AsrRuntimeConfig,
) -> Result<feelsay_lib::asr::AsrDiagnosticResult, feelsay_lib::app_error::AppError> {
    state.open_caption_process()?;
    let result = feelsay_lib::asr::run_system_audio_asr_diagnostic(config);
    state
        .close_caption_process()
        .map_err(|error| feelsay_lib::app_error::AppError::Window(error.to_string()))?;
    result
}

fn app_data_dir() -> Result<std::path::PathBuf, String> {
    #[cfg(windows)]
    {
        let app_data = std::env::var_os("APPDATA")
            .ok_or_else(|| "APPDATA is not set; cannot find Feelsay app data".to_string())?;
        Ok(std::path::PathBuf::from(app_data).join("app.feelsay.desktop"))
    }

    #[cfg(not(windows))]
    {
        Err("ASR diagnostic CLI is Windows-only for now".to_string())
    }
}

fn overlay_settings_from_env() -> feelsay_lib::overlay_settings::OverlaySettings {
    std::env::var("FEELSAY_OVERLAY_SETTINGS")
        .ok()
        .and_then(|settings| {
            serde_json::from_str::<feelsay_lib::overlay_settings::OverlaySettings>(&settings).ok()
        })
        .unwrap_or_default()
        .normalized()
}

#[cfg(windows)]
fn run_caption_window_child(
    settings: feelsay_lib::overlay_settings::OverlaySettings,
    placement_file: Option<std::path::PathBuf>,
    settings_file: Option<std::path::PathBuf>,
    caption_file: Option<std::path::PathBuf>,
) {
    use core::ffi::c_void;
    use feelsay_lib::overlay_settings::{hex_to_rgb, OverlayPlacement, OverlaySettings};
    use std::{
        cell::{Cell, RefCell},
        time::{Duration, Instant, SystemTime},
    };
    use windows::{
        core::{w, PCWSTR},
        Win32::{
            Foundation::{COLORREF, HWND, LPARAM, LRESULT, POINT, RECT, SIZE, WPARAM},
            Graphics::Gdi::{
                BeginPaint, CreateCompatibleDC, CreateDIBSection, CreateFontW, CreatePen,
                CreateSolidBrush, DeleteDC, DeleteObject, DrawTextW, Ellipse, EndPaint,
                GetMonitorInfoW, MonitorFromRect, MonitorFromWindow, SelectObject, SetBkMode,
                SetTextColor, AC_SRC_ALPHA, AC_SRC_OVER, ANTIALIASED_QUALITY, BITMAPINFO, BI_RGB,
                CLIP_DEFAULT_PRECIS, DEFAULT_CHARSET, DIB_RGB_COLORS, DRAW_TEXT_FORMAT,
                DT_CALCRECT, DT_CENTER, DT_SINGLELINE, DT_VCENTER, DT_WORDBREAK, HDC, MONITORINFO,
                MONITOR_DEFAULTTONEAREST, OUT_DEFAULT_PRECIS, PAINTSTRUCT, PS_SOLID, TRANSPARENT,
            },
            UI::WindowsAndMessaging::{
                AppendMenuW, CreatePopupMenu, CreateWindowExW, DefWindowProcW, DestroyMenu,
                DestroyWindow, DispatchMessageW, GetClientRect, GetCursorPos, GetMessageW,
                GetWindowLongPtrW, GetWindowRect, KillTimer, PostQuitMessage, RegisterClassW,
                SetTimer, SetWindowLongPtrW, SetWindowPos, TrackPopupMenu, TranslateMessage,
                UpdateLayeredWindow, CREATESTRUCTW, GWLP_USERDATA, GWL_EXSTYLE, HTBOTTOM,
                HTBOTTOMLEFT, HTBOTTOMRIGHT, HTCAPTION, HTCLIENT, HTLEFT, HTRIGHT, HTTOP,
                HTTOPLEFT, HTTOPRIGHT, HWND_NOTOPMOST, HWND_TOPMOST, MA_NOACTIVATE, MF_CHECKED,
                MF_STRING, MINMAXINFO, MSG, SWP_NOACTIVATE, SWP_NOMOVE, SWP_NOSIZE, TPM_NONOTIFY,
                TPM_RETURNCMD, TPM_RIGHTALIGN, ULW_ALPHA, WINDOW_EX_STYLE, WINDOW_STYLE, WM_CREATE,
                WM_DESTROY, WM_DPICHANGED, WM_ERASEBKGND, WM_EXITSIZEMOVE, WM_GETMINMAXINFO,
                WM_LBUTTONUP, WM_MOUSEACTIVATE, WM_MOVE, WM_MOVING, WM_NCCALCSIZE, WM_NCHITTEST,
                WM_PAINT, WM_SIZE, WM_TIMER, WNDCLASSW, WS_EX_LAYERED, WS_EX_NOACTIVATE,
                WS_EX_TOOLWINDOW, WS_EX_TOPMOST, WS_EX_TRANSPARENT, WS_POPUP, WS_THICKFRAME,
                WS_VISIBLE,
            },
        },
    };

    const BACKGROUND_MARKER: u32 = 0x00010101;
    const RESIZE_BORDER: i32 = 10;
    const CENTER_SNAP_THRESHOLD: i32 = 8;
    const CENTER_SNAP_RELEASE_THRESHOLD: i32 = 22;
    const SET_BUTTON_SIZE: i32 = 30;
    const SET_BUTTON_MARGIN: i32 = 12;
    const SETTINGS_TIMER_ID: usize = 1;
    const SETTINGS_TIMER_MS: u32 = 100;
    const CAPTION_STALE_MS: u64 = 4500;

    struct CaptionWindowState {
        parent_process: Option<windows::Win32::Foundation::HANDLE>,
        render_test_path: Option<std::path::PathBuf>,
        transcript_saving: Cell<bool>,
        control_error: RefCell<Option<String>>,
        control_polled: Cell<Option<Instant>>,
        settings: RefCell<OverlaySettings>,
        placement_file: Option<std::path::PathBuf>,
        settings_file: Option<std::path::PathBuf>,
        settings_modified: Cell<Option<SystemTime>>,
        caption_text: RefCell<String>,
        caption_source_label: RefCell<String>,
        caption_speaker_label: RefCell<String>,
        caption_speaker_confidence: Cell<Option<feelsay_lib::diarization::SpeakerLabelConfidence>>,
        caption_updated_at_ms: Cell<u64>,
        caption_file: Option<std::path::PathBuf>,
        caption_modified: Cell<Option<SystemTime>>,
        snap_x_cursor: Cell<Option<i32>>,
        snap_y_cursor: Cell<Option<i32>>,
        snap_x_suppressed: Cell<bool>,
        snap_y_suppressed: Cell<bool>,
    }

    unsafe extern "system" fn window_proc(
        hwnd: HWND,
        message: u32,
        wparam: WPARAM,
        lparam: LPARAM,
    ) -> LRESULT {
        match message {
            WM_CREATE => {
                let create_struct = lparam.0 as *const CREATESTRUCTW;
                let state = unsafe { (*create_struct).lpCreateParams as *mut CaptionWindowState };
                unsafe {
                    SetWindowLongPtrW(hwnd, GWLP_USERDATA, state as isize);
                    if (*state).settings_file.is_some() || (*state).caption_file.is_some() {
                        let _ = SetTimer(Some(hwnd), SETTINGS_TIMER_ID, SETTINGS_TIMER_MS, None);
                    }
                }
                LRESULT(0)
            }
            WM_NCCALCSIZE => LRESULT(0),
            WM_MOUSEACTIVATE => LRESULT(MA_NOACTIVATE as isize),
            WM_GETMINMAXINFO => {
                unsafe {
                    let info = &mut *(lparam.0 as *mut MINMAXINFO);
                    info.ptMinTrackSize = POINT { x: 280, y: 110 };
                }
                LRESULT(0)
            }
            WM_DPICHANGED => {
                unsafe {
                    let rect = &*(lparam.0 as *const RECT);
                    let _ = SetWindowPos(
                        hwnd,
                        None,
                        rect.left,
                        rect.top,
                        rect.right - rect.left,
                        rect.bottom - rect.top,
                        SWP_NOACTIVATE,
                    );
                    render_caption(hwnd);
                }
                LRESULT(0)
            }
            WM_NCHITTEST => unsafe { hit_test_caption_window(hwnd, lparam) },
            WM_ERASEBKGND => LRESULT(1),
            WM_SIZE => {
                unsafe {
                    render_caption(hwnd);
                    write_placement(hwnd, false);
                }
                LRESULT(0)
            }
            WM_MOVE => {
                unsafe {
                    write_placement(hwnd, false);
                }
                LRESULT(0)
            }
            WM_MOVING => {
                unsafe {
                    snap_to_center(hwnd, lparam);
                    write_moving_placement(hwnd, lparam);
                }
                LRESULT(1)
            }
            WM_EXITSIZEMOVE => {
                unsafe {
                    reset_snap_state(hwnd);
                    persist_overlay_geometry(hwnd);
                }
                LRESULT(0)
            }
            WM_TIMER => {
                if wparam.0 == SETTINGS_TIMER_ID {
                    unsafe {
                        if let Some(state) = caption_state(hwnd) {
                            if state.parent_process.is_some_and(|handle| {
                                windows::Win32::System::Threading::WaitForSingleObject(handle, 0)
                                    != windows::Win32::Foundation::WAIT_TIMEOUT
                            }) {
                                let _ = DestroyWindow(hwnd);
                                return LRESULT(0);
                            }
                        }
                        reload_settings_if_changed(hwnd);
                        reload_caption_if_changed(hwnd);
                        refresh_controls(hwnd);
                    }
                    return LRESULT(0);
                }

                unsafe { DefWindowProcW(hwnd, message, wparam, lparam) }
            }
            WM_LBUTTONUP => unsafe { handle_click(hwnd, lparam) },
            WM_PAINT => {
                unsafe {
                    let mut paint = PAINTSTRUCT::default();
                    let _ = BeginPaint(hwnd, &mut paint);
                    let _ = EndPaint(hwnd, &paint);
                    render_caption(hwnd);
                }
                LRESULT(0)
            }
            WM_DESTROY => {
                unsafe {
                    let _ = KillTimer(Some(hwnd), SETTINGS_TIMER_ID);
                    let state = SetWindowLongPtrW(hwnd, GWLP_USERDATA, 0);
                    if state != 0 {
                        let state = Box::from_raw(state as *mut CaptionWindowState);
                        if let Some(handle) = state.parent_process {
                            let _ = windows::Win32::Foundation::CloseHandle(handle);
                        }
                        drop(state);
                    }
                    PostQuitMessage(0);
                }
                LRESULT(0)
            }
            _ => unsafe { DefWindowProcW(hwnd, message, wparam, lparam) },
        }
    }

    unsafe fn hit_test_caption_window(hwnd: HWND, lparam: LPARAM) -> LRESULT {
        let cursor_x = lparam_low_word(lparam);
        let cursor_y = lparam_high_word(lparam);
        let mut window_rect = RECT::default();

        if GetWindowRect(hwnd, &mut window_rect).is_err() {
            return LRESULT(HTCAPTION as isize);
        }

        if screen_point_in_set_button(window_rect, cursor_x, cursor_y) {
            return LRESULT(HTCLIENT as isize);
        }

        let on_left = cursor_x < window_rect.left + RESIZE_BORDER;
        let on_right = cursor_x >= window_rect.right - RESIZE_BORDER;
        let on_top = cursor_y < window_rect.top + RESIZE_BORDER;
        let on_bottom = cursor_y >= window_rect.bottom - RESIZE_BORDER;

        let hit_test = match (on_left, on_right, on_top, on_bottom) {
            (true, _, true, _) => HTTOPLEFT,
            (_, true, true, _) => HTTOPRIGHT,
            (true, _, _, true) => HTBOTTOMLEFT,
            (_, true, _, true) => HTBOTTOMRIGHT,
            (true, _, _, _) => HTLEFT,
            (_, true, _, _) => HTRIGHT,
            (_, _, true, _) => HTTOP,
            (_, _, _, true) => HTBOTTOM,
            _ => HTCAPTION,
        };

        LRESULT(hit_test as isize)
    }

    fn lparam_low_word(lparam: LPARAM) -> i32 {
        (lparam.0 as u32 & 0xffff) as i16 as i32
    }

    fn lparam_high_word(lparam: LPARAM) -> i32 {
        ((lparam.0 as u32 >> 16) & 0xffff) as i16 as i32
    }

    unsafe fn handle_click(hwnd: HWND, lparam: LPARAM) -> LRESULT {
        if !is_placement_mode(hwnd) {
            let mut rect = RECT::default();
            if GetClientRect(hwnd, &mut rect).is_ok()
                && client_point_in_rect(
                    lparam_low_word(lparam),
                    lparam_high_word(lparam),
                    set_button_rect(rect),
                )
            {
                show_compact_controls(hwnd);
            }
            return LRESULT(0);
        }

        let mut client_rect = RECT::default();
        if GetClientRect(hwnd, &mut client_rect).is_ok()
            && client_point_in_rect(
                lparam_low_word(lparam),
                lparam_high_word(lparam),
                set_button_rect(client_rect),
            )
        {
            write_placement(hwnd, true);
            let _ = DestroyWindow(hwnd);
            return LRESULT(0);
        }

        LRESULT(0)
    }

    unsafe fn refresh_controls(hwnd: HWND) {
        let Some(state) = caption_state(hwnd) else {
            return;
        };
        if state.placement_file.is_some()
            || state
                .control_polled
                .get()
                .is_some_and(|time| time.elapsed() < Duration::from_secs(1))
        {
            return;
        }
        state.control_polled.set(Some(Instant::now()));
        match feelsay_lib::overlay_control::request(None, None) {
            Ok(status) => {
                state
                    .transcript_saving
                    .set(status.transcript.saving_enabled);
                state
                    .control_error
                    .replace(status.error.or(status.transcript.error));
            }
            Err(_) => {
                state
                    .control_error
                    .replace(Some("Controls unavailable — check the main window".into()));
            }
        }
        render_caption(hwnd);
    }

    unsafe fn persist_overlay_geometry(hwnd: HWND) {
        let Some(state) = caption_state(hwnd) else {
            return;
        };
        if state.placement_file.is_some() {
            return;
        }
        let mut rect = RECT::default();
        if GetWindowRect(hwnd, &mut rect).is_err() {
            return;
        }
        let patch = serde_json::json!({"startX": rect.left, "startY": rect.top, "startWidth": (rect.right - rect.left).max(280), "startHeight": (rect.bottom - rect.top).max(110)});
        if let Ok(status) = feelsay_lib::overlay_control::request(None, Some(patch)) {
            state.settings.replace(status.settings);
        }
    }

    unsafe fn show_compact_controls(hwnd: HWND) {
        let Some(state) = caption_state(hwnd) else {
            return;
        };
        state.control_polled.set(None);
        refresh_controls(hwnd);
        let Ok(menu) = CreatePopupMenu() else {
            return;
        };
        let flags = if state.transcript_saving.get() {
            MF_STRING | MF_CHECKED
        } else {
            MF_STRING
        };
        let _ = AppendMenuW(menu, flags, 1, w!("Save transcript locally"));
        for (id, label) in [
            (2, "Larger text"),
            (3, "Smaller text"),
            (4, "Darker background"),
            (5, "Lighter background"),
            (6, "White text"),
            (7, "Yellow text"),
            (8, "Black background"),
            (9, "Blue background"),
        ] {
            let label: Vec<u16> = label.encode_utf16().chain(Some(0)).collect();
            let _ = AppendMenuW(menu, MF_STRING, id, PCWSTR(label.as_ptr()));
        }
        let mut cursor = POINT::default();
        let _ = GetCursorPos(&mut cursor);
        let selected = TrackPopupMenu(
            menu,
            TPM_RETURNCMD | TPM_NONOTIFY | TPM_RIGHTALIGN,
            cursor.x,
            cursor.y,
            None,
            hwnd,
            None,
        )
        .0;
        let _ = DestroyMenu(menu);
        if selected == 0 {
            return;
        }
        let settings = state.settings.borrow().clone();
        let saving = if selected == 1 {
            Some(!state.transcript_saving.get())
        } else {
            None
        };
        let patch = match selected {
            2 => serde_json::json!({"fontSize": settings.font_size + 4}),
            3 => serde_json::json!({"fontSize": settings.font_size.saturating_sub(4)}),
            4 => serde_json::json!({"backgroundOpacity": settings.background_opacity + 0.1}),
            5 => serde_json::json!({"backgroundOpacity": settings.background_opacity - 0.1}),
            6 => serde_json::json!({"textColor": "#ffffff"}),
            7 => serde_json::json!({"textColor": "#ffff80"}),
            8 => serde_json::json!({"backgroundColor": "#000000"}),
            9 => serde_json::json!({"backgroundColor": "#101b30"}),
            _ => serde_json::json!({}),
        };
        match feelsay_lib::overlay_control::request(saving, (selected != 1).then_some(patch)) {
            Ok(status) => {
                state
                    .transcript_saving
                    .set(status.transcript.saving_enabled);
                state
                    .control_error
                    .replace(status.error.or(status.transcript.error));
                state.settings.replace(status.settings);
            }
            Err(_) => {
                state
                    .control_error
                    .replace(Some("Change not confirmed — check Settings".into()));
            }
        }
        render_caption(hwnd);
    }

    unsafe fn render_caption(hwnd: HWND) {
        let Some(state) = caption_state(hwnd) else {
            return;
        };
        let mut settings = state.settings.borrow().clone();
        settings.font_size =
            settings.font_size * windows::Win32::UI::HiDpi::GetDpiForWindow(hwnd).max(96) / 96;

        let mut rect = RECT::default();
        if GetClientRect(hwnd, &mut rect).is_err() {
            return;
        }

        let width = rect.right - rect.left;
        let height = rect.bottom - rect.top;
        if width <= 0 || height <= 0 {
            return;
        }
        settings.font_size = settings.font_size.min(((height - 48).max(20) / 2) as u32);

        let hdc = CreateCompatibleDC(None);
        let mut bitmap_info = BITMAPINFO::default();
        bitmap_info.bmiHeader.biSize = std::mem::size_of_val(&bitmap_info.bmiHeader) as u32;
        bitmap_info.bmiHeader.biWidth = width;
        bitmap_info.bmiHeader.biHeight = -height;
        bitmap_info.bmiHeader.biPlanes = 1;
        bitmap_info.bmiHeader.biBitCount = 32;
        bitmap_info.bmiHeader.biCompression = BI_RGB.0;

        let mut bits = std::ptr::null_mut();
        let Ok(bitmap) =
            CreateDIBSection(Some(hdc), &bitmap_info, DIB_RGB_COLORS, &mut bits, None, 0)
        else {
            let _ = DeleteDC(hdc);
            return;
        };

        let previous_bitmap = SelectObject(hdc, bitmap.into());
        let pixel_count = (width * height) as usize;
        let pixels = std::slice::from_raw_parts_mut(bits as *mut u32, pixel_count);
        pixels.fill(BACKGROUND_MARKER);

        SetBkMode(hdc, TRANSPARENT);

        let format = DT_CENTER | DT_VCENTER | DT_WORDBREAK;
        let caption_text = state.caption_text.borrow();
        let mut label = current_caption_status_label(state);
        if let Some(error) = state.control_error.borrow().as_ref() {
            label = error.clone();
        } else if state.transcript_saving.get() {
            label = if label.is_empty() {
                "● Saving locally".into()
            } else {
                format!("{label} · ● Saving locally")
            };
        }
        let text = if caption_is_stale(state.caption_updated_at_ms.get()) {
            ""
        } else {
            caption_text.as_str()
        };

        let content_rect = RECT {
            left: rect.left + 16,
            right: rect.right - 16,
            top: rect.top + 8,
            bottom: rect.bottom - 12,
        };
        draw_caption_content(hdc, label.as_str(), text, content_rect, &settings, format);

        draw_set_button(
            hdc,
            rect,
            if state.placement_file.is_some() {
                "Set"
            } else {
                "···"
            },
        );

        let (red, green, blue) = hex_to_rgb(&settings.background_color);
        let background_alpha =
            ((settings.background_opacity.clamp(0.0, 1.0) * 255.0).round() as u32).max(1);
        let background_pixel = (background_alpha << 24)
            | ((red as u32 * background_alpha / 255) << 16)
            | ((green as u32 * background_alpha / 255) << 8)
            | (blue as u32 * background_alpha / 255);

        for pixel in pixels.iter_mut() {
            if (*pixel & 0x00ffffff) == BACKGROUND_MARKER {
                *pixel = background_pixel;
            } else {
                *pixel |= 0xff000000;
            }
        }

        if let Some(path) = &state.render_test_path {
            let mut bmp = Vec::with_capacity(54 + pixels.len() * 4);
            bmp.extend_from_slice(b"BM");
            bmp.extend_from_slice(&(54 + pixels.len() as u32 * 4).to_le_bytes());
            bmp.extend_from_slice(&[0; 4]);
            bmp.extend_from_slice(&54u32.to_le_bytes());
            bmp.extend_from_slice(&40u32.to_le_bytes());
            bmp.extend_from_slice(&width.to_le_bytes());
            bmp.extend_from_slice(&(-height).to_le_bytes());
            bmp.extend_from_slice(&1u16.to_le_bytes());
            bmp.extend_from_slice(&32u16.to_le_bytes());
            bmp.extend_from_slice(&[0; 24]);
            for pixel in pixels.iter() {
                bmp.extend_from_slice(&pixel.to_le_bytes());
            }
            std::fs::write(path, bmp).expect("write controlled overlay render");
        }

        let size = SIZE {
            cx: width,
            cy: height,
        };
        let source = POINT { x: 0, y: 0 };
        let blend = windows::Win32::Graphics::Gdi::BLENDFUNCTION {
            BlendOp: AC_SRC_OVER as u8,
            BlendFlags: 0,
            SourceConstantAlpha: 255,
            AlphaFormat: AC_SRC_ALPHA as u8,
        };

        let _ = UpdateLayeredWindow(
            hwnd,
            None,
            None,
            Some(&size),
            Some(hdc),
            Some(&source),
            COLORREF(0),
            Some(&blend),
            ULW_ALPHA,
        );

        SelectObject(hdc, previous_bitmap);
        let _ = DeleteObject(bitmap.into());
        let _ = DeleteDC(hdc);
    }

    unsafe fn caption_state(hwnd: HWND) -> Option<&'static CaptionWindowState> {
        let pointer = GetWindowLongPtrW(hwnd, GWLP_USERDATA) as *const CaptionWindowState;
        pointer.as_ref()
    }

    unsafe fn reload_settings_if_changed(hwnd: HWND) {
        let Some(state) = caption_state(hwnd) else {
            return;
        };
        let Some(path) = state.settings_file.as_ref() else {
            return;
        };
        let Ok(metadata) = std::fs::metadata(path) else {
            return;
        };
        let Ok(modified) = metadata.modified() else {
            return;
        };

        if state.settings_modified.get() == Some(modified) {
            return;
        }

        let Ok(content) = std::fs::read_to_string(path) else {
            return;
        };
        let Ok(settings) = serde_json::from_str::<OverlaySettings>(&content) else {
            return;
        };

        state.settings.replace(settings.normalized());
        state.settings_modified.set(Some(modified));
        apply_window_settings(hwnd);
        render_caption(hwnd);
    }

    unsafe fn reload_caption_if_changed(hwnd: HWND) {
        let Some(state) = caption_state(hwnd) else {
            return;
        };
        let Some(path) = state.caption_file.as_ref() else {
            return;
        };
        let Ok(metadata) = std::fs::metadata(path) else {
            return;
        };
        let Ok(modified) = metadata.modified() else {
            return;
        };

        if state.caption_modified.get() == Some(modified) {
            return;
        }

        let Ok(content) = std::fs::read_to_string(path) else {
            return;
        };
        let Ok(caption) = serde_json::from_str::<feelsay_lib::asr::CaptionRuntimeState>(&content)
        else {
            return;
        };

        state.caption_text.replace(current_caption_text(&caption));
        state
            .caption_source_label
            .replace(current_caption_source_label(&caption));
        state
            .caption_speaker_label
            .replace(current_caption_speaker_label(&caption));
        state
            .caption_speaker_confidence
            .set(caption.speaker_confidence);
        state.caption_updated_at_ms.set(caption.updated_at_ms);
        state.caption_modified.set(Some(modified));
        render_caption(hwnd);
    }

    fn current_caption_text(caption: &feelsay_lib::asr::CaptionRuntimeState) -> String {
        let text = if !caption.provisional_text.trim().is_empty() {
            caption.provisional_text.trim()
        } else if !caption.committed_text.trim().is_empty() {
            caption.committed_text.trim()
        } else {
            caption.text.trim()
        };

        if text.is_empty() {
            "Listening".to_string()
        } else {
            text.to_string()
        }
    }

    fn current_caption_source_label(caption: &feelsay_lib::asr::CaptionRuntimeState) -> String {
        caption
            .source_label
            .as_deref()
            .unwrap_or_default()
            .trim()
            .to_string()
    }

    fn current_caption_speaker_label(caption: &feelsay_lib::asr::CaptionRuntimeState) -> String {
        caption
            .speaker_label
            .as_deref()
            .unwrap_or_default()
            .trim()
            .to_string()
    }

    fn current_caption_status_label(hwnd_state: &CaptionWindowState) -> String {
        let source_label = hwnd_state.caption_source_label.borrow();
        let speaker_label = hwnd_state.caption_speaker_label.borrow();
        let speaker_label = speaker_label.trim();

        if speaker_label.is_empty() {
            return source_label.trim().to_string();
        }

        let speaker_label = match hwnd_state.caption_speaker_confidence.get() {
            Some(confidence) => format!(
                "{} ({})",
                speaker_label,
                feelsay_lib::diarization::speaker_confidence_label(confidence)
            ),
            None => speaker_label.to_string(),
        };
        let source_label = source_label.trim();

        if source_label.is_empty() {
            speaker_label
        } else {
            format!("{source_label} - {speaker_label}")
        }
    }

    fn caption_is_stale(updated_at_ms: u64) -> bool {
        updated_at_ms != 0
            && current_timestamp_ms().saturating_sub(updated_at_ms) > CAPTION_STALE_MS
    }

    fn current_timestamp_ms() -> u64 {
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|duration| duration.as_millis().min(u128::from(u64::MAX)) as u64)
            .unwrap_or(0)
    }

    unsafe fn apply_window_settings(hwnd: HWND) {
        let Some(state) = caption_state(hwnd) else {
            return;
        };
        let settings = state.settings.borrow();

        set_click_through(
            hwnd,
            state.placement_file.is_none() && settings.click_through,
        );

        let mut rect = RECT::default();
        if GetWindowRect(hwnd, &mut rect).is_err() {
            return;
        }

        let x = settings.start_x.unwrap_or(rect.left);
        let y = settings.start_y.unwrap_or(rect.top);
        let _ = SetWindowPos(
            hwnd,
            Some(if settings.always_on_top {
                HWND_TOPMOST
            } else {
                HWND_NOTOPMOST
            }),
            x,
            y,
            settings.start_width as i32,
            settings.start_height as i32,
            SWP_NOACTIVATE,
        );
    }

    unsafe fn set_click_through(hwnd: HWND, enabled: bool) {
        let current_style = GetWindowLongPtrW(hwnd, GWL_EXSTYLE);
        let transparent_style = WS_EX_TRANSPARENT.0 as isize;
        let next_style = if enabled {
            current_style | transparent_style
        } else {
            current_style & !transparent_style
        };

        if next_style == current_style {
            return;
        }

        SetWindowLongPtrW(hwnd, GWL_EXSTYLE, next_style);
        let _ = SetWindowPos(
            hwnd,
            None,
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
        );
    }

    unsafe fn is_placement_mode(hwnd: HWND) -> bool {
        caption_state(hwnd)
            .and_then(|state| state.placement_file.as_ref())
            .is_some()
    }

    unsafe fn write_placement(hwnd: HWND, is_accepted: bool) {
        let Some(state) = caption_state(hwnd) else {
            return;
        };
        let Some(path) = state.placement_file.as_ref() else {
            return;
        };

        let mut rect = RECT::default();
        if GetWindowRect(hwnd, &mut rect).is_err() {
            return;
        }

        let placement = OverlayPlacement {
            x: rect.left,
            y: rect.top,
            width: (rect.right - rect.left).max(0) as u32,
            height: (rect.bottom - rect.top).max(0) as u32,
            is_accepted,
        };

        write_placement_file(path, placement);
    }

    unsafe fn write_moving_placement(hwnd: HWND, lparam: LPARAM) {
        let Some(state) = caption_state(hwnd) else {
            return;
        };
        let Some(path) = state.placement_file.as_ref() else {
            return;
        };

        let rect = *(lparam.0 as *const RECT);
        let placement = OverlayPlacement {
            x: rect.left,
            y: rect.top,
            width: (rect.right - rect.left).max(0) as u32,
            height: (rect.bottom - rect.top).max(0) as u32,
            is_accepted: false,
        };

        write_placement_file(path, placement);
    }

    fn write_placement_file(path: &std::path::Path, placement: OverlayPlacement) {
        if let Ok(content) = serde_json::to_string(&placement) {
            let _ = std::fs::write(path, content);
        }
    }

    unsafe fn snap_to_center(hwnd: HWND, lparam: LPARAM) {
        let Some(state) = caption_state(hwnd) else {
            return;
        };
        if state.placement_file.is_none() {
            return;
        }

        let mut cursor = POINT::default();
        if GetCursorPos(&mut cursor).is_err() {
            return;
        }

        let rect = &mut *(lparam.0 as *mut RECT);
        let monitor = MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST);
        let mut monitor_info = MONITORINFO {
            cbSize: std::mem::size_of::<MONITORINFO>() as u32,
            ..Default::default()
        };

        if !GetMonitorInfoW(monitor, &mut monitor_info).as_bool() {
            return;
        }

        let work_area = monitor_info.rcWork;
        let width = rect.right - rect.left;
        let height = rect.bottom - rect.top;
        let monitor_center_x = work_area.left + (work_area.right - work_area.left) / 2;
        let monitor_center_y = work_area.top + (work_area.bottom - work_area.top) / 2;
        let window_center_x = rect.left + width / 2;
        let window_center_y = rect.top + height / 2;

        if should_snap_axis(
            &state.snap_x_cursor,
            &state.snap_x_suppressed,
            cursor.x,
            window_center_x - monitor_center_x,
        ) {
            rect.left = monitor_center_x - width / 2;
            rect.right = rect.left + width;
        }

        if should_snap_axis(
            &state.snap_y_cursor,
            &state.snap_y_suppressed,
            cursor.y,
            window_center_y - monitor_center_y,
        ) {
            rect.top = monitor_center_y - height / 2;
            rect.bottom = rect.top + height;
        }
    }

    fn should_snap_axis(
        anchor_cursor: &Cell<Option<i32>>,
        is_suppressed: &Cell<bool>,
        cursor_position: i32,
        center_distance: i32,
    ) -> bool {
        if let Some(anchor_position) = anchor_cursor.get() {
            if (cursor_position - anchor_position).abs() <= CENTER_SNAP_RELEASE_THRESHOLD {
                return true;
            }

            anchor_cursor.set(None);
            is_suppressed.set(true);
            return false;
        }

        if is_suppressed.get() {
            if center_distance.abs() > CENTER_SNAP_THRESHOLD {
                is_suppressed.set(false);
            }
            return false;
        }

        if center_distance.abs() <= CENTER_SNAP_THRESHOLD {
            anchor_cursor.set(Some(cursor_position));
            return true;
        }

        false
    }

    unsafe fn reset_snap_state(hwnd: HWND) {
        let Some(state) = caption_state(hwnd) else {
            return;
        };

        state.snap_x_cursor.set(None);
        state.snap_y_cursor.set(None);
        state.snap_x_suppressed.set(false);
        state.snap_y_suppressed.set(false);
    }

    unsafe fn draw_set_button(hdc: HDC, client_rect: RECT, label: &str) {
        let button_rect = set_button_rect(client_rect);
        let brush = CreateSolidBrush(color_ref("#00d1b2"));
        let pen = CreatePen(PS_SOLID, 1, color_ref("#ffffff"));
        let previous_brush = SelectObject(hdc, brush.into());
        let previous_pen = SelectObject(hdc, pen.into());

        let _ = Ellipse(
            hdc,
            button_rect.left,
            button_rect.top,
            button_rect.right,
            button_rect.bottom,
        );

        let button_font = CreateFontW(
            -10,
            0,
            0,
            0,
            700,
            0,
            0,
            0,
            DEFAULT_CHARSET,
            OUT_DEFAULT_PRECIS,
            CLIP_DEFAULT_PRECIS,
            ANTIALIASED_QUALITY,
            0,
            w!("Segoe UI"),
        );
        let previous_font = SelectObject(hdc, button_font.into());
        SetTextColor(hdc, color_ref("#ffffff"));
        SetBkMode(hdc, TRANSPARENT);

        let mut label = label.encode_utf16().collect::<Vec<u16>>();
        let mut label_rect = button_rect;
        DrawTextW(
            hdc,
            &mut label,
            &mut label_rect,
            DT_CENTER | DT_VCENTER | DT_SINGLELINE,
        );

        SelectObject(hdc, previous_font);
        SelectObject(hdc, previous_pen);
        SelectObject(hdc, previous_brush);
        let _ = DeleteObject(button_font.into());
        let _ = DeleteObject(pen.into());
        let _ = DeleteObject(brush.into());
    }

    fn set_button_rect(client_rect: RECT) -> RECT {
        RECT {
            left: client_rect.right - SET_BUTTON_MARGIN - SET_BUTTON_SIZE,
            top: client_rect.top + SET_BUTTON_MARGIN,
            right: client_rect.right - SET_BUTTON_MARGIN,
            bottom: client_rect.top + SET_BUTTON_MARGIN + SET_BUTTON_SIZE,
        }
    }

    fn screen_point_in_set_button(window_rect: RECT, x: i32, y: i32) -> bool {
        let client_rect = RECT {
            left: 0,
            top: 0,
            right: window_rect.right - window_rect.left,
            bottom: window_rect.bottom - window_rect.top,
        };
        let button_rect = set_button_rect(client_rect);
        client_point_in_rect(x - window_rect.left, y - window_rect.top, button_rect)
    }

    fn client_point_in_rect(x: i32, y: i32, rect: RECT) -> bool {
        x >= rect.left && x < rect.right && y >= rect.top && y < rect.bottom
    }

    fn color_ref(color: &str) -> COLORREF {
        let (red, green, blue) = hex_to_rgb(color);
        COLORREF((red as u32) | ((green as u32) << 8) | ((blue as u32) << 16))
    }

    fn offset_rect(rect: RECT, x: i32, y: i32) -> RECT {
        RECT {
            left: rect.left + x,
            top: rect.top + y,
            right: rect.right + x,
            bottom: rect.bottom + y,
        }
    }

    unsafe fn draw_caption_content(
        hdc: HDC,
        source_label: &str,
        text: &str,
        rect: RECT,
        settings: &OverlaySettings,
        format: DRAW_TEXT_FORMAT,
    ) {
        let source_label = source_label.trim();
        if source_label.is_empty() {
            draw_caption_lines(hdc, text, rect, settings, format);
            return;
        }

        let height = rect.bottom - rect.top;
        let label_height = ((settings.font_size as f32 * 0.7).round() as i32).clamp(18, 34);
        let gap = 4;
        let label_rect = RECT {
            left: rect.left,
            top: rect.top + (height / 10).min(16),
            right: rect.right - 36,
            bottom: rect.top + (height / 10).min(16) + label_height,
        };
        let caption_rect = RECT {
            left: rect.left,
            top: label_rect.bottom + gap,
            right: rect.right,
            bottom: rect.bottom,
        };
        let label_size = ((settings.font_size as f32) * 0.42)
            .round()
            .clamp(14.0, 24.0) as u32;

        draw_caption_text(
            hdc,
            source_label,
            label_rect,
            settings,
            label_size,
            DT_CENTER | DT_VCENTER | DT_SINGLELINE,
        );
        draw_caption_lines(hdc, text, caption_rect, settings, format);
    }

    unsafe fn draw_caption_lines(
        hdc: HDC,
        text: &str,
        rect: RECT,
        settings: &OverlaySettings,
        format: DRAW_TEXT_FORMAT,
    ) {
        if let Some((original, translation)) = text.split_once('\n') {
            let midpoint = rect.top + (rect.bottom - rect.top) / 2;
            let gap = 4;
            let original_rect = RECT {
                left: rect.left,
                top: rect.top,
                right: rect.right,
                bottom: midpoint - gap,
            };
            let translation_rect = RECT {
                left: rect.left,
                top: midpoint + gap,
                right: rect.right,
                bottom: rect.bottom,
            };
            let original_size = ((settings.font_size as f32) * settings.original_line_scale)
                .round()
                .clamp(18.0, settings.font_size as f32) as u32;

            draw_caption_text(
                hdc,
                original,
                original_rect,
                settings,
                original_size,
                format,
            );
            draw_caption_text(
                hdc,
                translation,
                translation_rect,
                settings,
                settings.font_size,
                format,
            );
            return;
        }

        draw_caption_text(hdc, text, rect, settings, settings.font_size, format);
    }

    unsafe fn draw_caption_text(
        hdc: HDC,
        text: &str,
        rect: RECT,
        settings: &OverlaySettings,
        font_size: u32,
        format: DRAW_TEXT_FORMAT,
    ) {
        // An empty Vec has a dangling pointer; DrawTextW may dereference it even at length zero.
        if text.trim().is_empty() {
            return;
        }
        let available_height = (rect.bottom - rect.top).max(1) as u32;
        let font_size = font_size.min((available_height * 3 / 4).max(8));
        let font_family: Vec<u16> = settings.font_family.encode_utf16().chain([0]).collect();
        let font = CreateFontW(
            -(font_size as i32),
            0,
            0,
            0,
            settings.font_weight.win32_weight(),
            0,
            0,
            0,
            DEFAULT_CHARSET,
            OUT_DEFAULT_PRECIS,
            CLIP_DEFAULT_PRECIS,
            ANTIALIASED_QUALITY,
            0,
            PCWSTR(font_family.as_ptr()),
        );
        let previous_font = SelectObject(hdc, font.into());

        let mut words: Vec<&str> = text.split_whitespace().collect();
        let mut display = words.join(" ");
        let mut measured;
        let max_height = (rect.bottom - rect.top).min(font_size as i32 * 4);
        loop {
            measured = rect;
            let mut buffer: Vec<u16> = display.encode_utf16().collect();
            DrawTextW(hdc, &mut buffer, &mut measured, format | DT_CALCRECT);
            if measured.bottom - measured.top <= max_height || words.len() <= 1 {
                break;
            }
            words.remove(0);
            display = words.join(" ");
        }
        let text = display.as_str();
        let rect = RECT {
            top: rect.top
                + ((rect.bottom - rect.top - (measured.bottom - measured.top)) / 2).max(0),
            ..rect
        };

        if settings.outline_width > 0 {
            SetTextColor(hdc, color_ref(&settings.outline_color));
            let outline_width = settings.outline_width as i32;
            for x in -outline_width..=outline_width {
                for y in -outline_width..=outline_width {
                    if x == 0 && y == 0 {
                        continue;
                    }
                    let mut outline_rect = offset_rect(rect, x, y);
                    let mut outline_text: Vec<u16> = text.encode_utf16().collect();
                    DrawTextW(hdc, &mut outline_text, &mut outline_rect, format);
                }
            }
        }

        SetTextColor(hdc, color_ref(&settings.text_color));
        let mut caption_text: Vec<u16> = text.encode_utf16().collect();
        let mut text_rect = rect;
        DrawTextW(hdc, &mut caption_text, &mut text_rect, format);

        SelectObject(hdc, previous_font);
        let _ = DeleteObject(font.into());
    }

    unsafe {
        let render_test_path = diagnostic_arg_value("--overlay-render-test");
        let parent_process = match std::env::var("FEELSAY_PARENT_PID")
            .ok()
            .and_then(|value| value.parse::<u32>().ok())
        {
            Some(pid) => match windows::Win32::System::Threading::OpenProcess(
                windows::Win32::System::Threading::PROCESS_SYNCHRONIZE,
                false,
                pid,
            ) {
                Ok(handle) => Some(handle),
                Err(_) => return,
            },
            None => None,
        };
        let hidden_test = render_test_path.is_some();
        let previous_foreground = windows::Win32::UI::WindowsAndMessaging::GetForegroundWindow();
        let class_name = w!("FeelSayCaptionWindowChild");
        let window_class = WNDCLASSW {
            lpfnWndProc: Some(window_proc),
            lpszClassName: class_name,
            ..Default::default()
        };

        RegisterClassW(&window_class);

        let mut cursor = POINT::default();
        let _ = GetCursorPos(&mut cursor);
        let proposed = RECT {
            left: settings.start_x.unwrap_or(cursor.x),
            top: settings.start_y.unwrap_or(cursor.y),
            right: settings.start_x.unwrap_or(cursor.x) + settings.start_width as i32,
            bottom: settings.start_y.unwrap_or(cursor.y) + settings.start_height as i32,
        };
        let monitor = MonitorFromRect(&proposed, MONITOR_DEFAULTTONEAREST);
        let mut info = MONITORINFO {
            cbSize: std::mem::size_of::<MONITORINFO>() as u32,
            ..Default::default()
        };
        let _ = GetMonitorInfoW(monitor, &mut info);
        let work = info.rcWork;
        let width = (settings.start_width as i32).min((work.right - work.left).max(280));
        let height = (settings.start_height as i32).min((work.bottom - work.top).max(110));
        let x = settings
            .start_x
            .unwrap_or(work.left + (work.right - work.left - width) / 2)
            .clamp(work.left, (work.right - width).max(work.left));
        let y = settings
            .start_y
            .unwrap_or(work.bottom - height - 60)
            .clamp(work.top, (work.bottom - height).max(work.top));
        let mut settings = settings;
        settings.start_x = Some(x);
        settings.start_y = Some(y);
        settings.start_width = width as u32;
        settings.start_height = height as u32;
        let settings_modified = settings_file
            .as_ref()
            .and_then(|path| std::fs::metadata(path).ok())
            .and_then(|metadata| metadata.modified().ok());
        let caption_modified = caption_file
            .as_ref()
            .and_then(|path| std::fs::metadata(path).ok())
            .and_then(|metadata| metadata.modified().ok());
        let caption_text = caption_file
            .as_ref()
            .and_then(|path| std::fs::read_to_string(path).ok())
            .and_then(|content| {
                serde_json::from_str::<feelsay_lib::asr::CaptionRuntimeState>(&content).ok()
            })
            .map(|caption| current_caption_text(&caption))
            .filter(|text| !text.trim().is_empty())
            .unwrap_or_else(|| "Listening".to_string());
        let caption_source_label = caption_file
            .as_ref()
            .and_then(|path| std::fs::read_to_string(path).ok())
            .and_then(|content| {
                serde_json::from_str::<feelsay_lib::asr::CaptionRuntimeState>(&content).ok()
            })
            .map(|caption| current_caption_source_label(&caption))
            .unwrap_or_default();
        let caption_speaker = caption_file
            .as_ref()
            .and_then(|path| std::fs::read_to_string(path).ok())
            .and_then(|content| {
                serde_json::from_str::<feelsay_lib::asr::CaptionRuntimeState>(&content).ok()
            });
        let caption_speaker_label = caption_speaker
            .as_ref()
            .map(current_caption_speaker_label)
            .unwrap_or_default();
        let caption_speaker_confidence =
            caption_speaker.and_then(|caption| caption.speaker_confidence);
        let caption_updated_at_ms = caption_file
            .as_ref()
            .and_then(|path| std::fs::read_to_string(path).ok())
            .and_then(|content| {
                serde_json::from_str::<feelsay_lib::asr::CaptionRuntimeState>(&content).ok()
            })
            .map(|caption| caption.updated_at_ms)
            .unwrap_or(0);
        let state = Box::into_raw(Box::new(CaptionWindowState {
            parent_process,
            render_test_path,
            transcript_saving: Cell::new(false),
            control_error: RefCell::new(None),
            control_polled: Cell::new(None),
            settings: RefCell::new(settings),
            placement_file,
            settings_file,
            settings_modified: Cell::new(settings_modified),
            caption_text: RefCell::new(caption_text),
            caption_source_label: RefCell::new(caption_source_label),
            caption_speaker_label: RefCell::new(caption_speaker_label),
            caption_speaker_confidence: Cell::new(caption_speaker_confidence),
            caption_updated_at_ms: Cell::new(caption_updated_at_ms),
            caption_file,
            caption_modified: Cell::new(caption_modified),
            snap_x_cursor: Cell::new(None),
            snap_y_cursor: Cell::new(None),
            snap_x_suppressed: Cell::new(false),
            snap_y_suppressed: Cell::new(false),
        }));

        if CreateWindowExW(
            WINDOW_EX_STYLE(
                WS_EX_LAYERED.0 | WS_EX_TOPMOST.0 | WS_EX_TOOLWINDOW.0 | WS_EX_NOACTIVATE.0,
            ),
            class_name,
            w!("FeelSay Caption Window"),
            WINDOW_STYLE(
                WS_POPUP.0 | (if hidden_test { 0 } else { WS_VISIBLE.0 }) | WS_THICKFRAME.0,
            ),
            x,
            y,
            width,
            height,
            None,
            None,
            None,
            Some(state.cast::<c_void>()),
        )
        .map(|hwnd| {
            apply_window_settings(hwnd);
            render_caption(hwnd);
            write_placement(hwnd, false);
            if hidden_test {
                assert!(!windows::Win32::UI::WindowsAndMessaging::IsWindowVisible(hwnd).as_bool());
                assert_eq!(
                    windows::Win32::UI::WindowsAndMessaging::GetForegroundWindow(),
                    previous_foreground
                );
                let _ = DestroyWindow(hwnd);
            }
        })
        .is_err()
        {
            drop(Box::from_raw(state));
            return;
        }

        if hidden_test {
            return;
        }

        let mut message = MSG::default();
        while GetMessageW(&mut message, None, 0, 0).into() {
            let _ = TranslateMessage(&message);
            DispatchMessageW(&message);
        }
    }
}

#[cfg(not(windows))]
fn run_caption_window_child(
    _settings: feelsay_lib::overlay_settings::OverlaySettings,
    _placement_file: Option<std::path::PathBuf>,
    _settings_file: Option<std::path::PathBuf>,
    _caption_file: Option<std::path::PathBuf>,
) {
    eprintln!("caption window child process is Windows-only for now");
}
