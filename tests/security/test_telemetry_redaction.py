"""Telemetry is the most commonly overlooked data leak in an AI workload.

Traces and logs contain prompts, retrieved passages and tool arguments by
construction. These tests assert that redaction happens **before** storage
rather than before display, that it cannot be bypassed by inventing a new field
name, and that the field key survives so the telemetry stays queryable after
the value is gone.
"""

from __future__ import annotations

import json
import logging

import pytest

from observability.logging_config import StructuredFormatter, get_logger
from observability.tracing import _safe_attributes
from security.redaction import (
    REDACTED,
    SENSITIVE_KEYS,
    contains_sensitive,
    redact_attributes,
    redact_value,
)

JWT = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJzdWIiOiIxMjM0NTY3ODkwIn0"
    ".dBjftJeZ4CVPmB92K27uhbUJU1p1r_wW1gFWFOEjXk"
)
CONNECTION_STRING = (
    "DefaultEndpointsProtocol=https;AccountName=demo;"
    "AccountKey=abc123def456ghi789jkl012mno345pqr678stu901vwx234yz==;"
    "EndpointSuffix=core.windows.net"
)


class TestRedactionByKey:
    @pytest.mark.parametrize(
        "key",
        ["prompt", "system_prompt", "passage", "rationale", "tool_arguments", "payload"],
    )
    def test_model_and_evidence_content_never_reaches_telemetry(self, key: str) -> None:
        """The fields that carry business content are redacted wholesale. Not
        truncated, not hashed — a hash of a short passage is still a lookup."""
        result = redact_attributes({key: "confidential operating procedure text"})
        assert result[key] == REDACTED

    @pytest.mark.parametrize("key", ["api_key", "authorization", "token", "connection_string"])
    def test_credential_fields_are_redacted(self, key: str) -> None:
        assert redact_attributes({key: "anything at all"})[key] == REDACTED

    @pytest.mark.parametrize("key", ["email", "employee_id", "full_name", "ssn", "phone"])
    def test_personal_data_fields_are_redacted(self, key: str) -> None:
        assert redact_attributes({key: "value"})[key] == REDACTED

    def test_the_key_survives_so_the_field_stays_queryable(self) -> None:
        """Dropping the key breaks "show me every request that carried a
        prompt". Redaction removes the value, not the shape."""
        result = redact_attributes({"prompt": "secret", "correlation_id": "corr_abc12345"})
        assert set(result) == {"prompt", "correlation_id"}
        assert result["correlation_id"] == "corr_abc12345"

    def test_key_matching_is_case_insensitive(self) -> None:
        assert redact_attributes({"API_KEY": "x"})["API_KEY"] == REDACTED
        assert redact_attributes({"Prompt": "x"})["Prompt"] == REDACTED


class TestRedactionByValuePattern:
    def test_a_jwt_is_redacted_under_an_innocuous_key(self) -> None:
        """The control that matters most: redaction cannot be bypassed by
        choosing a field name nobody thought to add to the list."""
        result = redact_attributes({"debug_note": f"received {JWT} from caller"})
        assert JWT not in result["debug_note"]
        assert REDACTED in result["debug_note"]

    def test_a_bearer_header_is_redacted_anywhere_it_appears(self) -> None:
        result = redact_value("Authorization: Bearer abc.def-ghi_jkl")
        assert "abc.def-ghi_jkl" not in result

    def test_a_storage_connection_string_loses_its_key(self) -> None:
        result = redact_value(CONNECTION_STRING)
        assert "abc123def456ghi789jkl012mno345pqr678stu901vwx234yz==" not in result
        # The non-secret parts survive, so the field is still diagnosable.
        assert "AccountName=demo" in result

    def test_an_email_address_is_redacted_from_free_text(self) -> None:
        result = redact_value("escalated by first.last+tag@contoso.com this morning")
        assert "@contoso.com" not in result

    def test_oversized_values_are_truncated_not_stored_whole(self) -> None:
        """An unbounded attribute is both a cost problem and an exfiltration
        path: a whole document fits in one span attribute."""
        result = redact_value("lorem ipsum dolor sit amet " * 400)
        assert len(result) < 600
        assert result.endswith("[truncated]")

    def test_a_long_unbroken_token_is_redacted_rather_than_truncated(self) -> None:
        """Truncating a credential still leaks most of it. Anything long,
        unbroken and base64-shaped is removed outright, even though that costs
        some false positives on hashes."""
        assert redact_value("A" * 5_000) == REDACTED


