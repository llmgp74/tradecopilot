"""Symmetric encryption for API keys stored on disk."""

import logging
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


class SecretBox:
    """Encrypts and decrypts stored secrets with a local Fernet key."""

    def __init__(self, key_path: Path) -> None:
        """Load the key file, creating it on first use.

        Args:
            key_path: File holding the Fernet key. Created with mode 0600.
        """
        self.key_path = key_path
        self._fernet = Fernet(_load_or_create_key(key_path))

    def encrypt(self, value: str) -> str:
        """Encrypt one secret.

        Args:
            value: Plaintext. An empty string stays empty.

        Returns:
            A Fernet token, or an empty string.
        """
        if not value:
            return ""
        return self._fernet.encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt(self, token: str) -> str:
        """Decrypt one secret.

        Args:
            token: Fernet token. An empty string stays empty.

        Returns:
            The plaintext, or an empty string when the token cannot be
            decrypted with the current key.
        """
        if not token:
            return ""
        try:
            return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")
        except InvalidToken:
            logger.warning("Stored secret cannot be decrypted; treating it as unset")
            return ""


def _load_or_create_key(path: Path) -> bytes:
    """Return a valid Fernet key, creating or replacing the file as needed."""
    key = _read_key(path)
    if key is not None:
        try:
            Fernet(key)
        except ValueError:
            logger.warning("Settings key is invalid; generating a new one")
        else:
            return key
    key = Fernet.generate_key()
    _write_key(path, key)
    return key


def _read_key(path: Path) -> bytes | None:
    try:
        return path.read_bytes().strip()
    except FileNotFoundError:
        return None


def _write_key(path: Path, key: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        os.chmod(path, 0o600)
        path.write_bytes(key)
        return
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(key)
