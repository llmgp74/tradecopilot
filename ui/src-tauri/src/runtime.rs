//! Managed Python runtime: status, paths and provisioning.

use std::fs;
use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex, mpsc};
use std::thread;
use std::time::Duration;

use serde::Serialize;
use sha2::{Digest, Sha256};

/// uv release bundled by the first-launch bootstrap.
const UV_VERSION: &str = "0.13.7";

#[cfg(all(target_os = "macos", target_arch = "aarch64"))]
const UV_ARCHIVE: &str = "uv-aarch64-apple-darwin.tar.gz";
#[cfg(all(target_os = "macos", target_arch = "aarch64"))]
const UV_SHA256: &str = "81b811b57e4624df7ed3aac148e0359100d9962f3d9dce00aec533dc2e086731";

#[cfg(all(target_os = "macos", target_arch = "x86_64"))]
const UV_ARCHIVE: &str = "uv-x86_64-apple-darwin.tar.gz";
#[cfg(all(target_os = "macos", target_arch = "x86_64"))]
const UV_SHA256: &str = "20c47e4c1f630b8abaff8c291fa9b9aa300fef92c4fbff95adf198b55287cda7";

#[cfg(all(target_os = "windows", target_arch = "x86_64"))]
const UV_ARCHIVE: &str = "uv-x86_64-pc-windows-msvc.zip";
#[cfg(all(target_os = "windows", target_arch = "x86_64"))]
const UV_SHA256: &str = "0cdc5b38fe5a8168ed6a25814f5ba43c21d313dd3187314fccb37b7cec46e021";

#[cfg(all(target_os = "windows", target_arch = "aarch64"))]
const UV_ARCHIVE: &str = "uv-aarch64-pc-windows-msvc.zip";
#[cfg(all(target_os = "windows", target_arch = "aarch64"))]
const UV_SHA256: &str = "505d9e65e7692bac3ddf98c66754aa26c5050c409c184af30a881a0a72cc85e3";

/// State of the managed runtime directory.
#[derive(Debug, PartialEq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Status {
    /// The marker and the interpreter are present and match the app version.
    Installed,
    /// No marker has been written.
    Missing,
    /// A marker exists but the runtime is incomplete or from another version.
    Broken,
}

/// A pinned uv archive for one platform.
pub struct UvRelease {
    /// Release version, without the leading `v`.
    pub version: &'static str,
    /// Archive file name.
    pub archive: &'static str,
    /// Lowercase hex SHA-256 of the archive.
    pub sha256: &'static str,
}

/// Path of the marker written when setup completes.
pub fn marker_path(runtime: &Path) -> PathBuf {
    runtime.join("installed.json")
}

/// Path of the interpreter inside the managed virtual environment.
pub fn venv_python(runtime: &Path) -> PathBuf {
    if cfg!(windows) {
        runtime.join("venv").join("Scripts").join("python.exe")
    } else {
        runtime.join("venv").join("bin").join("python")
    }
}

/// Path of the downloaded uv executable.
pub fn uv_binary(runtime: &Path) -> PathBuf {
    if cfg!(windows) {
        runtime.join("bin").join("uv.exe")
    } else {
        runtime.join("bin").join("uv")
    }
}

/// Stops Windows from opening a console window for a child process.
pub fn hide_console(command: &mut Command) {
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;

        command.creation_flags(0x0800_0000);
    }
    #[cfg(not(windows))]
    let _ = command;
}

/// True when the venv was built from the managed Python under `python/`.
fn venv_is_managed(runtime: &Path) -> bool {
    let config = fs::read_to_string(runtime.join("venv").join("pyvenv.cfg")).unwrap_or_default();
    let managed = runtime.join("python");
    config.lines().any(|line| {
        line.split_once('=').is_some_and(|(key, value)| {
            key.trim() == "home" && Path::new(value.trim()).starts_with(&managed)
        })
    })
}

/// Classifies the runtime directory. A different app version or requirement
/// digest marks the runtime as broken so setup reinstalls the dependencies.
pub fn status(runtime: &Path, app_version: &str, requirements: &str) -> Status {
    let Ok(text) = fs::read_to_string(marker_path(runtime)) else {
        return Status::Missing;
    };
    let Ok(marker) = serde_json::from_str::<serde_json::Value>(&text) else {
        return Status::Broken;
    };
    if marker.get("version").and_then(|value| value.as_str()) != Some(app_version) {
        return Status::Broken;
    }
    if marker.get("requirements").and_then(|value| value.as_str()) != Some(requirements) {
        return Status::Broken;
    }
    if !venv_python(runtime).is_file() {
        return Status::Broken;
    }
    if !venv_is_managed(runtime) {
        return Status::Broken;
    }
    Status::Installed
}

