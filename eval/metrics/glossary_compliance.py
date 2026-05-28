"""Glossary compliance metric — thin adapter over the pipeline's compliance util.

We deliberately do NOT reimplement the scoring here. The pipeline
(:mod:`src.pipeline.compliance`) already has the canonical logic for "given
this candidate translation, the source text, and the glossary terms, what
fraction of applicable rules were honoured?" — the eval harness should
report the same number the runtime produced, otherwise eval scores and
production telemetry would drift apart and we'd have to debug "which
calculation is right" instead of "which translation is wrong".

This file is a Metric-protocol wrapper around that function so the runner
treats it the same as chrF.
"""

from __future__ import annotations

from typing import Any

from src.pipeline.compliance import compute_glossary_compliance
from src.profiles.schemas import ResolvedGlossaryTerm


class GlossaryComplianceMetric:
    """Score = fraction of applicable glossary rules honoured.

    Required kwargs: ``glossary_terms`` (list of :class:`ResolvedGlossaryTerm`)
    and ``source_text`` (str). When either is missing or empty we score
    1.0 — "nothing to comply with" matches the convention in the underlying
    function and means missing-context entries don't artificially drag the
    aggregate down.
    """

    @property
    def name(self) -> str:
        return "glossary_compliance"

    def compute(
        self,
        candidate: str,
        references: list[str],
        **kwargs: Any,
    ) -> float:
        glossary_terms: list[ResolvedGlossaryTerm] = kwargs.get("glossary_terms") or []
        source_text: str = kwargs.get("source_text") or ""
        if not glossary_terms or not source_text:
            return 1.0

        score, _violations = compute_glossary_compliance(
            translation=candidate,
            source_text=source_text,
            glossary_terms=glossary_terms,
        )
        return score
