"""Attachment copying into the workspace."""

import base64
from pathlib import Path

import pytest
from tradecopilot_agent.attach import attachment_media_type, save_attachments


def data_url(media_type: str, body: bytes) -> str:
    """Build a base64 data URL for one test file."""
    encoded = base64.b64encode(body).decode()
    return f"data:{media_type};base64,{encoded}"


def csv_part(name: str = "pnl.csv", media_type: str = "text/csv") -> dict[str, object]:
    """Build a UI file part for a small CSV."""
    return {
        "type": "file",
        "filename": name,
        "mediaType": media_type,
        "url": data_url(media_type or "text/csv", b"a,b\n1,2\n"),
    }


def test_empty_media_type_is_accepted_by_extension() -> None:
    """A webview often reports no type for a CSV, so the name decides."""
    assert attachment_media_type(csv_part(media_type="")) == "text/csv"


def test_saves_inside_the_thread_upload_directory(tmp_path: Path) -> None:
    """The copied file keeps its name and lands under the thread folder."""
    notes = save_attachments([csv_part()], tmp_path, "thread-1")

    files = list((tmp_path / "uploads" / "thread-1").iterdir())
    assert len(files) == 1
    assert files[0].name.endswith("-pnl.csv")
    assert files[0].read_bytes() == b"a,b\n1,2\n"
    assert notes[0].startswith("Attached file: /uploads/thread-1/")


def test_repeat_save_reuses_the_same_file(tmp_path: Path) -> None:
    """Re-sending the same history does not duplicate the copy."""
    save_attachments([csv_part()], tmp_path, "thread-1")
    save_attachments([csv_part()], tmp_path, "thread-1")

    assert len(list((tmp_path / "uploads" / "thread-1").iterdir())) == 1


def test_path_segments_are_stripped(tmp_path: Path) -> None:
    """A crafted filename cannot escape the upload directory."""
    save_attachments([csv_part(name="../../escape.csv")], tmp_path, "thread-1")

    assert not (tmp_path.parent / "escape.csv").exists()
    assert all(
        path.parent.name == "thread-1"
        for path in (tmp_path / "uploads" / "thread-1").iterdir()
    )


def test_unreadable_url_is_reported(tmp_path: Path) -> None:
    """A blob URL cannot be fetched by the server, so the note says so."""
    part = {
        "type": "file",
        "filename": "x.pdf",
        "mediaType": "application/pdf",
        "url": "blob:abc",
    }

    notes = save_attachments([part], tmp_path, "thread-1")

    assert notes == ["Attached file unavailable: /uploads/thread-1/x.pdf"]


def test_image_is_saved_too(tmp_path: Path) -> None:
    """Images are copied like any other file and keep their media type."""
    part = {
        "type": "file",
        "filename": "shot.png",
        "mediaType": "image/png",
        "url": data_url("image/png", b"png"),
    }

    notes = save_attachments([part], tmp_path, "thread-1")

    assert list((tmp_path / "uploads" / "thread-1").glob("*-shot.png"))
    assert "image/png" in notes[0]


def test_unaccepted_type_is_skipped(tmp_path: Path) -> None:
    """A file type outside the allowlist leaves no note and no copy."""
    part = {
        "type": "file",
        "filename": "archive.zip",
        "mediaType": "application/zip",
        "url": data_url("application/zip", b"zip"),
    }

    assert save_attachments([part], tmp_path, "thread-1") == []
    assert not (tmp_path / "uploads").exists()


def test_thread_id_cannot_escape_the_workspace(tmp_path: Path) -> None:
    """A crafted thread id is refused before any path is built."""
    with pytest.raises(ValueError, match="thread id"):
        save_attachments([csv_part()], tmp_path, "../escape")
    assert not (tmp_path.parent / "escape").exists()


def test_oversized_payload_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A payload above the server limit is refused, not decoded."""
    monkeypatch.setattr("tradecopilot_agent.attach.MAX_FILE_BYTES", 4)

    notes = save_attachments([csv_part()], tmp_path, "thread-1")

    assert notes == ["Attached file too large: /uploads/thread-1/pnl.csv"]
    assert not (tmp_path / "uploads").exists()
