# AI Translation — Streamlit Demo

A small Streamlit UI for exercising the AI Translation API by hand:
translate text with different profiles, inspect resolved profile data, add
glossary terms and style examples on the fly.

## Prerequisites

1. **Postgres + Redis running** (`docker compose up -d postgres redis`).
2. **API running** on port 8000:
   ```
   uv run uvicorn src.api.main:app --reload --port 8000
   ```
3. **Seed data present** (`internal-company` tenant + sample profiles):
   ```
   uv run python scripts/seed_sample_profile.py
   ```

## Run the demo

```bash
uv run streamlit run demo/app.py
```

The UI opens at `http://localhost:8501`.

A sidebar status indicator shows whether the API is reachable. If it's red,
fix the underlying issue (API not started, port collision, firewall) before
clicking around — the rest of the UI will be useless until that's green.

## Pages

- **Translate** — pick a profile + target language, type some text,
  translate. The result panel shows the translation plus cached / latency /
  cost / glossary-compliance metrics. Expand "Full metadata" for the
  pipeline trace (trace_id, resolution chain, token counts, stop reason).
- **Profiles** — browse all profiles, drill into one, inspect its resolved
  glossary + style examples (with the origin profile labelled per row),
  and add new terms or examples via inline forms. Adding a term bumps the
  parent profile's version, so the cache automatically invalidates for the
  next call.
- **About** — one-paragraph overview of what the service does and points
  to `CLAUDE.md` for the architecture.

## CORS

The API allowlists `http://localhost:8501` and `http://localhost:8001`
explicitly in `src/api/main.py`. If you run Streamlit on a different host
or port, update `_CORS_ORIGINS` there or you'll see opaque CORS failures in
the browser console.
