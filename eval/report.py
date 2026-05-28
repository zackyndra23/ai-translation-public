"""Markdown report formatter for the evaluation runner.

The runner produces a structured ``aggregates`` dict; this module turns it
into a human-readable Markdown document suitable for pasting into a PR
description or piping to ``less``. The shape of ``aggregates`` is locked in
the docstring of :func:`format_report` so the runner doesn't drift away
from what this formatter expects.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any


def _fmt_float(x: float | None, digits: int = 3) -> str:
    if x is None:
        return "—"
    return f"{x:.{digits}f}"


def _section_header(text: str) -> list[str]:
    return ["", f"## {text}", ""]


def _table_rows(
    rows: list[dict[str, Any]],
    columns: list[tuple[str, str]],
) -> list[str]:
    """Render ``rows`` as a Markdown table.

    ``columns`` is a list of ``(header, key)`` pairs. The header is what
    shows up at the top of the column; the key looks up the value in each
    row dict. Numeric values are formatted to 3dp.
    """
    if not rows:
        return ["_(no entries)_"]

    headers = [h for h, _ in columns]
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("|" + "|".join("---" for _ in columns) + "|")
    for row in rows:
        cells = []
        for _, key in columns:
            value = row.get(key)
            if isinstance(value, float):
                cells.append(_fmt_float(value))
            elif isinstance(value, Decimal):
                cells.append(f"{value:.6f}")
            elif value is None:
                cells.append("—")
            else:
                cells.append(str(value))
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def format_report(aggregates: dict[str, Any]) -> str:
    """Render an aggregates dict as Markdown.

    Expected ``aggregates`` shape::

        {
            "dataset": str,
            "model": str,
            "total_entries": int,
            "successful": int,
            "failed": int,
            "total_cost_usd": Decimal,
            "total_latency_ms": float,
            "cache_hits": int,
            "by_metric": {
                metric_name: {"mean": float, "p50": float, "p95": float, "count": int}
            },
            "by_language_pair": [
                {"pair": "en→id", "count": int, "metrics": {metric: mean_score}}
            ],
            "by_profile": [
                {"profile": "asuransi", "count": int, "metrics": {metric: mean_score}}
            ],
            "by_difficulty": [
                {"difficulty": "easy", "count": int, "metrics": {metric: mean_score}}
            ],
            "failures": [{"id": str, "error": str}],
        }
    """
    lines: list[str] = ["# Evaluation Report"]

    lines.extend(["", f"**Dataset**: `{aggregates.get('dataset', '?')}`"])
    lines.append(f"**Model**: `{aggregates.get('model', '?')}`")
    lines.append(f"**Total entries**: {aggregates['total_entries']}")
    lines.append(f"**Successful**: {aggregates['successful']}")
    lines.append(f"**Failed**: {aggregates['failed']}")
    cache_hits = aggregates.get("cache_hits", 0)
    lines.append(f"**Cache hits**: {cache_hits}")
    lines.append(f"**Total cost (USD)**: {aggregates['total_cost_usd']:.6f}")
    lines.append(f"**Total wall time**: {aggregates['total_latency_ms']:.0f} ms")

    # ---- overall per-metric stats -----------------------------------------
    lines.extend(_section_header("Overall metric scores"))
    metric_rows = [
        {"metric": name, **stats} for name, stats in aggregates.get("by_metric", {}).items()
    ]
    lines.extend(
        _table_rows(
            metric_rows,
            [
                ("Metric", "metric"),
                ("Mean", "mean"),
                ("p50", "p50"),
                ("p95", "p95"),
                ("N", "count"),
            ],
        )
    )

    # ---- stratified breakdowns --------------------------------------------
    metric_names = list(aggregates.get("by_metric", {}).keys())

    for label, key, group_col in (
        ("By language pair", "by_language_pair", "pair"),
        ("By profile", "by_profile", "profile"),
        ("By difficulty", "by_difficulty", "difficulty"),
    ):
        rows = aggregates.get(key, [])
        if not rows:
            continue
        lines.extend(_section_header(label))
        # Flatten "metrics" sub-dict into columns named after each metric.
        flat_rows = [
            {
                group_col: r[group_col],
                "count": r["count"],
                **{m: r["metrics"].get(m) for m in metric_names},
            }
            for r in rows
        ]
        cols = [(group_col.replace("_", " ").title(), group_col), ("N", "count")]
        cols.extend([(m, m) for m in metric_names])
        lines.extend(_table_rows(flat_rows, cols))

    # ---- failures (if any) ------------------------------------------------
    failures = aggregates.get("failures") or []
    if failures:
        lines.extend(_section_header("Failures"))
        lines.extend(_table_rows(failures, [("ID", "id"), ("Error", "error")]))

    return "\n".join(lines) + "\n"
