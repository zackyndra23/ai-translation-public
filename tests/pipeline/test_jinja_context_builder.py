"""Tests for the build_jinja_context pipeline stage."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest
from src.pipeline.schemas import PipelineRequest
from src.pipeline.stages import PipelineContext, build_jinja_context
from src.tenant_profile.resolver import ResolvedTenantProfile

pytestmark = pytest.mark.asyncio


def _make_ctx() -> PipelineContext:
    ctx = PipelineContext(
        request=PipelineRequest(
            text="Halo, selamat pagi",
            source_lang="id",
            target_lang="en",
            profile_id="profile-x",
            tenant_id="tenant-x",
        ),
        trace_id=uuid.uuid4().hex,
        started_at_perf=time.perf_counter(),
        started_at=datetime.now(UTC),
    )
    ctx.normalized_text = "Halo, selamat pagi"
    ctx.resolved_tenant_profile = ResolvedTenantProfile(
        profile_id="profile-x",
        tenant_id="tenant-x",
        tenant_name="PT Test — Sales (Indonesia)",
        country_name="Indonesia",
        company_name="PT Test",
        department_name="Sales",
        position_name="Sales Executive",
        service_name="general",
        service_id="service-x",
        service_tone="professional formal",
        service_target_audience="corporate clients",
        allowed_language=None,
        prompt_applied=["lang_detect_input", "translate", "lang_detect_output"],
    )
    ctx.selected_glossary = []
    ctx.selected_examples = []
    return ctx


async def test_context_populated_with_all_fields() -> None:
    ctx = _make_ctx()
    iso_repo = AsyncMock()
    iso_repo.get_name = AsyncMock(
        side_effect=lambda code: {"id": "Indonesian", "en": "English"}.get(code)
    )

    await build_jinja_context(ctx, iso_repo)

    assert ctx.jinja_context is not None
    assert ctx.jinja_context["tenant_name"] == "PT Test — Sales (Indonesia)"
    assert ctx.jinja_context["country_name"] == "Indonesia"
    assert ctx.jinja_context["service_tone"] == "professional formal"
    assert ctx.jinja_context["source_lang_code"] == "id"
    assert ctx.jinja_context["source_lang_name"] == "Indonesian"
    assert ctx.jinja_context["target_lang_code"] == "en"
    assert ctx.jinja_context["target_lang_name"] == "English"
    assert ctx.jinja_context["text"] == "Halo, selamat pagi"


async def test_context_falls_back_to_code_when_iso_miss() -> None:
    """If iso_languages.get_name returns None, use the code as the name."""
    ctx = _make_ctx()
    iso_repo = AsyncMock()
    iso_repo.get_name = AsyncMock(return_value=None)

    await build_jinja_context(ctx, iso_repo)
    assert ctx.jinja_context is not None
    assert ctx.jinja_context["source_lang_name"] == "id"
    assert ctx.jinja_context["target_lang_name"] == "en"


async def test_context_uses_detected_source_lang_when_present() -> None:
    """If lang_detect agent set ctx.detected_source_lang, prefer it over request.source_lang."""
    ctx = _make_ctx()
    ctx.detected_source_lang = "ms"
    iso_repo = AsyncMock()
    iso_repo.get_name = AsyncMock(side_effect=lambda c: {"ms": "Malay"}.get(c, c))
    await build_jinja_context(ctx, iso_repo)
    assert ctx.jinja_context is not None
    assert ctx.jinja_context["source_lang_code"] == "ms"
    assert ctx.jinja_context["source_lang_name"] == "Malay"


async def test_context_includes_glossary_and_examples() -> None:
    ctx = _make_ctx()
    glossary_term: Any = type(
        "T",
        (),
        {
            "source_term": "background check",
            "target_term": "pemeriksaan latar belakang",
            "is_forbidden": False,
        },
    )()
    example: Any = type("E", (), {"source_text": "X", "target_text": "Y"})()
    ctx.selected_glossary = [glossary_term]
    ctx.selected_examples = [example]
    iso_repo = AsyncMock()
    iso_repo.get_name = AsyncMock(return_value="Lang")
    await build_jinja_context(ctx, iso_repo)
    assert ctx.jinja_context is not None
    assert len(ctx.jinja_context["glossary_terms"]) == 1
    assert len(ctx.jinja_context["style_examples"]) == 1


async def test_context_handles_null_source_lang() -> None:
    """If request.source_lang is None and no detected_source_lang, source_lang_code is empty string."""
    ctx = _make_ctx()
    ctx.request = PipelineRequest(
        text="hello",
        target_lang="en",
        profile_id="profile-x",
        tenant_id="tenant-x",
        source_lang=None,
    )
    iso_repo = AsyncMock()
    iso_repo.get_name = AsyncMock(return_value=None)
    await build_jinja_context(ctx, iso_repo)
    assert ctx.jinja_context is not None
    assert ctx.jinja_context["source_lang_code"] == ""
    assert ctx.jinja_context["source_lang_name"] == ""