class TestTraceAttributes:
    def test_span_attributes_are_redacted_by_key_and_by_pattern(self) -> None:
        attributes = _safe_attributes(
            {"prompt": "secret text", "note": f"token {JWT}", "confidence": 0.88}
        )
        assert attributes["prompt"] == REDACTED
        assert JWT not in attributes["note"]

    def test_numeric_attributes_survive_intact(self) -> None:
        """Redaction that mangles counts and latencies gets turned off. The
        numbers are the reason the trace exists."""
        attributes = _safe_attributes({"confidence": 0.8812, "retrieved": 5, "degraded": False})
        assert attributes["confidence"] == 0.8812
        assert attributes["retrieved"] == 5
        assert attributes["degraded"] is False

    def test_a_non_scalar_attribute_is_stringified_and_redacted(self) -> None:
        attributes = _safe_attributes({"context": {"api_key": JWT}})
        assert JWT not in attributes["context"]


class TestStructuredLogging:
    @staticmethod
    def _emit(**extra: object) -> dict[str, object]:
        record = logging.LogRecord(
            name="test.redaction",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="workflow_step",
            args=(),
            exc_info=None,
        )
        for key, value in extra.items():
            setattr(record, key, value)
        return json.loads(StructuredFormatter().format(record))

    def test_redaction_happens_in_the_formatter_not_at_the_call_site(self) -> None:
        """A caller cannot opt out, and a new call site cannot forget."""
        payload = self._emit(prompt="confidential", correlation_id="corr_abc12345")
        assert payload["prompt"] == REDACTED
        assert payload["correlation_id"] == "corr_abc12345"

    def test_the_event_name_and_level_are_preserved(self) -> None:
        payload = self._emit(correlation_id="corr_abc12345")
        assert payload["event"] == "workflow_step"
        assert payload["level"] == "INFO"

    def test_bound_context_and_call_site_fields_are_both_emitted(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """``LoggerAdapter.process`` replaces the caller's ``extra`` by default,
        which silently drops half the structure. This asserts the merge."""
        logger = get_logger("test.merge", component="detector")
        with caplog.at_level(logging.INFO, logger="test.merge"):
            logger.info("detected", extra={"label": "seal_gap"})

        record = caplog.records[-1]
        assert record.component == "detector"
        assert record.label == "seal_gap"

    def test_a_traceback_is_reduced_to_its_type_and_message(self) -> None:
        """Tracebacks echo local variables, and local variables hold payloads."""
        try:
            raise ValueError("upstream returned 503")
        except ValueError:
            import sys  # noqa: PLC0415

            record = logging.LogRecord(
                name="test.redaction",
                level=logging.ERROR,
                pathname=__file__,
                lineno=1,
                msg="workflow_halted",
                args=(),
                exc_info=sys.exc_info(),
            )
        payload = json.loads(StructuredFormatter().format(record))
        assert payload["exception_type"] == "ValueError"
        assert payload["exception_message"] == "upstream returned 503"
        assert "Traceback" not in json.dumps(payload)


class TestRedactionPolicyItself:
    def test_the_sensitive_key_list_covers_the_obvious_categories(self) -> None:
        for expected in ("prompt", "passage", "token", "password", "email", "ssn"):
            assert expected in SENSITIVE_KEYS

    def test_contains_sensitive_is_used_as_a_detector_not_a_redactor(self) -> None:
        """Deliberately excludes the broad base64 heuristic, which fires on
        ordinary hashes. A detector that cries wolf gets ignored."""
        assert contains_sensitive(f"header {JWT}")
        assert not contains_sensitive("sha256:" + "a" * 64)

    def test_redaction_is_idempotent(self) -> None:
        once = redact_value(f"token {JWT}")
        assert redact_value(once) == once
