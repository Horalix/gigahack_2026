pub mod app_error;
pub mod app_state;
#[cfg(target_os = "windows")]
pub mod application_audio;
pub mod asr;
pub mod audio_capture;
pub mod caption_settings;
pub mod commands;
pub mod diarization;
pub mod model_settings;
pub mod overlay_control;
pub mod overlay_settings;
pub mod performance_settings;
pub mod persistence;
pub mod platform;
pub mod source;
pub mod transcript;
pub mod translation;

use app_state::AppState;
use tauri::{Emitter, Manager};

const EVENT_OPEN_SETTINGS: &str = "control-open-settings";
const EVENT_TOGGLE_CAPTIONS: &str = "control-toggle-captions";
const EVENT_TOGGLE_OVERLAY: &str = "control-toggle-overlay";
const EVENT_CLICK_THROUGH_TOGGLED: &str = "control-click-through-toggled";

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            app.manage(AppState::new(app.path().app_data_dir()?));
            #[cfg(target_os = "windows")]
            {
                *app.state::<AppState>().overlay_control.lock().unwrap() =
                    Some(overlay_control::start(app.handle().clone())?);
            }
            setup_tray(app)?;
            setup_global_shortcuts(app)?;
            Ok(())
        })
        .on_window_event(|window, event| {
            if window.label() == "main"
                && matches!(event, tauri::WindowEvent::CloseRequested { .. })
            {
                println!("app: main close requested; cleaning up audio meter");
                let app = window.app_handle();
                if let Some(state) = app.try_state::<AppState>() {
                    let _ = state.audio_meter().stop();
                    let _ = state.transcripts().finish_session();
                    let _ = state.close_caption_process();
                    let _ = state.stop_overlay_placement();
                    state.clear_caption_text();
                }
            }
        })
        .invoke_handler(tauri::generate_handler![
            commands::get_app_metadata,
            commands::get_app_status,
            commands::start_audio_meter,
            commands::stop_audio_meter,
            commands::open_caption_window,
            commands::close_caption_window,
            commands::is_caption_window_open,
            commands::get_overlay_settings,
            commands::save_overlay_settings,
            commands::get_overlay_settings_store,
            commands::save_overlay_settings_store,
            commands::patch_overlay_settings,
            commands::select_overlay_settings_profile,
            commands::start_overlay_placement,
            commands::get_overlay_placement,
            commands::stop_overlay_placement,
            commands::get_platform_capabilities,
            commands::list_available_sources,
            commands::get_source_previews,
            commands::get_model_settings_store,
            commands::save_model_settings_store,
            commands::get_model_status,
            commands::install_default_asr_assets,
            commands::run_asr_model_diagnostic,
            commands::run_caption_flow_diagnostic,
            commands::get_caption_settings,
            commands::save_caption_settings,
            commands::get_translation_settings,
            commands::save_translation_settings,
            commands::get_translation_engine_status,
            commands::run_translation_engine_diagnostic,
            commands::get_performance_settings,
            commands::save_performance_settings,
            commands::get_transcript_settings,
            commands::get_transcript_status,
            commands::read_transcript_session,
            commands::delete_transcript_session,
            commands::save_transcript_settings,
            commands::start_transcript_session,
            commands::append_transcript_segment,
            commands::finish_transcript_session,
            commands::list_transcript_sessions,
            commands::export_transcript_session,
            commands::open_transcript_exports
        ])
        .run(tauri::generate_context!())
        .expect("error while running Feelsay");
}