/// Builds the download URL for one pinned release.
pub fn archive_url(release: &UvRelease) -> String {
    format!(
        "https://github.com/astral-sh/uv/releases/download/{}/{}",
        release.version, release.archive
    )
}

/// Hashes the exported requirements so a dependency change reinstalls them.
pub fn requirements_digest(resources: &Path) -> String {
    match fs::read(resources.join("requirements.lock.txt")) {
        Ok(bytes) => sha256_hex(&bytes),
        Err(_) => String::new(),
    }
}

/// Writes the marker that marks a completed setup.
pub fn write_marker(runtime: &Path, app_version: &str, requirements: &str) -> Result<(), String> {
    fs::create_dir_all(runtime)
        .map_err(|error| format!("Cannot create {}: {error}", runtime.display()))?;
    let body = serde_json::json!({
        "version": app_version,
        "python": "3.13",
        "requirements": requirements,
    });
    fs::write(marker_path(runtime), body.to_string())
        .map_err(|error| format!("Cannot write the runtime marker: {error}"))
}

/// Downloads the pinned uv archive, verifies it and installs the executable.
pub fn download_and_install_uv(runtime: &Path) -> Result<(), String> {
    let release = uv_release().ok_or_else(|| "This platform is not supported.".to_string())?;
    let binary = uv_binary(runtime);
    if binary.is_file() {
        return Ok(());
    }
    let bin_dir = binary
        .parent()
        .ok_or_else(|| "Invalid uv path.".to_string())?;
    fs::create_dir_all(bin_dir).map_err(|error| format!("Cannot create {bin_dir:?}: {error}"))?;

    let client = reqwest::blocking::Client::builder()
        .connect_timeout(Duration::from_secs(30))
        .timeout(Duration::from_secs(600))
        .build()
        .map_err(|error| format!("Could not build the HTTP client: {error}"))?;
    let response = client
        .get(archive_url(&release))
        .send()
        .map_err(|error| format!("Could not download uv: {error}"))?;
    if !response.status().is_success() {
        return Err(format!("Downloading uv failed with {}.", response.status()));
    }
    let bytes = response
        .bytes()
        .map_err(|error| format!("Could not read the uv download: {error}"))?;
    let actual = sha256_hex(&bytes);
    if actual != release.sha256 {
        return Err(format!(
            "uv checksum mismatch: expected {}, got {actual}.",
            release.sha256
        ));
    }

    let archive = runtime.join(release.archive);
    fs::write(&archive, &bytes)
        .map_err(|error| format!("Cannot write {}: {error}", archive.display()))?;
    let extract = runtime.join("uv-extract");
    if extract.is_dir() {
        fs::remove_dir_all(&extract)
            .map_err(|error| format!("Cannot clear {}: {error}", extract.display()))?;
    }
    fs::create_dir_all(&extract)
        .map_err(|error| format!("Cannot create {}: {error}", extract.display()))?;

    let mut command = Command::new("tar");
    command.arg("-xf").arg(&archive).arg("-C").arg(&extract);
    hide_console(&mut command);
    let status = command
        .status()
        .map_err(|error| format!("Could not start tar: {error}"))?;
    if !status.success() {
        return Err("Could not extract the uv archive.".to_string());
    }

    // The macOS tarball nests the binary in a release directory; the Windows
    // zip stores it at the archive root.
    let extracted = fs::read_dir(&extract)
        .map_err(|error| format!("Cannot read {}: {error}", extract.display()))?
        .filter_map(Result::ok)
        .map(|entry| entry.path())
        .find(|path| path.is_dir())
        .unwrap_or_else(|| extract.clone());
    let source = extracted.join(if cfg!(windows) { "uv.exe" } else { "uv" });
    fs::copy(&source, &binary).map_err(|error| {
        format!(
            "Cannot copy {} to {}: {error}",
            source.display(),
            binary.display()
        )
    })?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;

        let mut permissions = fs::metadata(&binary)
            .map_err(|error| format!("Cannot read {}: {error}", binary.display()))?
            .permissions();
        permissions.set_mode(0o755);
        fs::set_permissions(&binary, permissions)
            .map_err(|error| format!("Cannot make {} executable: {error}", binary.display()))?;
    }

    let _ = fs::remove_file(&archive);
    let _ = fs::remove_dir_all(&extract);
    Ok(())
}

