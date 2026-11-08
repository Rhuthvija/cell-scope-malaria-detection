"""
crypto_util.py
Field-level encryption at rest for sensitive patient data (phone numbers and
blood-smear / Grad-CAM images) stored in SQLite.

Uses Fernet from the `cryptography` package: AES-128-CBC with an HMAC-SHA256
integrity check, so stored values can be neither read nor tampered with
without the key.

Setup:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    -> set the printed value as the CELLSCOPE_ENCRYPTION_KEY environment variable
       (on Render: Environment -> Add Environment Variable). Never commit it.

Behaviour:
  * Key set:     new values are stored as "enc:v1:<token>" and decrypted on read.
  * Key not set: values are stored as plain text (local development) and a
                 warning is printed once at startup.
  * Old plain-text rows keep working: values without the prefix are returned as-is.
  * A value that cannot be decrypted (wrong or rotated key) is returned as ""
    instead of crashing the app, and the problem is logged.
"""

import logging
import os

log = logging.getLogger("cellscope.crypto")

PREFIX = "enc:v1:"
ENCRYPTED_FIELDS = ("phone", "image_data", "heatmap_data")

_fernet = None
_warned = False


def _get_fernet():
    global _fernet, _warned
    if _fernet is not None:
        return _fernet
    key = os.environ.get("CELLSCOPE_ENCRYPTION_KEY", "").strip()
    if not key:
        if not _warned:
            print("[SECURITY] CELLSCOPE_ENCRYPTION_KEY is not set: patient data is stored "
                  "unencrypted. Set it in production.")
            _warned = True
        return None
    from cryptography.fernet import Fernet
    try:
        _fernet = Fernet(key.encode())
    except Exception as err:
        raise RuntimeError(
            "CELLSCOPE_ENCRYPTION_KEY is invalid. Generate one with: python -c \"from "
            "cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        ) from err
    return _fernet


def encryption_enabled() -> bool:
    return _get_fernet() is not None


def encrypt(value):
    """Encrypt a string for storage. None and "" pass through unchanged."""
    if value is None or value == "":
        return value
    value = str(value)
    if value.startswith(PREFIX):
        return value  # already encrypted
    f = _get_fernet()
    if f is None:
        return value
    return PREFIX + f.encrypt(value.encode("utf-8")).decode("ascii")


def decrypt(value):
    """Decrypt a stored value. Plain-text (legacy) values are returned unchanged."""
    if not isinstance(value, str) or not value.startswith(PREFIX):
        return value
    f = _get_fernet()
    if f is None:
        log.error("Encrypted value found but CELLSCOPE_ENCRYPTION_KEY is not set.")
        return ""
    from cryptography.fernet import InvalidToken
    try:
        return f.decrypt(value[len(PREFIX):].encode("ascii")).decode("utf-8")
    except InvalidToken:
        log.error("Could not decrypt a stored value (wrong or rotated key?).")
        return ""


def decrypt_row(row: dict) -> dict:
    """Decrypt every sensitive field present in a DB row dict (in place) and return it."""
    if row is None:
        return None
    for field in ENCRYPTED_FIELDS:
        if field in row:
            row[field] = decrypt(row[field])
    return row
