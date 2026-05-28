"""Manual smoke test for the Claude provider.

Run with:
    uv run python scripts/test_claude_provider.py

This script does ONE real call to the Anthropic API and prints the result. It
exists so a human can sanity-check that the wiring (env -> settings ->
factory -> provider -> SDK -> back) works end to end before we drop into
Phase 3. It is intentionally NOT a pytest test — pytest tests must be
deterministic and free, and this isn't.

Expected output looks roughly like::

    Translation : halo, apa kabar hari ini?
    Provider    : claude
    Model       : claude-sonnet-4-6
    Tokens (in) : 38
    Tokens (out): 12
    Cost (USD)  : 0.000294
    Latency (ms): 723.4
    Stop reason : end_turn
"""

from __future__ import annotations

import asyncio
import sys

from src.config.settings import get_settings
from src.providers.base import TranslationRequest
from src.providers.errors import AuthError, TranslationProviderError
from src.providers.factory import get_provider


async def _main() -> int:
    settings = get_settings()

    # Bail loudly if the env wasn't populated — we don't want to send a request
    # with a placeholder key and chase a confusing 401 from the SDK.
    if "placeholder" in settings.anthropic_api_key:
        print(
            "ERROR: ANTHROPIC_API_KEY in .env still has the placeholder value. "
            "Replace it with a real key and re-run."
        )
        return 1

    provider = get_provider("claude-sonnet")
    request = TranslationRequest(
        text="Hello, how are you today?",
        source_lang="en",
        target_lang="id",
    )

    print(f"Calling Claude ({provider.name}, model={settings.anthropic_model})...\n")
    try:
        result = await provider.translate(request)
    except AuthError as e:
        print(f"AUTH ERROR — your API key was rejected: {e}")
        return 2
    except TranslationProviderError as e:
        print(f"PROVIDER ERROR ({type(e).__name__}): {e}")
        return 3

    print(f"Translation : {result.translation}")
    print(f"Provider    : {result.provider}")
    print(f"Model       : {result.model}")
    print(f"Tokens (in) : {result.tokens_input}")
    print(f"Tokens (out): {result.tokens_output}")
    print(f"Cost (USD)  : {result.cost_usd}")
    print(f"Latency (ms): {result.latency_ms:.1f}")
    print(f"Stop reason : {result.metadata.get('stop_reason')}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
