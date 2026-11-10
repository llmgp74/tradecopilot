//! Supervised agent child process.

use std::fs::OpenOptions;
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::thread::{self, JoinHandle};
use std::time::Duration;

use serde::Serialize;
use tauri::{AppHandle, Emitter, Manager};

use crate::runtime;

/// State shared by the shell and the agent reader threads.
#[derive(Default, Clone)]
pub struct AgentState {
    /// Running agent process, if any.
    pub child: Arc<Mutex<Option<Child>>>,
    /// Agent origin, set when the port line arrives.
    pub base: Arc<Mutex<Option<String>>>,
    /// Setup worker, so concurrent bootstrap calls do not install twice.
    pub setup: Arc<Mutex<Option<JoinHandle<()>>>>,
    /// Currently running setup command, killed on exit.
    pub uv_child: Arc<Mutex<Option<Child>>>,
    /// Set once the startup timeout has fired.
    pub timed_out: Arc<AtomicBool>,
    /// Set when the shell stops the agent on purpose.
    pub stopping: Arc<AtomicBool>,
    /// Job object that kills the agent tree when the app exits.
    #[cfg(windows)]
    pub job: Arc<Mutex<Option<crate::windows_job::WindowsJob>>>,
}

#[derive(Clone, Serialize)]
struct ReadyPayload {
    base: String,
}

#[derive(Clone, Serialize)]
struct FailedPayload {
    message: String,
    log_path: String,
}

/// Path of the shared agent log.
pub fn log_path(app: &AppHandle) -> PathBuf {
    app.path()
        .app_log_dir()
        .unwrap_or_else(|_| std::env::temp_dir())
        .join("agent.log")
}

/// Extracts the port from a line the agent printed.
pub fn find_listening_port(text: &str) -> Option<u16> {
    for line in text.lines() {
        let Ok(value) = serde_json::from_str::<serde_json::Value>(line.trim()) else {
            continue;
        };
        if value.get("event").and_then(|item| item.as_str()) != Some("listening") {
            continue;
        }
        let Some(port) = value.get("port").and_then(|item| item.as_u64()) else {
            continue;
        };
        if (1..=65535).contains(&port) {
            return Some(port as u16);
        }
    }
    None
}

/// Environment for the agent process.
pub fn agent_env(_runtime: &Path, resources: &Path) -> Vec<(String, String)> {
    vec![
        (
            "PYTHONPATH".to_string(),
            resources
                .join("agent")
                .join("src")
                .to_string_lossy()
                .to_string(),
        ),
        ("PYTHONUNBUFFERED".to_string(), "1".to_string()),
    ]
}

/// Starts the agent when it is not already running.
pub fn spawn(
    app: &AppHandle,
    state: &AgentState,
    runtime: &Path,
    resources: &Path,
) -> Result<(), String> {
    let mut guard = state
        .child
        .lock()
        .map_err(|_| "Agent state is poisoned.".to_string())?;
    if let Some(child) = guard.as_mut()
        && child
            .try_wait()
            .map_err(|error| format!("Cannot check the agent: {error}"))?
            .is_none()
    {
        return Ok(());
    }

    let mut command = Command::new(runtime::venv_python(runtime));
    command.args(["-m", "tradecopilot_agent.desktop"]);
    for (key, value) in agent_env(runtime, resources) {
        command.env(key, value);
    }
    command.stdout(Stdio::piped()).stderr(Stdio::piped());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;

        command.creation_flags(0x0800_0000);
    }

    let mut child = command
        .spawn()
        .map_err(|error| format!("Could not start the agent: {error}"))?;
    let stdout = child.stdout.take();
    let stderr = child.stderr.take();
    #[cfg(windows)]
    if let Err(message) = assign_to_job(state, &child) {
        let _ = child.kill();
        let _ = child.wait();
        return Err(message);
    }
    *guard = Some(child);
    drop(guard);

    state.timed_out.store(false, Ordering::SeqCst);
    state.stopping.store(false, Ordering::SeqCst);
    if let Ok(mut slot) = state.base.lock() {
        slot.take();
    }

    let log = log_path(app);
    let recent = Arc::new(Mutex::new(Vec::<String>::new()));

    if let Some(stdout) = stdout {
        let app = app.clone();
        let base_slot = state.base.clone();
        let log = log.clone();
        thread::spawn(move || {
            let reader = BufReader::new(stdout);
            for line in reader.lines() {
                let Ok(line) = line else {
                    break;
                };
                append_line(&log, &line);
                if let Some(port) = find_listening_port(&line) {
                    let base = format!("http://127.0.0.1:{port}");
                    if let Ok(mut slot) = base_slot.lock() {
                        *slot = Some(base.clone());
                    }
                    let _ = app.emit("agent_ready", ReadyPayload { base });
                }
            }
        });
    }

    if let Some(stderr) = stderr {
        let log = log.clone();
        let recent = recent.clone();
        thread::spawn(move || {
            let reader = BufReader::new(stderr);
            for line in reader.lines() {
                let Ok(line) = line else {
                    break;
                };
                append_line(&log, &line);
                if let Ok(mut lines) = recent.lock() {
                    lines.push(line);
                    if lines.len() > 20 {
                        lines.remove(0);
                    }
                }
            }
        });
    }

    {
        let app = app.clone();
        let base_slot = state.base.clone();
        let timed_out = state.timed_out.clone();
        let log = log.clone();
        thread::spawn(move || {
            thread::sleep(Duration::from_secs(20));
            let ready = base_slot.lock().map(|slot| slot.is_some()).unwrap_or(true);
            if !ready && !timed_out.swap(true, Ordering::SeqCst) {
                let _ = app.emit(
                    "agent_failed",
                    FailedPayload {
                        message: "The agent did not report a port.".to_string(),
                        log_path: log.display().to_string(),
                    },
                );
            }
        });
    }

    {
        let app = app.clone();
        let child_slot = state.child.clone();
        let base_slot = state.base.clone();
        let stopped = state.stopping.clone();
        let recent = recent.clone();
        let log = log.clone();
        thread::spawn(move || {
            loop {
                thread::sleep(Duration::from_millis(500));
                let mut guard = match child_slot.lock() {
                    Ok(guard) => guard,
                    Err(_) => return,
                };
                let Some(child) = guard.as_mut() else {
                    return;
                };
                match child.try_wait() {
                    Ok(Some(status)) => {
                        *guard = None;
                        let was_ready = base_slot
                            .lock()
                            .map(|mut slot| slot.take().is_some())
                            .unwrap_or(false);
                        if stopped.swap(false, Ordering::SeqCst) {
                            return;
                        }
                        let tail = recent
                            .lock()
                            .map(|lines| lines.join("\n"))
                            .unwrap_or_default();
                        let message = if was_ready {
                            "The agent stopped unexpectedly.".to_string()
                        } else {
                            format!("The agent exited with {status}.")
                        };
                        let _ = app.emit(
                            "agent_failed",
                            FailedPayload {
                                message: format!("{message} {tail}"),
                                log_path: log.display().to_string(),
                            },
                        );
                        return;
                    }
                    Ok(None) => {}
                    Err(_) => return,
                }
            }
        });
    }

    Ok(())
}

