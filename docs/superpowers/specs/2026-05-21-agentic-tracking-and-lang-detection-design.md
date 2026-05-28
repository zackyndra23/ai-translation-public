# Design — Agentic Activity Tracking + Language Detection (Sub-proyek G + C)

> **Tanggal**: 2026-05-21
> **Status**: Approved (brainstorm), pending implementation plan
> **Author**: zaky + Claude (brainstorm session)
> **Sub-proyek**: G (agentic infrastructure) + C (language detection) bundled
> **Depends on**: sub-proyek B (translation_logs, forward C columns) — already shipped
> **Unblocks**: future agents (quality_check, summarizer, etc.) — drop in to existing parallel-groups orchestration

---

## 1. Konteks & motivasi

Saat ini pipeline hanya ada satu LLM call (the translate stage). Per stakeholder demo request, kita perlu menggambarkan "agentic AI" — multi-step LLM orchestration di mana setiap step punya prompt, tokens, cost, latency yang ter-record dan ter-visualize.

Sub-proyek B sudah menyiapkan forward columns (`detected_source_lang`, `detected_output_lang`, `source_lang_mismatch`, `output_lang_mismatch`) di `translation_logs` untuk diisi oleh sub-proyek C. Sub-proyek G adalah infrastruktur agentic yang membuat sub-proyek C natural fit (lang detection sebagai agent, bukan stage).

**Bundled scope:**
- **G**: Agent abstraction (`AgenticActivity`, `Agent` Protocol, parallel-groups orchestration), persisted via JSONB column + Redis cache, Streamlit visualization.
- **C**: First two concrete agents — `lang_detect_input` (Group 1 parallel with translate) and `lang_detect_output` (Group 2). Mismatch flags populate the existing forward columns.

## 2. Goals & non-goals

**Goals:**
- Pipeline runs 3 agents per `/translate` request (lang_detect_input + translate in parallel, lang_detect_output sequential after) — each agent's prompt + tokens + cost + latency recorded.
- API response carries `agentic_activities: list[AgenticActivity]` plus top-level mismatch flags.
- DB persists full agentic_activities list (JSONB) and populates sub-proyek B's forward columns.
- Redis cache stores agentic_activities so cache hits replay the flow viz with original metrics.
- Streamlit "Translate" page shows horizontal lanes per group + per-agent metric boxes + red mismatch banner.
- All agent failures soft-fail (do not block translate).

**Non-goals:**
- Bukan full DAG dependency model (parallel-groups sufficient untuk current + foreseeable scope).
- Bukan quality_check / summarizer / dst. agents (Future — drop into existing infra).
- Bukan typed result schema per agent (`dict[str, Any]` is the contract).
- Bukan hybrid library/LLM lang detection (LLM Haiku only — ADR-033).
- Bukan separate `agentic_activities` table (JSONB column sufficient at MVP scale).
- Bukan agent-specific UI sections (one unified flow viz, agent-type color-coded).
- Bukan retroactive backfill of pre-existing translation_logs rows (agentic_activities = NULL for old rows).

## 3. Keputusan utama

### 3.1 Parallel-groups dependency model

Agents organized into integer-indexed groups. Within a group, agents run via `asyncio.gather`. Groups run sequentially in ascending order.

**Rationale:** Sequential simpler but wastes latency on independent agents (lang_detect_input + translate). Full DAG overkill for foreseeable scope (3-5 agents). Parallel groups is sweet spot.

**Trade-off:** Agent dependencies must be declared statically (which group). Adding inter-group dependency later requires reassigning group_index, not a config tweak. Acceptable.

### 3.2 Three agents in initial scope (G+C combined)

- **Group 1 (parallel):**
  - `lang_detect_input` — Claude Haiku, detects source language of input text.
  - `translate` — Claude Sonnet, the main translation (current translate stage refactored as an agent).
- **Group 2 (sequential after Group 1):**
  - `lang_detect_output` — Claude Haiku, detects language of translate's output, validates it matches target_lang.

