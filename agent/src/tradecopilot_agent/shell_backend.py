"""Local shell backend with a small fixed deny list.

Commands run on the host with the user's permissions, so the approval policy
is the real control. This module is a backstop: it refuses obviously
destructive commands and obvious attempts to read credential files, even
when the tool is set to auto. Text matching over a command string can be
evaded, and that limit is deliberate.
"""

import os
import re
import sys
from pathlib import Path

from deepagents.backends.local_shell import LocalShellBackend
from deepagents.backends.protocol import ExecuteResponse

DENIED_COMMANDS: tuple[str, ...] = (
    "sudo",
    "shutdown",
    "reboot",
    "mkfs",
    "diskutil erase",
    "dd of=/dev/",
    "rm -rf /",
    "rm -rf ~",
    "| sh",
    "|sh",
    "| bash",
    "|bash",
)

DENIED_PATH_FRAGMENTS: tuple[str, ...] = (
    ".ssh",
    ".gnupg",
    ".aws",
    ".kube",
    ".azure",
    ".docker/config.json",
    ".config/gcloud",
    ".terraform.d",
    ".npmrc",
    ".pypirc",
    ".netrc",
    ".git-credentials",
    ".vault-token",
    ".password-store",
    ".gem/credentials",
    ".config/op",
    ".local/share/op",
    ".cargo/credentials.toml",
    ".config/gh/hosts.yml",
    ".cache/huggingface/token",
    ".claude/.credentials.json",
    ".longbridge",
    ".zshrc",
    ".zprofile",
    ".zshenv",
    ".zlogin",
    ".zlogout",
    ".bashrc",
    ".bash_profile",
    ".bash_login",
    ".bash_logout",
    ".profile",
    ".cshrc",
    ".tcshrc",
    ".config/fish",
)

DENIED_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(^|[\s/'\"])\.env(\.|$|[\s/'\";)])"),
    re.compile(r"\.pem([\s'\"`;)]|$)"),
    re.compile(r"\.key([\s'\"`;)]|$)"),
)


def denial_reason(command: str) -> str | None:
    """Return why a command is refused, or ``None`` when it may run.

    Args:
        command: Shell command the model asked to run.

    Returns:
        A short reason naming the matched rule.
    """
    for token in DENIED_COMMANDS:
        if token in command:
            return f"the command contains {token!r}"
    for fragment in DENIED_PATH_FRAGMENTS:
        if fragment in command:
            return f"the command names {fragment!r}"
    for pattern in DENIED_PATTERNS:
        match = pattern.search(command)
        if match is not None:
            return f"the command names {match.group(0).strip()!r}"
    return None


class WorkspaceShellBackend(LocalShellBackend):
    """Local shell backend that refuses commands on the deny list."""

    def execute(
        self,
        command: str,
        *,
        timeout: int | None = None,
    ) -> ExecuteResponse:
        """Refuse a denied command, otherwise run it in the workspace.

        Args:
            command: Shell command to run.
            timeout: Optional per-command timeout in seconds.

        Returns:
            The command result, or a failed result naming the denial.
        """
        reason = denial_reason(command)
        if reason is not None:
            return ExecuteResponse(
                output=f"Blocked: {reason}.",
                exit_code=1,
                truncated=False,
            )
        return super().execute(command, timeout=timeout)


def build_shell_backend(workspace: Path) -> WorkspaceShellBackend:
    """Build the backend rooted at the workspace.

    The app's interpreter directory is put first on ``PATH`` so ``python``
    resolves to the same environment that runs the server, including the
    parsing libraries installed for it.

    Args:
        workspace: Workspace root, used as the shell working directory.

    Returns:
        The configured backend.
    """
    path = f"{Path(sys.executable).parent}{os.pathsep}{os.environ.get('PATH', '')}"
    return WorkspaceShellBackend(
        root_dir=workspace,
        inherit_env=True,
        timeout=120,
        env={"PATH": path},
    )
