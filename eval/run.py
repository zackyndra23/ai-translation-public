"""CLI evaluation runner.

Run with::

    uv run python -m eval.run --dataset eval/datasets/golden_v1.jsonl --limit 3

What it does:

1. Load a JSONL dataset and filter entries (profile / target_lang / limit).
2. Estimate the upstream API cost up front and prompt the operator before
   spending real money. ``--yes`` skips the prompt for scripted use.
3. For each entry, call the same :class:`TranslationPipeline` the API uses
   (real provider, real cache — cache hits do NOT cost money and are
   reported in the aggregate).
4. Run each requested metric against the candidate translation.
5. Aggregate scores (overall mean / p50 / p95 + stratified by language
   pair, profile, difficulty).
6. Emit a Markdown report to stdout AND a full-detail JSON dump to
   ``eval/results/{timestamp}_{dataset}.json``.

The cost / time accounting separates "what we spent on this run" (real
USD) from "what the entry's translation actually cost" (zero on cache
hits) — see how ``total_cost_usd`` aggregates only fresh-call costs.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time

# Windows consoles default to cp1252 — any non-ASCII content in the report
# (arrows, accented chars, ...) would otherwise crash the print. Reconfiguring
# once at module load is cheap and applies to every subsequent ``print``.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from src.cache.redis_cache import RedisCache
from src.config.logging import get_logger
from src.config.settings import get_settings
from src.db.session import SessionLocal
from src.pipeline.pipeline import TranslationPipeline, build_template_env
from src.pipeline.schemas import PipelineRequest
from src.profiles.repository import ProfileRepository
from src.profiles.resolver import ProfileResolver
from src.providers.factory import get_provider
from src.providers.pricing import estimate_cost as estimate_provider_cost

from eval.metrics.registry import DEFAULT_METRICS, get_metric
from eval.report import format_report

log = get_logger(__name__)
DEFAULT_TENANT_NAME = "internal-company"


# ---- CLI ------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="eval.run",
        description="Run the translation pipeline against a golden dataset and score the outputs.",
    )
    p.add_argument(
        "--dataset",
        required=True,
        help="Path to a JSONL dataset under eval/datasets/.",
    )
    p.add_argument("--profile", default=None, help="Only run entries with this profile slug.")
    p.add_argument(
        "--target-lang", default=None, help="Only run entries with this target language."
    )
    p.add_argument(
        "--metrics",
        default=",".join(DEFAULT_METRICS),
        help=f"Comma-separated metric names (default: {','.join(DEFAULT_METRICS)}).",
    )
    p.add_argument("--output-dir", default="eval/results", help="Where to write JSON results.")
    p.add_argument(
        "--limit", type=int, default=None, help="Cap entries to the first N (smoke test)."
    )
    p.add_argument(
        "--yes",
        action="store_true",
        help="Skip the cost-confirmation prompt. Useful in CI / scripted runs.",
    )
    return p.parse_args(argv)


# ---- Dataset I/O ----------------------------------------------------------


def _load_dataset(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")
    entries: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for line_no, raw in enumerate(fh, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"Bad JSON at {path}:{line_no}: {e}") from e
    return entries


def _filter(
    entries: list[dict[str, Any]],
    *,
    profile: str | None,
    target_lang: str | None,
    limit: int | None,
) -> list[dict[str, Any]]:
    filtered = entries
    if profile is not None:
        filtered = [e for e in filtered if e.get("profile") == profile]
    if target_lang is not None:
        filtered = [e for e in filtered if e.get("target_lang") == target_lang]
    if limit is not None:
        filtered = filtered[:limit]
    return filtered


# ---- Cost preview ---------------------------------------------------------


def _estimate_total_cost(entries: list[dict[str, Any]], model_id: str) -> Decimal:
    """Sum the per-entry pricing estimate.

    This is the *upper bound* on what the run will cost — cache hits during
    the run pay zero, so the actual spend will usually be lower.
    """
    total = Decimal("0")
    for e in entries:
        total += estimate_provider_cost(model_id, e.get("source_text", ""), output_ratio=1.0)
    return total


def _confirm(prompt: str) -> bool:
    """Y/n confirmation. Returns True only on an explicit ``y``."""
    answer = input(prompt).strip().lower()
    return answer in {"y", "yes"}


# ---- Percentiles ----------------------------------------------------------


def _percentile(data: list[float], p: float) -> float | None:
    """Linear-interpolated percentile.

    We roll our own (rather than ``statistics.quantiles``) because the
    stdlib function needs ``n>=2`` and our smoke tests run with ``--limit 1``.
    Empty data → ``None`` so the report formatter prints ``—`` not ``0.0``.
    """
    if not data:
        return None
    s = sorted(data)
    k = (len(s) - 1) * p
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (k - f) * (s[c] - s[f])


# ---- Aggregation ----------------------------------------------------------


def _stratify(
    results: list[dict[str, Any]],
    *,
    group_key: str,
    metric_names: list[str],
) -> list[dict[str, Any]]:
    """Group ``results`` by ``group_key`` and compute mean per metric.

    Returns a list of dicts ``{<group_key>, count, metrics: {metric: mean}}``
    sorted by group label. We don't include failed entries in metric means
    (they have no scores), but they DO count toward ``count`` so an operator
    can see how many entries fell into the bucket vs. how many actually
    produced a translation.
    """
    buckets: dict[str, list[dict[str, Any]]] = {}
    for r in results:
        if group_key == "language_pair":
            # ASCII arrow rather than U+2192 so the same report renders on
            # consoles without UTF-8 support.
            key = f"{r.get('source_lang')}->{r.get('target_lang')}"
        else:
            key = str(r.get(group_key) or "—")
        buckets.setdefault(key, []).append(r)

    rows: list[dict[str, Any]] = []
    for label, items in sorted(buckets.items()):
        scored = [i for i in items if i.get("metric_scores")]
        metric_means: dict[str, float | None] = {}
        for m in metric_names:
            values = [i["metric_scores"][m] for i in scored if m in i.get("metric_scores", {})]
            metric_means[m] = sum(values) / len(values) if values else None
        rows.append(
            {
                group_key.replace("language_pair", "pair")
                if group_key == "language_pair"
                else group_key: label,
                "pair"
                if group_key == "language_pair"
                else group_key.replace("language_pair", ""): label,
                "count": len(items),
                "metrics": metric_means,
            }
        )
    # The hacky double-key above is to satisfy the report formatter (uses
    # "pair" for language groupings and the literal key name elsewhere).
    # Clean up by keeping only the right key per row:
    cleaned: list[dict[str, Any]] = []
    for r in rows:
        if group_key == "language_pair":
            cleaned.append({"pair": r["pair"], "count": r["count"], "metrics": r["metrics"]})
        else:
            cleaned.append({group_key: r[group_key], "count": r["count"], "metrics": r["metrics"]})
    return cleaned


def _build_aggregates(
    *,
    dataset_name: str,
    model_id: str,
    results: list[dict[str, Any]],
    metric_names: list[str],
    total_wall_ms: float,
) -> dict[str, Any]:
    successful = [r for r in results if "error" not in r]
    failures = [{"id": r["id"], "error": r["error"]} for r in results if "error" in r]

    # Overall per-metric stats — only counts entries where the metric ran.
    by_metric: dict[str, dict[str, Any]] = {}
    for m in metric_names:
        values = [r["metric_scores"][m] for r in successful if m in r.get("metric_scores", {})]
        by_metric[m] = {
            "mean": sum(values) / len(values) if values else None,
            "p50": _percentile(values, 0.5),
            "p95": _percentile(values, 0.95),
            "count": len(values),
        }

    total_cost = sum(
        (Decimal(r.get("cost_usd", "0")) for r in successful),
        start=Decimal("0"),
    )
    cache_hits = sum(1 for r in successful if r.get("cached"))

    return {
        "dataset": dataset_name,
        "model": model_id,
        "total_entries": len(results),
        "successful": len(successful),
        "failed": len(failures),
        "cache_hits": cache_hits,
        "total_cost_usd": total_cost,
        "total_latency_ms": total_wall_ms,
        "by_metric": by_metric,
        "by_language_pair": _stratify(
            successful, group_key="language_pair", metric_names=metric_names
        ),
        "by_profile": _stratify(successful, group_key="profile", metric_names=metric_names),
        "by_difficulty": _stratify(successful, group_key="difficulty", metric_names=metric_names),
        "failures": failures,
    }


def _jsonable(value: Any) -> Any:
    """Recursively convert Decimal → str so json.dumps doesn't choke."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    return value