/// Runs the bootstrap steps and reports each output line.
pub fn install_steps(
    runtime: &Path,
    resources: &Path,
    emit: &mut dyn FnMut(&str, &str),
    uv_child: &Arc<Mutex<Option<Child>>>,
) -> Result<(), String> {
    if !uv_binary(runtime).is_file() {
        emit("uv", "Downloading uv");
        download_and_install_uv(runtime)?;
        emit("uv", "uv is ready");
    }

    run_uv(
        runtime,
        "python",
        &["python", "install", "3.13"],
        emit,
        uv_child,
    )?;

    let venv = runtime.join("venv");
    // A venv built from a system interpreter such as Conda defeats the
    // managed runtime, so rebuild it with the downloaded Python.
    if venv.is_dir() && !venv_is_managed(runtime) {
        fs::remove_dir_all(&venv)
            .map_err(|error| format!("Cannot clear {}: {error}", venv.display()))?;
    }
    let venv_text = venv.to_string_lossy().to_string();
    // --allow-existing lets Retry repair a venv left by a failed setup.
    run_uv(
        runtime,
        "venv",
        &["venv", &venv_text, "--python", "3.13", "--allow-existing"],
        emit,
        uv_child,
    )?;

    let python = venv_python(runtime);
    let python_text = python.to_string_lossy().to_string();
    let requirements = resources.join("requirements.lock.txt");
    let requirements_text = requirements.to_string_lossy().to_string();
    run_uv(
        runtime,
        "deps",
        &[
            "pip",
            "install",
            "--python",
            &python_text,
            "-r",
            &requirements_text,
        ],
        emit,
        uv_child,
    )?;

    write_marker(
        runtime,
        env!("CARGO_PKG_VERSION"),
        &requirements_digest(resources),
    )
}

/// Runs one uv command and forwards both output streams line by line.
fn run_uv(
    runtime: &Path,
    step: &str,
    args: &[&str],
    emit: &mut dyn FnMut(&str, &str),
    uv_child: &Arc<Mutex<Option<Child>>>,
) -> Result<(), String> {
    let mut command = Command::new(uv_binary(runtime));
    command
        .args(args)
        .env("UV_CACHE_DIR", runtime.join("cache"))
        .env("UV_PYTHON_INSTALL_DIR", runtime.join("python"))
        // Without this uv prefers an interpreter already on PATH, such as a
        // Conda Python, over the managed download.
        .env("UV_MANAGED_PYTHON", "1")
        .env("UV_NO_CONFIG", "1")
        .env_remove("PYTHONPATH")
        .env_remove("VIRTUAL_ENV")
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    hide_console(&mut command);
    let mut child = command
        .spawn()
        .map_err(|error| format!("Could not start uv: {error}"))?;

    let stdout = child.stdout.take();
    let stderr = child.stderr.take();

    // The job or a crash-closed handle reaps this child with the app.
    #[cfg(windows)]
    let _job = crate::windows_job::WindowsJob::new().ok().inspect(|job| {
        let _ = job.assign(&child);
    });

    if let Ok(mut slot) = uv_child.lock() {
        *slot = Some(child);
    }

    let (sender, receiver) = mpsc::channel::<String>();
    let mut readers = Vec::new();
    if let Some(stdout) = stdout {
        let sender = sender.clone();
        readers.push(thread::spawn(move || forward(stdout, sender)));
    }
    if let Some(stderr) = stderr {
        let sender = sender.clone();
        readers.push(thread::spawn(move || forward(stderr, sender)));
    }
    drop(sender);

    let mut lines = Vec::new();
    for line in receiver {
        emit(step, &line);
        lines.push(line);
    }
    for reader in readers {
        let _ = reader.join();
    }

    let mut child = uv_child
        .lock()
        .ok()
        .and_then(|mut slot| slot.take())
        .ok_or_else(|| format!("{step} was stopped."))?;
    let status = child
        .wait()
        .map_err(|error| format!("uv did not finish: {error}"))?;
    if !status.success() {
        let tail = lines
            .iter()
            .rev()
            .take(20)
            .rev()
            .cloned()
            .collect::<Vec<_>>()
            .join("\n");
        return Err(format!("{step} failed:\n{tail}"));
    }
    Ok(())
}