Mismatch comparison runs post-Group-2:
- `source_lang_mismatch = detected_source_lang != (request.source_lang or detected_source_lang)` — None if user passed source_lang=None (auto) AND detection succeeded (no claim to mismatch against).
- `output_lang_mismatch = detected_output_lang != request.target_lang` — None if detection failed.

### 3.3 LLM-based lang detection (Claude Haiku)

Authentic agentic narrative for stakeholder demos. Each detection ~$0.00006 / ~400ms via Haiku (cheap). Reuses existing `ClaudeProvider` (just inject Haiku `model_id`). ADR-033.

Streamlit's frontend langdetect (typing-detection UX added with Item 2 in earlier commit) is unrelated and retained — different layer, different purpose (proactive type-time vs. confirmatory post-request).

### 3.4 Soft-fail per agent

Agent failures (LLM error, parsing failure, code bug) don't block main translate. Lang_detect_input failure → `detected_source_lang=None`, `source_lang_mismatch=None`, translate continues with user's claimed source_lang. ADR-031.

Translate agent failure IS still hard-fail (it's the primary value of the pipeline). Failed agents still record their AgenticActivity entry with `status="failed"`.

### 3.5 JSONB persistence (no separate table)

`agentic_activities JSONB NULL` column on `translation_logs` (migration 004). Sub-proyek F dashboard can aggregate via Postgres JSONB operators when needed. Separate table adds JOIN complexity for no MVP benefit.

### 3.6 Horizontal lanes Streamlit layout

Per parallel group: one horizontal row. Per agent: one box with metrics (model, tokens, cost, latency, result snippet). Color-coded by agent_type (blue = detection, green = translate). Red mismatch banner above when either flag true. Existing "Full metadata" expander stays for developer JSON view.

### 3.7 Alternatives considered & rejected

| Alternatif | Rejected because |
|------------|------------------|
| Sequential-only orchestration | Wastes latency on independent agents (lang_detect_input + translate runnable in parallel). |
| Full DAG | Overkill for 3 agents; visualization complexity (graph layout) >> parallel groups (rows). |
| 2 agents only (no lang_detect_output) | Sub-proyek C originally wanted both source AND output validation. Half a feature. |
| 4+ agents incl. quality_check | Scope creep. Defer as a follow-up sub-proyek. |
| Library-based lang detection | Boring viz (tokens=0, cost=0). Misses agentic demo narrative. Less accurate on short text. Retained at Streamlit frontend layer for unrelated typing-detection UX. |
| Hybrid library→LLM | Implementation complexity (confidence threshold logic, two code paths). YAGNI. |
| Typed result schema per agent | Union types + discriminator complicate Pydantic + JSONB. Low value vs `dict[str, Any]`. |
| Separate `agentic_activities` table with FK | Normalized but adds migration + JOIN. JSONB sufficient at MVP scale. |
| Compact strip Streamlit layout | Less detail per agent; "boring" stakeholder demo. |
| Vertical detail cards layout | Loses spatial intuition (parallel vs sequential expressed only via tag). |

## 4. Architecture

### 4.1 Package layout

```
src/pipeline/agents/
├── __init__.py              # public exports: Agent Protocol, AgenticActivity, run_pipeline
├── base.py                  # Agent Protocol + AgenticActivity Pydantic
├── lang_detect.py           # LangDetectAgent (LLM-based, reusable for input/output direction)
├── translate.py             # TranslateAgent (refactored from current translate stage)
└── orchestrator.py          # run_agents(ctx, agents) — group-by + asyncio.gather + activity capture
```

### 4.2 Agent Protocol

```python
@runtime_checkable
class Agent(Protocol):
    name: str
    agent_type: str
    group_index: int

    async def run(self, ctx: PipelineContext) -> AgenticActivity:
        """Run the agent against the pipeline context.

        Must NEVER raise — capture failures internally and emit an
        AgenticActivity with status='failed'. The only exception is the
        TranslateAgent (primary value); it may propagate provider errors
        to halt the pipeline.
        """
        ...
```

### 4.3 Orchestrator

```python
async def run_agents(ctx: PipelineContext, agents: list[Agent]) -> list[AgenticActivity]:
    """Group agents by group_index, run each group via asyncio.gather, collect results in order.

    Cancellation-safe: uses ``return_exceptions=True`` so a translate agent
    failure does NOT cancel sibling lang_detect agents mid-flight. The
    translate exception is captured along with all sibling activities, then
    re-raised after the group completes so the pipeline's record_log finally
    block sees a complete activities list.
    """
    activities: list[AgenticActivity] = []
    grouped: dict[int, list[Agent]] = {}
    for agent in agents:
        grouped.setdefault(agent.group_index, []).append(agent)

    pending_raise: BaseException | None = None
    for group_index in sorted(grouped):
        group_agents = grouped[group_index]
        gather_results = await asyncio.gather(
            *(_safe_run(agent, ctx) for agent in group_agents),
            return_exceptions=False,  # _safe_run never raises; gather safe
        )
        # _safe_run returns (activity, raised_exc_or_None) — always both fields set
        for activity, raised in gather_results:
            activities.append(activity)
            if raised is not None and activity.agent_type == "translation":
                pending_raise = raised

    if pending_raise is not None:
        raise pending_raise
    return activities


async def _safe_run(
    agent: Agent, ctx: PipelineContext
) -> tuple[AgenticActivity, BaseException | None]:
    """Run an agent and capture (activity, exception). Never raises.

    Non-translate agents: agent.run() is expected to catch its own errors
    and emit a status='failed' activity; raised is None.

    TranslateAgent: agent.run() propagates provider errors. _safe_run
    captures the exception, synthesizes a status='failed' activity with
    the same metadata it would have written, and returns both. The
    orchestrator decides whether to re-raise based on agent_type.
    """
    started = datetime.now(UTC)
    perf_start = time.perf_counter()
    try:
        activity = await agent.run(ctx)
        return activity, None
    except Exception as exc:
        completed = datetime.now(UTC)
        latency_ms = (time.perf_counter() - perf_start) * 1000.0
        # Synthesize a failed activity so we have a record even when the
        # agent itself didn't catch the error.
        activity = AgenticActivity(
            name=agent.name,
            agent_type=agent.agent_type,
            group_index=agent.group_index,
            latency_ms=latency_ms,
            status="failed",
            started_at=started,
            completed_at=completed,
            error_code=getattr(exc, "error_code", None) or type(exc).__name__,
            error_detail=sanitize_error(str(exc)),
        )
        return activity, exc
```

**Build helper:** `build_agents(ctx)` (called from the pipeline orchestrator) constructs the 3 agents per request — wires `model_id`, the rendered prompt for translate, and the shared provider instance:

```python
def build_agents(
    ctx: PipelineContext,
    *,
    provider: TranslationProvider,
    haiku_model_id: str,
    sonnet_model_id: str,
) -> list[Agent]:
    """Configure the 3 agents for one /translate request.

    Same provider instance is reused for all agents (one connection pool,
    one SDK client). Different model_ids inject Haiku vs Sonnet behavior.
    """
    return [
        LangDetectAgent(
            name="lang_detect_input",
            group_index=1,
            text_source="input",  # uses ctx.normalized_text
            provider=provider,
            model_id=haiku_model_id,
        ),
        TranslateAgent(
            name="translate",
            group_index=1,
            provider=provider,
            model_id=sonnet_model_id,
        ),
        LangDetectAgent(
            name="lang_detect_output",
            group_index=2,
            text_source="output",  # uses ctx.agentic_activities[translate].result.translation
            provider=provider,
            model_id=haiku_model_id,
        ),
    ]
```

The `text_source` parameter resolves at `run()` time — `"output"` lang detection waits for `ctx.agentic_activities` to include the translate activity (guaranteed by Group 1 completing before Group 2 starts).

### 4.4 Pipeline orchestration refactor

`TranslationPipeline.translate(request)` orchestrates:

1. validate_and_normalize (existing stage)
2. load_resolved_profile (existing stage)
3. cache_lookup (existing stage)
   - On hit: reconstruct PipelineResult from cache (includes agentic_activities). Skip agents.
4. preprocess (existing stage)
5. build_prompt (existing stage — builds the system prompt for translate agent)
6. **`agents = build_agents(ctx)`** — returns 3 Agent instances configured with model_ids and the rendered prompt
7. **`agentic_activities = await run_agents(ctx, agents)`**
8. ctx.agentic_activities = agentic_activities
9. Compute mismatch flags from detected_lang results in agentic_activities
10. postprocess_and_verify (existing stage — runs against the translate activity's result)
11. cache_write (existing stage — caches the PipelineResult with agentic_activities)
12. record_log (existing stage — log row now has rendered agentic_activities JSONB + populated forward columns)

The existing translate stage in `src/pipeline/stages.py` becomes a thin wrapper that delegates to `TranslateAgent.run`, OR is replaced entirely by the agent.

## 5. AgenticActivity schema

```python
# src/pipeline/agents/base.py

class AgenticActivity(BaseModel):
    """One agent's execution record — propagated to response + log + Redis cache."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    agent_type: str  # "language_detection" | "translation"
    group_index: int

    model_id: str | None = None
    prompt_applied: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: Decimal | None = None

    latency_ms: float
    status: Literal["success", "failed", "skipped"]
    started_at: datetime
    completed_at: datetime

    result: dict[str, Any] | None = None
    error_code: str | None = None
    error_detail: str | None = None
```

**Result shapes per agent:**
- `lang_detect_input`: `{"detected_lang": "fr", "confidence": 0.95}` (confidence optional; Haiku may not always return it)
- `lang_detect_output`: same shape as input
- `translate`: `{"translation": "Bonjour le monde…", "stop_reason": "end_turn"}`

## 6. API surface

### 6.1 PipelineResult additions

```python
class PipelineResult(BaseModel):
    # ... existing fields ...
    agentic_activities: list[AgenticActivity] = Field(default_factory=list)
    detected_source_lang: str | None = None
    detected_output_lang: str | None = None
    source_lang_mismatch: bool | None = None
    output_lang_mismatch: bool | None = None
```

### 6.2 TranslateResponse + BatchTranslateResultItem mirror

Both API response shapes gain the same 5 fields. `ErrorResponse` does NOT gain them (failed translate has no meaningful detection data).

### 6.3 Streamlit reads from response

`demo/app.py:render_translate_page()` adds:

1. **Mismatch banner** above translation:
```python
if result.get("source_lang_mismatch") or result.get("output_lang_mismatch"):
    msgs = []
    if result.get("source_lang_mismatch"):
        msgs.append(f"Source: detected '{result['detected_source_lang']}' but you claimed '{source_code}'")
    if result.get("output_lang_mismatch"):
        msgs.append(f"Output: detected '{result['detected_output_lang']}' but target was '{target_code}'")
    st.error("⚠ Language mismatch — " + " | ".join(msgs))
```

2. **Agent flow visualization** above translation result:
```python
def _render_agent_flow(activities: list[dict]) -> None:
    if not activities:
        return
    st.markdown("### 🤖 Agent flow")
    groups: dict[int, list[dict]] = {}
    for act in activities:
        groups.setdefault(act["group_index"], []).append(act)
    for gid in sorted(groups):
        st.caption(f"Group {gid}" + (" (parallel)" if len(groups[gid]) > 1 else ""))
        cols = st.columns(len(groups[gid]))
        for col, act in zip(cols, groups[gid]):
            with col:
                _render_agent_box(act)


def _render_agent_box(act: dict) -> None:
    color = "#e3f2fd" if act["agent_type"] == "language_detection" else "#e8f5e9"
    border_color = "#1976d2" if act["agent_type"] == "language_detection" else "#388e3c"
    cost = f"${act['cost_usd']}" if act.get("cost_usd") else "—"
    tokens = (
        f"{act.get('input_tokens', '?')}→{act.get('output_tokens', '?')} tok"
        if act.get("input_tokens") is not None
        else "—"
    )
    result_preview = ""
    if act.get("result"):
        if "detected_lang" in act["result"]:
            result_preview = f"→ {act['result']['detected_lang']}"
        elif "translation" in act["result"]:
            result_preview = f"→ \"{act['result']['translation'][:40]}…\""
    status_icon = "✓" if act["status"] == "success" else "✗"
    st.markdown(
        f"""<div style="background:{color};border-left:4px solid {border_color};
            border-radius:6px;padding:10px;margin-bottom:8px">
        <strong>{status_icon} {act['name']}</strong><br>
        <span style="font-size:12px;color:#666">{act.get('model_id') or 'non-LLM'}</span><br>
        <span style="font-size:12px">{tokens} · {cost} · {act['latency_ms']:.0f}ms</span><br>
        <span style="font-size:12px;color:#1976d2">{result_preview}</span>
        </div>""",
        unsafe_allow_html=True,
    )
```

3. **Full metadata expander** (existing) — unchanged, shows full response JSON for developers.

## 7. Persistence

### 7.1 Migration 004

```sql
ALTER TABLE translation_logs ADD COLUMN agentic_activities JSONB NULL;
```

(`detected_source_lang`, `detected_output_lang`, `source_lang_mismatch`, `output_lang_mismatch` columns already exist from sub-proyek B Phase 1 — finally populated.)

### 7.2 `_build_log_payload` update

In `src/pipeline/stages.py`:
- New input: `ctx.agentic_activities` list (set by orchestrator after run_agents).
- Reads detection results from activities[lang_detect_input].result and activities[lang_detect_output].result.
- Populates: detected_source_lang, detected_output_lang, source_lang_mismatch, output_lang_mismatch.
- Serializes full list to agentic_activities JSONB via `[act.model_dump(mode="json") for act in activities]`.

### 7.3 Cache hit reconstruction

`PipelineResult.model_validate(raw_from_cache)` automatically reconstructs agentic_activities + mismatch fields. Old cache entries (pre-sub-proyek-G) lack these fields → Pydantic defaults to `[]` / `None`. Acceptable.

## 8. Error handling

| Skenario | Behavior |
|----------|----------|
| `lang_detect_input` LLM call fails | Activity status='failed', error_code populated, sanitized error_detail. detected_source_lang = None, source_lang_mismatch = None. Translate continues. |
| `lang_detect_output` fails | Same for output. Result still returned. |
| `translate` agent fails | Pipeline raises (primary value). Lang_detect activities still recorded if they ran. record_log persists everything via existing finally block. |
| Agent code bug throws | Caught at agent.run() level (non-translate agents). status='failed', error_code=type(e).__name__. Orchestrator continues. |
| Provider RateLimitError after 3 retries | Standard RetryingProvider behavior applies — wraps all agent calls. |
| Cache hit | agentic_activities reconstructed from cached PipelineResult. No re-execution. latency_ms reflects ORIGINAL call. |

## 9. Testing strategy

### 9.1 Unit tests (`tests/pipeline/agents/`)

- `test_lang_detect_agent_success` — mocked provider returns "fr", activity has detected_lang in result + populated metrics.
- `test_lang_detect_agent_swallows_provider_error` — RateLimitError caught, status='failed', error_code='rate_limited'.
- `test_lang_detect_agent_swallows_code_bug` — agent's internal logic throws (e.g., JSON parse fail), status='failed', error_code=type(e).__name__.
- `test_translate_agent_success` — mocked provider returns translation, activity result has translation + stop_reason.
- `test_translate_agent_provider_failure_propagates` — translate failure DOES raise (primary value).

### 9.2 Pipeline integration (`tests/pipeline/test_pipeline_agents.py`)

- `test_pipeline_runs_3_agents_in_2_groups` — agentic_activities has 3 entries with group_index ∈ {1, 1, 2}.
- `test_pipeline_populates_mismatch_flags_true` — claim source_lang="en", lang_detect returns "fr" → source_lang_mismatch=True.
- `test_pipeline_populates_mismatch_flags_false` — claim="en", detect="en" → source_lang_mismatch=False.
- `test_pipeline_mismatch_none_when_detection_fails` — lang_detect_input fails → source_lang_mismatch=None. Translate succeeds.
- `test_pipeline_cache_hit_preserves_agentic_activities` — first call populates cache; second call hits cache; agentic_activities reconstructed (same content as first call).
- `test_pipeline_translate_failure_still_records_partial_activities` — translate raises, but lang_detect_input ran first → log row has 2 activities (success + failed translate).

### 9.3 API tests (`tests/api/test_agentic_response.py`)

- `test_translate_response_includes_agentic_activities` — body.agentic_activities is non-empty list with 3 entries.
- `test_translate_response_includes_mismatch_fields` — mismatch fields present (bool or null).
- `test_log_row_persists_agentic_activities_jsonb` — DB row has agentic_activities JSONB populated.
- `test_log_row_populates_detected_lang_columns` — sub-proyek B's forward columns finally populated.

### 9.4 Manual smoke (operator-run, post-push)

1. Refresh Streamlit after deploy.
2. Translate "Bonjour le monde" with source_lang="en" (claimed wrong on purpose).
3. Expect red mismatch banner: "Source: detected 'fr' but you claimed 'en'".
4. Expect 3 agent boxes in horizontal lanes (Group 1: detect_input + translate; Group 2: detect_output).
5. Click "Full metadata" expander to see full JSON with agentic_activities array.
6. Query: `SELECT detected_source_lang, source_lang_mismatch, jsonb_array_length(agentic_activities) FROM translation_logs ORDER BY started_at DESC LIMIT 1;` → expect ("fr", true, 3).
7. Repeat with same input — confirm cache hit AND agentic_activities still populated.

## 10. ADR additions

| ID | Topic |
|----|-------|
| **ADR-031** | Agent failures soft-fail by default — don't block primary translate. Extends graceful-degradation pattern from ADR-013 (cache) and ADR-027 (record_log). Translate agent itself still hard-fails (primary value). |
| **ADR-032** | `AgenticActivity.result` typed as `dict[str, Any]` (JSONB), not typed per agent. Rationale: shape varies per agent type; Union with discriminator complicates Pydantic + JSONB serialization for low value. Future agents extend without schema migration. |
| **ADR-033** | Lang detection backend = Claude Haiku (LLM). Rationale: authentic agentic narrative for stakeholder demos; cost overhead negligible (~$0.0001/call vs. $0.001-0.005 main translate); reuses ClaudeProvider abstraction. Frontend langdetect (Streamlit typing-detection UX) retained at different layer for different purpose. |

ADR-031/032/033 di-append ke "Decision log" section di `CLAUDE.md` saat implementation.

## 11. Open questions / follow-ups

Tidak ada open questions material — keputusan utama settled via brainstorm Q1–Q4.

**Follow-ups (out of scope for G+C):**
- `quality_check` agent (LLM critique of translation accuracy) — Group 2 parallel with lang_detect_output. Separate sub-proyek.
- `glossary_enforcer` agent (auto-replace forbidden terms in translation) — Group 3 sequential after translate. Separate sub-proyek.
- Dashboard view (sub-proyek F) reading agentic_activities aggregations — per-agent cost/latency P50/P95.
- Hybrid library/LLM lang detection escalation (cost optimization) — defer until LLM cost becomes material.
- Hard-fail policy override per agent (operator-controlled) — defer until need surfaces.

## 12. References

- `CLAUDE.md` — ADR-001 (provider abstraction), ADR-013 (graceful degradation), ADR-027 (record_log swallow), ADR-029 (asyncio.Lock for batch flush).
- `src/pipeline/pipeline.py`, `src/pipeline/stages.py` — orchestrator refactor target.
- `src/providers/claude.py`, `src/providers/factory.py` — Haiku provider injection for lang_detect agents.
- `src/translation_logs/schemas.py` — TranslationLogCreate gains `agentic_activities: list[dict[str, Any]] | None`.
- `demo/app.py` — Streamlit Translate page redesign target.
- `docs/superpowers/specs/2026-05-21-translation-log-table-design.md` — sub-proyek B (forward columns).
