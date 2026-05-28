"""Metric name → class registry.

Centralising this lets the CLI runner accept ``--metrics chrf,glossary_compliance``
as a comma-separated string and look up each entry. Adding a new metric
becomes a one-line registry change + one new file — there's nothing else
to update.
"""

from __future__ import annotations

from eval.metrics.base import Metric
from eval.metrics.chrf import ChrFMetric
from eval.metrics.glossary_compliance import GlossaryComplianceMetric

# Map: name (used in CLI flags + report column headers) → constructor.
# Constructors take no args today; if a future metric needs config, we'll
# either keep the no-args interface (and read config from a settings module)
# or evolve the registry to accept a builder callable. YAGNI for now.
METRIC_REGISTRY: dict[str, type[Metric]] = {
    "chrf": ChrFMetric,
    "glossary_compliance": GlossaryComplianceMetric,
}

DEFAULT_METRICS = ("chrf", "glossary_compliance")


class UnknownMetricError(KeyError):
    """Raised when the CLI asks for a metric name we don't have."""


def get_metric(name: str) -> Metric:
    """Construct the metric registered under ``name``.

    Raises :class:`UnknownMetricError` (a ``KeyError`` subclass) so a typo
    on the CLI produces a clear error rather than ``KeyError: 'chfr'``.
    """
    cls = METRIC_REGISTRY.get(name)
    if cls is None:
        raise UnknownMetricError(f"Unknown metric {name!r}. Known: {sorted(METRIC_REGISTRY)}")
    return cls()