fn setup_tray(app: &mut tauri::App) -> Result<(), Box<dyn std::error::Error>> {
    use tauri::{
        menu::{Menu, MenuItem, PredefinedMenuItem},
        tray::TrayIconBuilder,
    };

    let show = MenuItem::with_id(app, "show", "Show Feelsay", true, None::<&str>)?;
    let toggle = MenuItem::with_id(app, "toggle", "Start / Stop", true, None::<&str>)?;
    let overlay = MenuItem::with_id(app, "overlay", "Show / Hide Overlay", true, None::<&str>)?;
    let click_through = MenuItem::with_id(
        app,
        "click-through",
        "Toggle Click-through",
        true,
        None::<&str>,
    )?;
    let settings = MenuItem::with_id(app, "settings", "Settings", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;
    let separator = PredefinedMenuItem::separator(app)?;
    let menu = Menu::with_items(
        app,
        &[
            &show,
            &toggle,
            &overlay,
            &click_through,
            &settings,
            &separator,
            &quit,
        ],
    )?;

    let mut builder = TrayIconBuilder::new()
        .menu(&menu)
        .show_menu_on_left_click(true)
        .on_menu_event(|app, event| match event.id().as_ref() {
            "show" => show_main_window(app),
            "toggle" => emit_control(app, EVENT_TOGGLE_CAPTIONS),
            "overlay" => emit_control(app, EVENT_TOGGLE_OVERLAY),
            "click-through" => toggle_click_through(app),
            "settings" => {
                show_main_window(app);
                emit_control(app, EVENT_OPEN_SETTINGS);
            }
            "quit" => quit_app(app),
            _ => {}
        });

    if let Some(icon) = app.default_window_icon() {
        builder = builder.icon(icon.clone());
    }

    builder.build(app)?;
    Ok(())
}

fn setup_global_shortcuts(app: &mut tauri::App) -> Result<(), Box<dyn std::error::Error>> {
    use tauri_plugin_global_shortcut::{
        Code, GlobalShortcutExt, Modifiers, Shortcut, ShortcutState,
    };

    let toggle_captions = Shortcut::new(Some(Modifiers::CONTROL | Modifiers::SHIFT), Code::KeyC);
    let toggle_overlay = Shortcut::new(Some(Modifiers::CONTROL | Modifiers::SHIFT), Code::KeyO);
    let click_through_shortcut =
        Shortcut::new(Some(Modifiers::CONTROL | Modifiers::SHIFT), Code::KeyX);

    let shortcuts = [toggle_captions, toggle_overlay, click_through_shortcut];
    let handler_toggle_captions = toggle_captions;
    let handler_toggle_overlay = toggle_overlay;
    let handler_toggle_click_through = click_through_shortcut;

    app.handle().plugin(
        tauri_plugin_global_shortcut::Builder::new()
            .with_handler(move |app, shortcut, event| {
                if event.state() != ShortcutState::Pressed {
                    return;
                }

                if shortcut == &handler_toggle_captions {
                    emit_control(app, EVENT_TOGGLE_CAPTIONS);
                } else if shortcut == &handler_toggle_overlay {
                    emit_control(app, EVENT_TOGGLE_OVERLAY);
                } else if shortcut == &handler_toggle_click_through {
                    toggle_click_through(app);
                }
            })
            .build(),
    )?;

    for shortcut in shortcuts {
        // Another application may own a shortcut; the main controls must still work.
        if let Err(error) = app.global_shortcut().register(shortcut) {
            eprintln!("Shortcut unavailable: {error}");
        }
    }

    Ok(())
}

fn emit_control(app: &tauri::AppHandle, event: &str) {
    let _ = app.emit(event, ());
}

fn show_main_window(app: &tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
}

fn toggle_click_through(app: &tauri::AppHandle) {
    if let Some(state) = app.try_state::<AppState>() {
        if let Ok(is_enabled) = state.toggle_active_profile_click_through() {
            let _ = app.emit(EVENT_CLICK_THROUGH_TOGGLED, is_enabled);
        }
    }
}

fn quit_app(app: &tauri::AppHandle) {
    if let Some(state) = app.try_state::<AppState>() {
        let _ = state.audio_meter().stop();
        let _ = state.transcripts().finish_session();
        let _ = state.close_caption_process();
        let _ = state.stop_overlay_placement();
        state.clear_caption_text();
    }

    app.exit(0);
}
