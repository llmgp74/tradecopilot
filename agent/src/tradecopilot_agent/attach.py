"""Copy attached files into the agent workspace.

The browser sends each attachment as a base64 data URL inside the chat
request. The server writes the bytes under ``uploads/<thread_id>/`` and hands
the model a workspace path, which its file and shell tools can open.
"""

import base64
import hashlib
import re
from pathlib import Path
from typing import Any

UIPart = dict[str, Any]

EXTENSION_MEDIA_TYPES: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".pdf": "application/pdf",
    ".csv": "text/csv",
    ".tsv": "text/tab-separated-values",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".json": "application/json",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

ACCEPTED_MEDIA_TYPES: frozenset[str] = frozenset(EXTENSION_MEDIA_TYPES.values())
IMAGE_MEDIA_TYPES: frozenset[str] = frozenset(
    {"image/png", "image/jpeg", "image/webp", "image/gif"}
)

MAX_FILE_BYTES: int = 10 * 1024 * 1024
"""Largest decoded attachment the server accepts."""

_THREAD_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,64}")


def attachment_media_type(part: UIPart) -> str | None:
    """Return the media type of an accepted file part.

    Webviews report an empty type for CSV, TSV, and Markdown files, so the
    filename extension decides when the reported type is missing or unknown.

    Args:
        part: One UI message part.

    Returns:
        An accepted media type, or ``None`` when the file type is not
        supported.
    """
    media_type = part.get("mediaType")
    if isinstance(media_type, str) and media_type in ACCEPTED_MEDIA_TYPES:
        return media_type
    filename = part.get("filename")
    if isinstance(filename, str):
        return EXTENSION_MEDIA_TYPES.get(Path(filename).suffix.lower())
    return None


def is_image_part(part: UIPart) -> bool:
    """Return whether the part is an image the model can see.

    Args:
        part: One UI message part.

    Returns:
        True for an accepted image type.
    """
    return attachment_media_type(part) in IMAGE_MEDIA_TYPES


def save_attachments(parts: list[UIPart], workspace: Path, thread_id: str) -> list[str]:
    """Copy the accepted file parts into the thread's upload directory.

    A file is written only when its target is missing, so re-sending the same
    history reuses the copy. Each accepted part produces one note line for the
    model; parts with an unsupported type are skipped.

    Args:
        parts: Parts of the user message that starts the turn.
        workspace: Workspace root.
        thread_id: Thread the files belong to.

    Returns:
        Note lines in part order.

    Raises:
        ValueError: When the thread id cannot be a directory name.
    """
    if _THREAD_ID_PATTERN.fullmatch(thread_id) is None:
        raise ValueError(f"Invalid thread id {thread_id!r}.")
    notes: list[str] = []
    for part in parts:
        if part.get("type") != "file":
            continue
        media_type = attachment_media_type(part)
        if media_type is None:
            continue
        name = _safe_name(part)
        virtual = f"/uploads/{thread_id}/{name}"
        url = part.get("url")
        body = _data_payload(url)
        if body is None:
            reason = "too large" if _payload_exceeds_limit(url) else "unavailable"
            notes.append(f"Attached file {reason}: {virtual}")
            continue
        digest = hashlib.sha1(str(url).encode()).hexdigest()[:8]
        target = workspace / "uploads" / thread_id / f"{digest}-{name}"
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(body)
        notes.append(
            f"Attached file: /uploads/{thread_id}/{digest}-{name} "
            f"({media_type}, {_human_size(len(body))})"
        )
    return notes


def _safe_name(part: UIPart) -> str:
    """Strip directory components from the reported filename.

    Args:
        part: One UI file part.

    Returns:
        A bare filename, or ``upload`` plus the extension when none is given.
    """
    filename = part.get("filename")
    extension = ""
    if isinstance(filename, str):
        extension = Path(filename).suffix
        name = Path(filename).name
        if name:
            return name
    return f"upload{extension}"


def _data_payload(url: Any) -> bytes | None:
    """Decode the payload of a base64 data URL.

    Args:
        url: File part URL.

    Returns:
        The file bytes, or ``None`` when the URL is not a readable data URL.
    """
    if not isinstance(url, str) or not url.startswith("data:"):
        return None
    header, separator, payload = url.partition(",")
    if separator == "" or ";base64" not in header:
        return None
    if len(payload) > MAX_FILE_BYTES * 4 // 3 + 4:
        return None
    try:
        return base64.b64decode(payload, validate=True)
    except ValueError:
        return None


def _payload_exceeds_limit(url: Any) -> bool:
    """Return whether a base64 data URL is longer than the accepted size.

    Args:
        url: File part URL.

    Returns:
        True for a data URL whose encoded payload is over the limit.
    """
    if not isinstance(url, str) or not url.startswith("data:"):
        return False
    header, separator, payload = url.partition(",")
    if separator == "" or ";base64" not in header:
        return False
    return len(payload) > MAX_FILE_BYTES * 4 // 3 + 4


def _human_size(size: int) -> str:
    """Format a byte count for the attachment note.

    Args:
        size: Number of bytes.

    Returns:
        A short size such as ``812 B`` or ``2.4 MB``.
    """
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"