# ---- Per-entry execution --------------------------------------------------


async def _run_entry(
    entry: dict[str, Any],
    *,
    pipeline: TranslationPipeline,
    resolver: ProfileResolver,
    tenant_id: Any,
    metrics: list[Any],
) -> dict[str, Any]:
    """Translate one entry and score it. Errors are captured, not raised."""
    eid = entry.get("id", "?")
    try:
        request = PipelineRequest(
            text=entry["source_text"],
            target_lang=entry["target_lang"],
            profile_slug=entry["profile"],
            tenant_id=tenant_id,
            source_lang=entry.get("source_lang"),
        )
        result = await pipeline.translate(request)
        # Resolve the profile separately so we can hand glossary terms to
        # the compliance metric. The pipeline's own cache would normally
        # mean this is cheap; tenant-bound resolution stays in-process.
        resolved = await resolver.resolve(tenant_id, entry["profile"])
        references = [entry["reference"], *entry.get("alt_references", [])]
        scores: dict[str, float] = {}
        for metric in metrics:
            scores[metric.name] = metric.compute(
                candidate=result.translation,
                references=references,
                glossary_terms=resolved.glossary_terms,
                source_text=entry["source_text"],
            )
        return {
            "id": eid,
            "source_text": entry["source_text"],
            "source_lang": entry.get("source_lang"),
            "target_lang": entry.get("target_lang"),
            "profile": entry.get("profile"),
            "difficulty": entry.get("difficulty"),
            "reference": entry["reference"],
            "translation": result.translation,
            "metric_scores": scores,
            "cached": result.cached,
            "latency_ms": result.latency_ms,
            "cost_usd": str(result.cost_usd),
        }
    except Exception as e:
        log.warning("eval.entry_failed", entry_id=eid, error=str(e), error_type=type(e).__name__)
        return {
            "id": eid,
            "source_lang": entry.get("source_lang"),
            "target_lang": entry.get("target_lang"),
            "profile": entry.get("profile"),
            "difficulty": entry.get("difficulty"),
            "error": f"{type(e).__name__}: {e}",
        }


