"""Email normalisation for lookup and rate-limit keys (D10 M-7): NFKC, strip, lower."""

import unicodedata


def normalize_email(email: str) -> str:
    return unicodedata.normalize("NFKC", email).strip().lower()
