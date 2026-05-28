# SDK Demo Webpage

Two HTML files in this directory share identical English content. The
difference: `index.html` is the static page; `load-sdk.html` adds a
`<script>` tag that drops the Translator SDK in and translates the page
into Indonesian in place. Both are served by `serve.py` on port 8001.

## Prerequisites

1. **API running on port 8000:**
   ```
   uv run uvicorn src.api.main:app --reload --port 8000
   ```
2. **Postgres + Redis up** (docker compose).
3. **Seed data present** — `internal-company` tenant with the `general`
   profile. Run `uv run python scripts/seed_sample_profile.py` if missing.

## Run the demo

```
uv run python demo/webpage/serve.py
```

Then in a browser:

- `http://localhost:8001/index.html` — the page in English.
- `http://localhost:8001/load-sdk.html` — same page, SDK auto-runs on load
  and replaces text in place.

A small status pill in the top-right corner of `load-sdk.html` reports
"initializing... → translating page... → done in Nms (X items, Y cached)".
Open DevTools' console to see batch-level logging.

## What to look for

Manual verification (this is the MVP test layer — no automated browser
tests yet):

- **Progressive translation.** Visible text translates first; you should
  see the hero headline switch before the footer changes.
- **Form translation.** Labels translate to Indonesian, and `placeholder`
  attributes on the inputs do too — check via DevTools Element panel if
  the placeholders aren't visible.
- **Image and link tooltips.** `title` attributes (hover the CTA button or
  the footer links) come back in Indonesian; same for `alt` on images.
- **Meta tags.** Inspect `<head>` — `<meta name="description">` and
  `<meta property="og:title">` / `og:description` should have Indonesian
  `content` after the SDK runs.
- **Opt-out works.** The section labelled "Legal notice (do not translate)"
  has `data-no-translate` on its container — it should remain English.
- **`<code>` left alone.** The API URL example inside `<code>` tags must
  stay literal — translating that would break the doc.
- **Cache hit on reload.** Reload `load-sdk.html`. The second load should
  show "X cached" equal to the total item count, and the page should
  appear translated within a few hundred milliseconds rather than the
  ~1–2 seconds of the first run.
- **Profile bump invalidates.** Update the `general` profile via the API
  or the Streamlit demo's Profiles page — the next reload should refetch
  (the cache key includes profile version).

## Troubleshooting

- **CORS error in console** — the API allowlists `localhost:8001` and
  `127.0.0.1:8001`. If you hit it from another origin, edit
  `_CORS_ORIGINS` in `src/api/main.py`.
- **`status: error`** — open DevTools, the SDK logs a stack trace to the
  console with the failing batch. The most common cause is the API not
  running on 8000.
- **Translation stuck on "initializing..."** — the SDK fetches the
  profile version once via `GET /profiles/{slug}`. If that 404s (no seed
  data), it will continue with a static version key but cache hits
  across reloads won't work until you seed.
