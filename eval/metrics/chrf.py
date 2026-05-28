"""chrF metric — character n-gram F-score from sacrebleu.

Why chrF (and not BLEU): chrF is character-based, so it doesn't depend on
language-specific tokenisation. That matters when we're evaluating
EN→ID/JA/ZH in the same harness — BLEU's word tokenisation would have to
swap per target language, and tokeniser choice would dominate scores in
subtle ways. chrF sidesteps that entire problem.

Multi-reference handling: chrF takes the *max* over references (best
match), which is the right thing for our golden set where ``alt_references``
exists to capture legitimate paraphrases (not multiple gold standards we
average).

Output range: sacrebleu's chrF returns 0..100; we normalise to 0..1 here
so the report aggregator treats every metric the same way.
"""

from __future__ import annotations

from typing import Any

from sacrebleu.metrics import CHRF  # type: ignore[attr-defined]


class ChrFMetric:
    """character n-gram F-score, normalised to ``[0.0, 1.0]``."""

    def __init__(self) -> None:
        # Default chrF (n=6 char order, beta=2) — the same parameters
        # sacrebleu uses as the published "chrF" reference implementation.
        self._chrf = CHRF()

    @property
    def name(self) -> str:
        return "chrf"

    def compute(
        self,
        candidate: str,
        references: list[str],
        **kwargs: Any,
    ) -> float:
        # An empty reference list means we have nothing to score against —
        # return 0 explicitly so a forgotten reference shows up in the
        # report as "zero quality" rather than a silent NaN.
        if not references:
            return 0.0

        # sacrebleu's ``corpus_score`` expects ``references`` as a list of
        # reference *sets* — one entry per reference, each entry a list of
        # hypotheses (one hypothesis here, so one-element inner lists).
        ref_sets: list[list[str]] = [[ref] for ref in references]
        score = self._chrf.corpus_score([candidate], ref_sets).score

        # sacrebleu returns 0..100. We carry 0..1 throughout the harness.
        return float(score) / 100.0
