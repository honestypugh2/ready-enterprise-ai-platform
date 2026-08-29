"""Telemetry and audit redaction.

Telemetry is the most commonly overlooked data leak in an AI workload, because
traces contain prompts, retrieved passages and tool arguments by construction.
Redaction therefore happens **before** storage rather than before display, and
the key is preserved so the field remains queryable after its value is gone.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

REDACTED = "[redacted]"

# Keys whose VALUES must never reach telemetry or an audit receipt. Extend this
# after a data classification review, not after an incident.
SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "prompt",
        "system_prompt",
        "answer",
        "content",
        "passage",
        "passages",
        "rationale",
        "tool_arguments",
        "payload",
        "authorization",
        "api_key",
        "apikey",
        "secret",
        "password",
        "token",
        "access_token",
        "connection_string",
        "email",
        "full_name",
        "address",
        "phone",
        "ssn",
        "employee_id",
    }
)

# Content hashes and fingerprints. These are the identifiers an audit receipt
# exists to carry — which frame was inspected, which policy file produced the
# verdict, which proposal was approved — and they are not secret. They are
# matched first and preserved, because the credential heuristic below cannot
# distinguish a hex digest from a base64 key and was silently destroying them.
_PRESERVED = re.compile(r"\b(?:sha256|sha512|sha1|md5):[0-9a-f]{32,128}\b")

# Values that look like credentials regardless of the key they arrive under.
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b")),
    # Requires evidence of base64: mixed case, or padding, or a non-hex symbol.
    # A lowercase hex digest therefore does not match, while a real key — which
    # is base64 of random bytes — effectively always does.
    (
        "azure_key",
        re.compile(
            r"\b(?=[A-Za-z0-9+/]{40,}={0,2}\b)"
            r"(?=[A-Za-z0-9+/=]*[A-Z])"
            r"(?=[A-Za-z0-9+/=]*[a-z])"
            r"[A-Za-z0-9+/]{40,}={0,2}\b"
        ),
    ),
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("bearer", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]+")),
    ("connection_string", re.compile(r"(?i)\b(AccountKey|SharedAccessKey|Password)=[^;\s]+")),
)

_MAX_VALUE_LENGTH = 512
_PLACEHOLDER = "\x00\x00PRESERVED{}\x00\x00"


def redact_value(value: Any) -> str:
    """Redact credential-shaped content and cap length.

    Provenance hashes are held out of the credential scan. Without that, the
    audit chain still verifies but can no longer say which frame was inspected
    or which policy version decided it.
    """
    text = str(value)

    preserved: list[str] = []

    def _hold(match: re.Match[str]) -> str:
        preserved.append(match.group(0))
        return _PLACEHOLDER.format(len(preserved) - 1)

    text = _PRESERVED.sub(_hold, text)
    for _, pattern in _PATTERNS:
        text = pattern.sub(REDACTED, text)
    for index, original in enumerate(preserved):
        text = text.replace(_PLACEHOLDER.format(index), original)

    if len(text) > _MAX_VALUE_LENGTH:
        text = text[:_MAX_VALUE_LENGTH] + "…[truncated]"
    return text


def redact_attributes(attributes: Mapping[str, Any]) -> dict[str, str]:
    """Redact by key, then by value pattern. The key itself is always preserved."""
    result: dict[str, str] = {}
    for key, value in attributes.items():
        if key.lower() in SENSITIVE_KEYS:
            result[key] = REDACTED
        else:
            result[key] = redact_value(value)
    return result


def contains_sensitive(text: str) -> bool:
    """True when a credential-shaped token is present. Used by the redaction tests."""
    return any(pattern.search(text) for name, pattern in _PATTERNS if name != "azure_key")