/// Stops the agent and any running setup command.
pub fn stop(state: &AgentState) {
    state.stopping.store(true, Ordering::SeqCst);
    kill_tracked(&state.child);
    kill_tracked(&state.uv_child);
    if let Ok(mut slot) = state.base.lock() {
        slot.take();
    }
    state.timed_out.store(true, Ordering::SeqCst);
}

/// Kills and waits for a tracked child, clearing its slot.
fn kill_tracked(slot: &Arc<Mutex<Option<Child>>>) {
    if let Ok(mut guard) = slot.lock()
        && let Some(mut child) = guard.take()
    {
        let _ = child.kill();
        let _ = child.wait();
    }
}

/// Creates the job object on first use and assigns the child to it.
#[cfg(windows)]
fn assign_to_job(state: &AgentState, child: &Child) -> Result<(), String> {
    let mut job = state
        .job
        .lock()
        .map_err(|_| "Agent state is poisoned.".to_string())?;
    if job.is_none() {
        let created = crate::windows_job::WindowsJob::new()
            .map_err(|error| format!("Cannot create the job object: {error}"))?;
        *job = Some(created);
    }
    if let Some(job) = job.as_ref() {
        job.assign(child)
            .map_err(|error| format!("Cannot assign the agent to the job object: {error}"))?;
    }
    Ok(())
}

/// Appends one line to the agent log, creating its directory when needed.
fn append_line(path: &Path, line: &str) {
    if let Some(parent) = path.parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    if let Ok(mut file) = OpenOptions::new().create(true).append(true).open(path) {
        let _ = writeln!(file, "{line}");
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn finds_the_port_after_other_output() {
        let text = "warning: noisy\n{\"event\": \"listening\", \"port\": 51234}\n";
        assert_eq!(find_listening_port(text), Some(51234));
    }

    #[test]
    fn ignores_lines_that_are_not_the_event() {
        assert_eq!(find_listening_port("{\"port\": 1}\nready\n"), None);
    }

    #[test]
    fn ignores_a_split_json_line() {
        assert_eq!(
            find_listening_port("{\"event\": \"listening\", \"port\":"),
            None
        );
    }

    #[cfg(unix)]
    #[test]
    fn kill_tracked_terminates_and_clears_the_child() {
        let slot: Arc<Mutex<Option<Child>>> = Arc::new(Mutex::new(None));
        let child = Command::new("sleep").arg("30").spawn().unwrap();
        *slot.lock().unwrap() = Some(child);
        kill_tracked(&slot);
        assert!(slot.lock().unwrap().is_none());
    }

    #[test]
    fn env_overrides_pythonpath() {
        let env = agent_env(Path::new("/r"), Path::new("/res"));
        let expected = Path::new("/res")
            .join("agent")
            .join("src")
            .to_string_lossy()
            .to_string();
        assert!(env.contains(&("PYTHONPATH".to_string(), expected)));
    }
}
