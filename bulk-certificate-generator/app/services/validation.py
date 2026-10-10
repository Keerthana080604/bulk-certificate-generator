"""Recipient-level validation (content checks + duplicate policy)."""
import re
from dataclasses import dataclass

from app.core.config import (
    DEFAULT_CERTIFICATE_TITLE,
    MAX_EMAIL_LEN,
    MAX_NAME_LEN,
    MAX_TITLE_LEN,
)
from app.schemas.jobs import RecipientIn

# Deliberately simple: one "@", no spaces, a dot in the domain. Real verification
# of an address needs to send mail to it, which is out of scope.
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$")


@dataclass
class ValidatedRecipient:
    position: int
    name: str
    email: str
    title: str
    error: str | None  # None means the recipient is valid


def _font_safe(text: str) -> bool:
    try:
        text.encode("cp1252")
        return True
    except UnicodeEncodeError:
        return False


def _validate_text_field(label: str, value: str, max_len: int, errors: list[str]) -> None:
    if len(value) > max_len:
        errors.append(f"{label} exceeds {max_len} characters")
    elif not value.isprintable():
        errors.append(f"{label} contains control characters")
    elif not _font_safe(value):
        errors.append(f"{label} contains characters the certificate font cannot render")


def validate_recipients(recipients: list[RecipientIn]) -> list[ValidatedRecipient]:
    """Validate every recipient; never raises for bad content.

    Duplicate policy: same email (case-insensitive) + same certificate title within
    one request. The first valid occurrence is kept; later ones are marked invalid.
    """
    results: list[ValidatedRecipient] = []
    seen: set[tuple[str, str]] = set()

    for position, rec in enumerate(recipients):
        errors: list[str] = []
        name = (rec.name or "").strip()
        email = (rec.email or "").strip()
        title = DEFAULT_CERTIFICATE_TITLE if rec.certificate_title is None else rec.certificate_title.strip()

        if not name:
            errors.append("name is required")
        else:
            _validate_text_field("name", name, MAX_NAME_LEN, errors)

        if not email:
            errors.append("email is required")
        elif len(email) > MAX_EMAIL_LEN:
            errors.append(f"email exceeds {MAX_EMAIL_LEN} characters")
        elif not EMAIL_RE.match(email):
            errors.append("email is not a valid address")

        if not title:
            errors.append("certificate_title must not be blank")
        else:
            _validate_text_field("certificate_title", title, MAX_TITLE_LEN, errors)

        if not errors:
            key = (email.lower(), title.lower())
            if key in seen:
                errors.append("duplicate recipient (same email and certificate title)")
            else:
                seen.add(key)

        results.append(
            ValidatedRecipient(
                position=position,
                # Clip what we STORE so a huge invalid value cannot bloat the DB.
                name=name[:MAX_NAME_LEN],
                email=email[:MAX_EMAIL_LEN],
                title=title[:MAX_TITLE_LEN],
                error="; ".join(errors) if errors else None,
            )
        )
    return results
