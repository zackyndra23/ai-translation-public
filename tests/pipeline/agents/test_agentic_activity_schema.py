"""Schema sanity tests for AgenticActivity Pydantic model."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError
from src.pipeline.agents.base import AgenticActivity


def _minimal() -> dict:
    return dict(
        name="lang_detect_input",
        agent_type="language_detection",
        group_index=1,
        latency_ms=400.0,
        status="success",
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
    )


def test_minimal_payload_accepted() -> None:
    activity = AgenticActivity(**_minimal())
    assert activity.name == "lang_detect_input"
    assert activity.status == "success"
    assert activity.model_id is None
    assert activity.cost_usd is None
    assert activity.result is None


def test_failed_status_with_error_fields() -> None:
    payload = _minimal()
    payload["status"] = "failed"
    payload["error_code"] = "rate_limited"
    payload["error_detail"] = "429 from provider"
    activity = AgenticActivity(**payload)
    assert activity.status == "failed"
    assert activity.error_code == "rate_limited"


def test_invalid_status_rejected() -> None:
    payload = _minimal()
    payload["status"] = "pending"
    with pytest.raises(ValidationError):
        AgenticActivity(**payload)


def test_full_llm_call_payload() -> None:
    payload = _minimal()
    payload["model_id"] = "claude-haiku-4-5-20251001"
    payload["prompt_applied"] = "Detect the language of: ..."
    payload["input_tokens"] = 50
    payload["output_tokens"] = 12
    payload["cost_usd"] = Decimal("0.00006")
    payload["result"] = {"detected_lang": "fr", "confidence": 0.95}
    activity = AgenticActivity(**payload)
    assert activity.input_tokens == 50
    assert activity.result == {"detected_lang": "fr", "confidence": 0.95}
