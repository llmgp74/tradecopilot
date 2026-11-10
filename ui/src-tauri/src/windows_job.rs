//! Windows job object that kills the agent tree when the app exits.

use std::io;
use std::os::windows::io::AsRawHandle;
use std::process::Child;
use std::ptr;

use windows_sys::Win32::Foundation::{CloseHandle, HANDLE};
use windows_sys::Win32::System::JobObjects::{
    AssignProcessToJobObject, CreateJobObjectW, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION, JobObjectExtendedLimitInformation,
    SetInformationJobObject,
};

/// A job with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`.
///
/// The handle is stored as `isize` so the type is `Send` and `Sync`; the raw
/// `HANDLE` pointer type is neither, which would make `AgentState` unusable
/// from Tauri managed state and worker threads.
pub struct WindowsJob(isize);

impl WindowsJob {
    /// Creates a job whose members die when the last handle closes.
    pub fn new() -> io::Result<Self> {
        unsafe {
            let handle = CreateJobObjectW(ptr::null(), ptr::null());
            if handle == 0 {
                return Err(io::Error::last_os_error());
            }
            let mut limits: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
            limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
            let applied = SetInformationJobObject(
                handle,
                JobObjectExtendedLimitInformation,
                &limits as *const _ as *const _,
                std::mem::size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
            );
            if applied == 0 {
                let error = io::Error::last_os_error();
                CloseHandle(handle);
                return Err(error);
            }
            Ok(Self(handle as isize))
        }
    }

    /// Adds a child process to the job.
    pub fn assign(&self, child: &Child) -> io::Result<()> {
        unsafe {
            if AssignProcessToJobObject(self.0 as HANDLE, child.as_raw_handle() as HANDLE) == 0 {
                return Err(io::Error::last_os_error());
            }
            Ok(())
        }
    }
}

impl Drop for WindowsJob {
    fn drop(&mut self) {
        unsafe {
            CloseHandle(self.0 as HANDLE);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::process::{Command, Stdio};

    #[test]
    fn assigns_a_child_to_the_job() {
        let job = WindowsJob::new().unwrap();
        let mut child = Command::new("cmd")
            .args(["/c", "ping", "-n", "2", "127.0.0.1"])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .unwrap();
        job.assign(&child).unwrap();
        let _ = child.kill();
        let _ = child.wait();
    }
}
