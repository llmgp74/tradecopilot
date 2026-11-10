//! Tauri commands the desktop frontend invokes.

use std::fs::OpenOptions;
use std::io::Write;
use std::path::{Path, PathBuf};

use serde::Serialize;
use tauri::{AppHandle, Emitter, Manager, State};

use crate::agent::{AgentState, log_path, spawn, stop};
use crate::runtime;

#[derive(Clone, Serialize)]
struct ProgressPayload {
    step: String,
    line: String,
}

#[derive(Clone, Serialize)]
struct FailurePayload {
    message: String,
    log_path: String,
}

/// Resolves the managed runtime directory and the bundled resources.
fn paths(app: &AppHandle) -> Result<(PathBuf, PathBuf), String> {
    let home = app
        .path()
        .home_dir()
        .map_err(|error| format!("Cannot find the home directory: {error}"))?;
    let runtime = home.join(".tradecopilot").join("runtime");
    let resources = app
        .path()
        .resource_dir()
        .map_err(|error| format!("Cannot find the app resources: {error}"))?;
    Ok((runtime, resources))
}

/// Appends one setup line to the shared log.
fn append_log(path: &Path, step: &str, line: &str) {
    if let Some(parent) = path.parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    if let Ok(mut file) = OpenOptions::new().create(true).append(true).open(path) {
        let _ = writeln!(file, "{step}: {line}");
    }
}

/// Installs the runtime when needed, then starts the agent.
fn bootstrap_inner(app: &AppHandle, state: &AgentState) -> Result<(), String> {
    let (runtime_dir, resources) = paths(app)?;
    let mut setup = state
        .setup
        .lock()
        .map_err(|_| "Agent state is poisoned.".to_string())?;
    if let Some(handle) = setup.as_ref()
        && !handle.is_finished()
    {
        return Ok(());
    }

    match runtime::status(&runtime_dir, env!("CARGO_PKG_VERSION")) {
        runtime::Status::Installed => spawn(app, state, &runtime_dir, &resources),
        runtime::Status::Missing | runtime::Status::Broken => {
            let app_handle = app.clone();
            let worker_state = AgentState::clone(state);
            let worker_runtime = runtime_dir.clone();
            let worker_resources = resources.clone();
            let log = log_path(app);
            let handle = std::thread::spawn(move || {
                let emit_log = log.clone();
                let result = runtime::install_steps(
                    &worker_runtime,
                    &worker_resources,
                    &mut |step, line| {
                        append_log(&emit_log, step, line);
                        let _ = app_handle.emit(
                            "setup_progress",
                            ProgressPayload {
                                step: step.to_string(),
                                line: line.to_string(),
                            },
                        );
                    },
                    &worker_state.uv_child,
                );
                match result {
                    Ok(()) => {
                        if let Err(message) = spawn(
                            &app_handle,
                            &worker_state,
                            &worker_runtime,
                            &worker_resources,
                        ) {
                            let _ = app_handle.emit(
                                "setup_failed",
                                FailurePayload {
                                    message,
                                    log_path: log.display().to_string(),
                                },
                            );
                        }
                    }
                    Err(message) => {
                        let _ = app_handle.emit(
                            "setup_failed",
                            FailurePayload {
                                message,
                                log_path: log.display().to_string(),
                            },
                        );
                    }
                }
            });
            *setup = Some(handle);
            Ok(())
        }
    }
}

/// Installs the runtime if needed and starts the agent. Idempotent.
#[tauri::command]
pub fn bootstrap(app: AppHandle, state: State<'_, AgentState>) -> Result<(), String> {
    if cfg!(debug_assertions) {
        return Ok(());
    }
    bootstrap_inner(&app, &state)
}

/// Stops the agent and starts a fresh one.
#[tauri::command]
pub fn restart_agent(app: AppHandle, state: State<'_, AgentState>) -> Result<(), String> {
    stop(&state);
    if cfg!(debug_assertions) {
        return Ok(());
    }
    bootstrap_inner(&app, &state)
}
