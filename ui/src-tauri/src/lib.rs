mod agent;
mod commands;
mod runtime;
#[cfg(windows)]
mod windows_job;

use tauri::Manager;

/// Hides the window instead of closing it on macOS.
///
/// macOS apps keep running with their windows closed; the dock icon brings the
/// window back. Other platforms close the app from the window control.
#[cfg(target_os = "macos")]
fn keep_running_on_close(window: &tauri::Window, event: &tauri::WindowEvent) {
    if let tauri::WindowEvent::CloseRequested { api, .. } = event {
        api.prevent_close();
        let _ = window.hide();
    }
}

/// Leaves window closing to the platform on non-macOS systems.
#[cfg(not(target_os = "macos"))]
fn keep_running_on_close(_window: &tauri::Window, _event: &tauri::WindowEvent) {}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
                let _ = window.set_focus();
            }
        }))
        .on_window_event(keep_running_on_close)
        .plugin(tauri_plugin_opener::init())
        .manage(agent::AgentState::default())
        .invoke_handler(tauri::generate_handler![
            commands::bootstrap,
            commands::restart_agent,
            commands::cached_model_catalog,
            commands::refresh_model_catalog,
        ])
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app, event| match event {
            // The dock icon reopens the hidden window.
            tauri::RunEvent::Reopen { .. } => {
                if let Some(window) = app.get_webview_window("main") {
                    let _ = window.show();
                    let _ = window.set_focus();
                }
            }
            tauri::RunEvent::ExitRequested { .. } | tauri::RunEvent::Exit => {
                agent::stop(&app.state::<agent::AgentState>());
            }
            _ => {}
        });
}