# ---- Main -----------------------------------------------------------------


async def _async_main(args: argparse.Namespace) -> int:
    settings = get_settings()
    dataset_path = Path(args.dataset)
    entries = _filter(
        _load_dataset(dataset_path),
        profile=args.profile,
        target_lang=args.target_lang,
        limit=args.limit,
    )
    if not entries:
        print("No entries after filtering — nothing to evaluate.")
        return 1

    metric_names = [m.strip() for m in args.metrics.split(",") if m.strip()]
    metrics = [get_metric(m) for m in metric_names]

    estimated_cost = _estimate_total_cost(entries, settings.anthropic_model)
    print(
        f"About to run {len(entries)} translations against model "
        f"`{settings.anthropic_model}`, estimated upstream cost up to "
        f"${estimated_cost:.4f} (cache hits will reduce this)."
    )
    if not args.yes and not _confirm("Continue? [y/N] "):
        print("Aborted.")
        return 0

    # Build the pipeline once for the whole run.
    cache = RedisCache(redis_url=settings.redis_url)
    provider = get_provider("claude-sonnet")
    haiku_provider = get_provider("claude-sonnet", model_id_override=settings.anthropic_haiku_model)
    template_env = build_template_env()

    results: list[dict[str, Any]] = []
    start = time.perf_counter()
    async with SessionLocal() as session:
        repo = ProfileRepository(session)
        tenant = await repo.get_tenant_by_name(DEFAULT_TENANT_NAME)
        if tenant is None:
            print(
                f"ERROR: tenant {DEFAULT_TENANT_NAME!r} missing. "
                "Run scripts/seed_sample_profile.py first."
            )
            return 2
        resolver = ProfileResolver(repo)
        pipeline = TranslationPipeline(
            provider=provider,
            haiku_provider=haiku_provider,
            cache=cache,
            resolver=resolver,
            template_env=template_env,
            model_id=settings.anthropic_model,
            haiku_model_id=settings.anthropic_haiku_model,
        )

        for entry in entries:
            results.append(
                await _run_entry(
                    entry,
                    pipeline=pipeline,
                    resolver=resolver,
                    tenant_id=tenant.id,
                    metrics=metrics,
                )
            )

    wall_ms = (time.perf_counter() - start) * 1000.0
    aggregates = _build_aggregates(
        dataset_name=dataset_path.name,
        model_id=settings.anthropic_model,
        results=results,
        metric_names=metric_names,
        total_wall_ms=wall_ms,
    )

    # Stdout: Markdown report.
    print()
    print(format_report(aggregates))

    # JSON: full per-entry detail.
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_path = output_dir / f"{timestamp}_{dataset_path.stem}.json"
    out_path.write_text(
        json.dumps(
            {
                "aggregates": _jsonable(aggregates),
                "entries": _jsonable(results),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"Full results saved to: {out_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    return asyncio.run(_async_main(args))


if __name__ == "__main__":
    sys.exit(main())
