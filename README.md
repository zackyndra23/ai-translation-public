# AI Translation API

Domain-aware translation API powered by Claude, with a JavaScript SDK for live
webpage translation. See [`CLAUDE.md`](./CLAUDE.md) for the full project context.

## Quickstart (development)

### 1. Prerequisites
- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/) for dependency management
- Docker Desktop (for PostgreSQL and Redis)

### 2. Clone & environment
```bash
git clone git@gitlab.com:aitegrity-core/ai-translation-v1.git
cd ai-translation-v1
cp .env.example .env
# Edit .env: set ANTHROPIC_API_KEY at minimum.
```

### 3. Start infrastructure (Postgres + Redis)
```bash
docker compose up -d postgres redis
docker compose ps          # both should show "healthy"
```

### 4. Install Python dependencies
```bash
uv sync
```

### 5. Run the API
```bash
uv run uvicorn src.api.main:app --reload --port 8000
```

Verify it's up:
```bash
curl http://localhost:8000/health
# -> {"status":"ok","timestamp":"..."}
```

### 6. Run the test suite
```bash
uv run pytest
```

### 7. Lint, type-check, pre-commit hooks
```bash
uv run ruff check src/ tests/
uv run ruff format src/ tests/
uv run mypy src/
uv run pre-commit install      # one-time, installs git hooks
uv run pre-commit run --all-files
```

## Frontend demo (React SPA)

The operator demo UI lives in [`frontend-demo/`](./frontend-demo/) — a Vite +
React + TypeScript + Tailwind + shadcn/ui SPA. It replaces the former
Streamlit demo (`demo/app.py`, deleted in sub-proyek J).

### Launch

```powershell
.\scripts\run-demo.ps1
```

The PowerShell launcher locates `chrome.exe`, installs `npm` dependencies on
first run, starts Vite at `http://localhost:5173`, and force-opens Chrome
once the dev server is ready.

If `pwsh` is not on PATH, run from a regular PowerShell session:
```powershell
.\scripts\run-demo.ps1
```

### What is mocked vs. live

The frontend in v1 is **mock-only** — it does NOT call the FastAPI backend.
`services/mockApi.ts` simulates `/translate` responses with realistic
latencies and parallel agent timing. You can launch and demo it without
running `uvicorn`, Postgres, or Redis at all.

See [`frontend-demo/README.md`](./frontend-demo/README.md) for the launch
flow, mock behaviours, and the future path to real-backend integration.

## Project layout
See [`CLAUDE.md`](./CLAUDE.md) for the architecture overview, design principles,
and decision log.
