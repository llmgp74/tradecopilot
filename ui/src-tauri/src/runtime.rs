//! Managed Python runtime: status, paths and provisioning.

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    #[test]
    fn missing_marker_reports_missing() {
        let dir = tempfile::tempdir().unwrap();
        assert_eq!(status(dir.path(), "0.1.0"), Status::Missing);
    }

    #[test]
    fn marker_without_interpreter_reports_broken() {
        let dir = tempfile::tempdir().unwrap();
        fs::write(
            marker_path(dir.path()),
            r#"{"version":"0.1.0","python":"3.13"}"#,
        )
        .unwrap();
        assert_eq!(status(dir.path(), "0.1.0"), Status::Broken);
    }

    #[test]
    fn sha256_matches_a_known_vector() {
        assert_eq!(
            sha256_hex(b"abc"),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        );
    }

    #[test]
    fn uv_release_is_defined_for_v1_targets() {
        if cfg!(any(
            all(target_os = "macos", target_arch = "aarch64"),
            all(target_os = "macos", target_arch = "x86_64"),
            all(target_os = "windows", target_arch = "x86_64")
        )) {
            assert!(uv_release().is_some());
        }
    }
}
