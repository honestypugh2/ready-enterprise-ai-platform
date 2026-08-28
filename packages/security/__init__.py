"""Security plane.

Two responsibilities that must not live anywhere else:

* **Redaction** — applied before telemetry or an audit receipt is written, so a
  prompt, passage or credential never enters the store in the first place.
* **Sanitisation** — retrieved content is untrusted input. This package makes
  that explicit in the payload and raises a reviewable signal; the actual
  containment is architectural (identity, typed tools, deterministic policy,
  a writer that requires a bound approval).

Identity and network controls are infrastructure concerns and live in ``infra/``
and ``docs/security/``.
"""

from security.identity import IdentityContext, WorkloadIdentity, resolve_credential
from security.redaction import (
    REDACTED,
    SENSITIVE_KEYS,
    contains_sensitive,
    redact_attributes,
    redact_value,
)
from security.sanitisation import (
    UNTRUSTED_CLOSE,
    UNTRUSTED_OPEN,
    SanitisedContent,
    sanitise_untrusted,
    wrap_untrusted,
)

__all__ = [
    "REDACTED",
    "SENSITIVE_KEYS",
    "UNTRUSTED_CLOSE",
    "UNTRUSTED_OPEN",
    "IdentityContext",
    "SanitisedContent",
    "WorkloadIdentity",
    "contains_sensitive",
    "redact_attributes",
    "redact_value",
    "resolve_credential",
    "sanitise_untrusted",
    "wrap_untrusted",
]
