"""Untrusted-input sanitisation.

Retrieved documents and tool output are data, not instruction. This module does
not attempt to "detect prompt injection" reliably — that is not achievable and
claiming it would be dishonest. What it does is narrower and useful:

* wrap untrusted content in an explicit, non-forgeable delimiter,
* strip control characters and delimiter-spoofing sequences,
* surface a signal so an injection attempt is *logged and evaluated* rather
  than silently absorbed.

The actual containment is architectural: least-privilege identities, typed tool
schemas, deterministic policy outside the model, and a writer that will not act
without a bound approval. This function reduces noise; it is not the control.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Deliberately not a "blocklist that makes you safe". These are heuristics whose
# only job is to raise a reviewable signal for the evaluation harness.
_SUSPICIOUS_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("instruction_override", re.compile(r"(?i)\bignore (all |the )?(previous|prior|above)\b")),
    ("role_switch", re.compile(r"(?i)\b(you are now|act as|from now on,? you)\b")),
    (
        "system_prompt_probe",
        re.compile(r"(?i)\b(system prompt|your instructions|reveal .*prompt)\b"),
    ),
    ("tool_coercion", re.compile(r"(?i)\b(call|invoke|execute) the .{0,40}(tool|function|api)\b")),
    ("exfiltration", re.compile(r"(?i)\b(send|post|upload|email) .{0,40}(to|at) https?://")),
    (
        "authority_claim",
        re.compile(r"(?i)\b(approved by|authori[sz]ed by|no approval (is )?needed)\b"),
    ),
    ("delimiter_spoof", re.compile(r"(?i)(</?untrusted[^>]*>|```system|<\|im_start\|>)")),
)

_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

UNTRUSTED_OPEN = "<untrusted_document>"
UNTRUSTED_CLOSE = "</untrusted_document>"


@dataclass(frozen=True, slots=True)
class SanitisedContent:
    """Cleaned text plus the signals worth recording about it."""

    text: str
    signals: tuple[str, ...]
    modified: bool

    @property
    def suspicious(self) -> bool:
        return bool(self.signals)


def sanitise_untrusted(text: str) -> SanitisedContent:
    """Neutralise delimiter spoofing and report injection-shaped signals."""
    signals = tuple(name for name, pattern in _SUSPICIOUS_PATTERNS if pattern.search(text))

    cleaned = _CONTROL_CHARACTERS.sub(" ", text)
    # Break any attempt to close the untrusted block early.
    cleaned = cleaned.replace(UNTRUSTED_CLOSE, "&lt;/untrusted_document&gt;")
    cleaned = cleaned.replace(UNTRUSTED_OPEN, "&lt;untrusted_document&gt;")
    cleaned = re.sub(r"<\|im_(start|end)\|>", "", cleaned)

    return SanitisedContent(text=cleaned, signals=signals, modified=cleaned != text)


def wrap_untrusted(text: str, *, citation_ref: str) -> str:
    """Render a passage for a prompt with its provenance and its status attached."""
    sanitised = sanitise_untrusted(text)
    return (
        f'{UNTRUSTED_OPEN} ref="{citation_ref}" trust="none">\n{sanitised.text}\n{UNTRUSTED_CLOSE}'
    )
