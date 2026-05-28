"""Metric Protocol — the contract every evaluation metric implements.

A metric takes a single candidate translation plus a list of references and
returns a score in ``[0.0, 1.0]``. Extra context (glossary terms, source
text, language pair) flows in via ``**kwargs`` so metrics that don't need
it stay simple while metrics that do can pull what they need by name.

We deliberately normalise every metric to the same 0..1 range here, even
though chrF natively returns 0..100 and other future metrics may have
different scales. The evaluation report aggregates and stratifies these
scores across many entries — having one consistent scale means the
aggregation code doesn't need to know which metric it's summing.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Metric(Protocol):
    """One scored quality signal computed per translation."""

    @property
    def name(self) -> str:
        """Stable identifier used as a column header and dict key in reports."""
        ...

    def compute(
        self,
        candidate: str,
        references: list[str],
        **kwargs: Any,
    ) -> float:
        """Return a score in ``[0.0, 1.0]`` for the candidate against references.

        ``kwargs`` may carry metric-specific extras (e.g. ``glossary_terms``
        + ``source_text`` for ``GlossaryComplianceMetric``). Metrics ignore
        kwargs they don't recognise.
        """
        ...