/// Reads a child stream and forwards complete lines.
fn forward(stream: impl std::io::Read, sender: mpsc::Sender<String>) {
    let reader = BufReader::new(stream);
    for line in reader.lines() {
        let Ok(line) = line else {
            break;
        };
        if sender.send(line).is_err() {
            break;
        }
    }
}

/// Hashes bytes with SHA-256.
pub fn sha256_hex(bytes: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(bytes);
    hasher
        .finalize()
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

/// Returns the pinned uv release for the current platform.
#[cfg(any(
    all(target_os = "macos", target_arch = "aarch64"),
    all(target_os = "macos", target_arch = "x86_64"),
    all(target_os = "windows", target_arch = "x86_64"),
    all(target_os = "windows", target_arch = "aarch64")
))]
pub fn uv_release() -> Option<UvRelease> {
    Some(UvRelease {
        version: UV_VERSION,
        archive: UV_ARCHIVE,
        sha256: UV_SHA256,
    })
}

/// Returns the pinned uv release for the current platform.
#[cfg(not(any(
    all(target_os = "macos", target_arch = "aarch64"),
    all(target_os = "macos", target_arch = "x86_64"),
    all(target_os = "windows", target_arch = "x86_64"),
    all(target_os = "windows", target_arch = "aarch64")
)))]
pub fn uv_release() -> Option<UvRelease> {
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn missing_marker_reports_missing() {
        let dir = tempfile::tempdir().unwrap();
        assert_eq!(status(dir.path(), "0.1.0", ""), Status::Missing);
    }

    #[test]
    fn marker_without_interpreter_reports_broken() {
        let dir = tempfile::tempdir().unwrap();
        fs::write(
            marker_path(dir.path()),
            r#"{"version":"0.1.0","python":"3.13","requirements":""}"#,
        )
        .unwrap();
        assert_eq!(status(dir.path(), "0.1.0", ""), Status::Broken);
    }

    #[test]
    fn sha256_matches_a_known_vector() {
        assert_eq!(
            sha256_hex(b"abc"),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        );
    }

    #[test]
    fn venv_is_managed_tracks_the_python_home() {
        let dir = tempfile::tempdir().unwrap();
        assert!(!venv_is_managed(dir.path()));

        let venv = dir.path().join("venv");
        fs::create_dir_all(&venv).unwrap();
        fs::write(venv.join("pyvenv.cfg"), "home = /opt/anaconda3/bin\n").unwrap();
        assert!(!venv_is_managed(dir.path()));

        let home = dir.path().join("python").join("cpython-3.13").join("bin");
        fs::write(
            venv.join("pyvenv.cfg"),
            format!("home = {}\n", home.display()),
        )
        .unwrap();
        assert!(venv_is_managed(dir.path()));
    }

    #[test]
    fn marker_is_written_with_the_app_version() {
        let dir = tempfile::tempdir().unwrap();
        let python = venv_python(dir.path());
        fs::create_dir_all(python.parent().unwrap()).unwrap();
        fs::write(&python, b"").unwrap();
        let home = dir.path().join("python").join("cpython-3.13").join("bin");
        fs::write(
            dir.path().join("venv").join("pyvenv.cfg"),
            format!("home = {}\n", home.display()),
        )
        .unwrap();
        write_marker(dir.path(), "0.1.0", "deps-a").unwrap();
        assert_eq!(status(dir.path(), "0.1.0", "deps-a"), Status::Installed);
        assert_eq!(status(dir.path(), "0.2.0", "deps-a"), Status::Broken);
        assert_eq!(status(dir.path(), "0.1.0", "deps-b"), Status::Broken);
    }

    #[test]
    fn download_archive_url_is_built_from_the_pin() {
        if let Some(release) = uv_release() {
            assert_eq!(
                archive_url(&release),
                format!(
                    "https://github.com/astral-sh/uv/releases/download/{}/{}",
                    release.version, release.archive
                )
            );
        }
    }

    #[test]
    fn uv_release_is_defined_for_v1_targets() {
        if cfg!(any(
            all(target_os = "macos", target_arch = "aarch64"),
            all(target_os = "macos", target_arch = "x86_64"),
            all(target_os = "windows", target_arch = "x86_64"),
            all(target_os = "windows", target_arch = "aarch64")
        )) {
            assert!(uv_release().is_some());
        }
    }
}
