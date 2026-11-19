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

    let digest = runtime::requirements_digest(&resources);
    match runtime::status(&runtime_dir, env!("CARGO_PKG_VERSION"), &digest) {
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

const CATALOG_URL: &str = "https://models.dev/api.json";
const CATALOG_FILE: &str = "models-catalog.json";

/// Resolves the cached catalog path in the app data directory.
fn catalog_path(app: &AppHandle) -> Result<PathBuf, String> {
    app.path()
        .app_data_dir()
        .map(|directory| directory.join(CATALOG_FILE))
        .map_err(|error| format!("Cannot find the app data directory: {error}"))
}

/// Keeps only the provider and model fields the app renders.
fn slim_catalog(raw: &str) -> Result<String, String> {
    let parsed: serde_json::Value =
        serde_json::from_str(raw).map_err(|error| format!("Invalid catalog: {error}"))?;
    let providers = parsed
        .as_object()
        .ok_or_else(|| "The catalog is not an object.".to_string())?;
    if providers.is_empty() {
        return Err("The catalog has no providers.".to_string());
    }
    let mut slim_providers = serde_json::Map::new();
    for (id, provider) in providers {
        let Some(provider) = provider.as_object() else {
            continue;
        };
        let mut models = serde_json::Map::new();
        if let Some(catalog_models) = provider.get("models").and_then(|value| value.as_object()) {
            for (model_id, model) in catalog_models {
                let Some(model) = model.as_object() else {
                    continue;
                };
                let mut entry = serde_json::Map::new();
                entry.insert(
                    "name".to_string(),
                    model.get("name").cloned().unwrap_or_default(),
                );
                entry.insert(
                    "reasoning".to_string(),
                    serde_json::Value::Bool(
                        model
                            .get("reasoning")
                            .and_then(|value| value.as_bool())
                            .unwrap_or(false),
                    ),
                );
                entry.insert(
                    "reasoning_options".to_string(),
                    model
                        .get("reasoning_options")
                        .cloned()
                        .unwrap_or_else(|| serde_json::Value::Array(Vec::new())),
                );
                entry.insert(
                    "tool_call".to_string(),
                    serde_json::Value::Bool(
                        model
                            .get("tool_call")
                            .and_then(|value| value.as_bool())
                            .unwrap_or(false),
                    ),
                );
                models.insert(model_id.clone(), serde_json::Value::Object(entry));
            }
        }
        let mut entry = serde_json::Map::new();
        entry.insert(
            "name".to_string(),
            provider
                .get("name")
                .cloned()
                .unwrap_or_else(|| serde_json::Value::String(id.clone())),
        );
        for field in ["doc", "api", "npm"] {
            entry.insert(
                field.to_string(),
                provider
                    .get(field)
                    .cloned()
                    .unwrap_or_else(|| serde_json::Value::String(String::new())),
            );
        }
        entry.insert("models".to_string(), serde_json::Value::Object(models));
        slim_providers.insert(id.clone(), serde_json::Value::Object(entry));
    }
    let mut root = serde_json::Map::new();
    root.insert(
        "providers".to_string(),
        serde_json::Value::Object(slim_providers),
    );
    Ok(serde_json::Value::Object(root).to_string())
}

/// Validates that a cached body is already in the slim shape.
///
/// The cache is written after slimming, so re-slimming it would treat the
/// `providers` key as a provider.
fn parse_cached_catalog(raw: &str) -> Result<String, String> {
    let parsed: serde_json::Value =
        serde_json::from_str(raw).map_err(|error| format!("Invalid catalog: {error}"))?;
    let providers = parsed
        .get("providers")
        .and_then(|value| value.as_object())
        .ok_or_else(|| "The cached catalog has no providers.".to_string())?;
    if providers.is_empty() {
        return Err("The cached catalog has no providers.".to_string());
    }
    Ok(raw.to_string())
}

/// Returns the cached catalog, or None when the cache is absent.
#[tauri::command(async)]
pub fn cached_model_catalog(app: AppHandle) -> Result<Option<String>, String> {
    let path = catalog_path(&app)?;
    if !path.exists() {
        return Ok(None);
    }
    let text = std::fs::read_to_string(&path)
        .map_err(|error| format!("Cannot read the cached catalog: {error}"))?;
    parse_cached_catalog(&text).map(Some)
}

/// Fetches models.dev, caches the slim catalog, and returns it.
#[tauri::command(async)]
pub fn refresh_model_catalog(app: AppHandle) -> Result<String, String> {
    let client = reqwest::blocking::Client::builder()
        .timeout(std::time::Duration::from_secs(10))
        .build()
        .map_err(|error| format!("Cannot create the HTTP client: {error}"))?;
    let raw = client
        .get(CATALOG_URL)
        .send()
        .and_then(|response| response.error_for_status())
        .and_then(|response| response.text())
        .map_err(|error| format!("The catalog fetch failed: {error}"))?;
    let slim = slim_catalog(&raw)?;
    let path = catalog_path(&app)?;
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|error| format!("Cannot create the cache directory: {error}"))?;
    }
    let temporary = path.with_extension("json.tmp");
    std::fs::write(&temporary, &slim)
        .map_err(|error| format!("Cannot write the catalog cache: {error}"))?;
    std::fs::rename(&temporary, &path)
        .map_err(|error| format!("Cannot replace the catalog cache: {error}"))?;
    Ok(slim)
}

#[cfg(test)]
mod tests {
    use super::{parse_cached_catalog, slim_catalog};

    #[test]
    fn slim_catalog_drops_unused_fields() {
        let raw = r#"{"openai":{"name":"OpenAI","doc":"d","api":"","npm":"@ai-sdk/openai","env":["OPENAI_API_KEY"],"models":{"gpt-5":{"name":"GPT-5","reasoning":true,"tool_call":true,"cost":{"input":1}}}}}"#;
        let slim: serde_json::Value = serde_json::from_str(&slim_catalog(raw).unwrap()).unwrap();
        assert!(slim["providers"]["openai"]["env"].is_null());
        assert_eq!(
            slim["providers"]["openai"]["models"]["gpt-5"]["name"],
            "GPT-5"
        );
        assert_eq!(slim["providers"]["openai"]["npm"], "@ai-sdk/openai");
    }

    #[test]
    fn cached_catalog_keeps_the_slim_shape() {
        let slim = r#"{"providers":{"openai":{"name":"OpenAI","models":{}}}}"#;
        let parsed: serde_json::Value =
            serde_json::from_str(&parse_cached_catalog(slim).unwrap()).unwrap();
        assert!(parsed["providers"]["openai"].is_object());
        assert!(parsed["providers"]["providers"].is_null());
    }

    #[test]
    fn slim_catalog_rejects_invalid_json() {
        assert!(slim_catalog("not json").is_err());
        assert!(slim_catalog(r#"{}"#).is_err());
    }
}
