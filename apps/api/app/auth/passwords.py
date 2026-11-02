"""argon2id password verification with a constant-time miss path (D9, D10 L-3)."""

from contextlib import suppress

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()  # argon2id, RFC 9106 low-memory profile

# Hash of a random throwaway password, computed once. Verifying against it costs the same as a
# real verify, so an unknown email or a user without a hash takes as long as a wrong password.
_DUMMY_HASH = _hasher.hash("insmartfix-dummy-password-for-timing-parity")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored_hash: str | None, password: str) -> bool:
    """True only if `stored_hash` is a valid argon2 hash of `password`. Always does one verify."""
    if stored_hash is None:
        dummy_verify(password)  # looked up through the module so tests can spy on it
        return False
    try:
        return _hasher.verify(stored_hash, password)
    except VerifyMismatchError:
        return False
    except (InvalidHashError, VerificationError):
        return False


def dummy_verify(password: str) -> None:
    with suppress(VerifyMismatchError):
        _hasher.verify(_DUMMY_HASH, password)
