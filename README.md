# 🧠 MAGI-lite v0.1

Multi-Agent Governance Intelligence system for personal decision-making.

## Quick Start

### Prerequisites
- Python 3.11+
- Redis
- Supabase account
- Heroku CLI (for deployment)

### Local Setup
```bash
# Clone
git clone https://github.com/Crawbyte/NUX-AGI
cd NUX-AGI

# Setup Python environment
cd orchestrator
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Configure environment
cp ../.env.example .env
# Edit .env with your API keys

# Run migrations
alembic upgrade head

# Start orchestrator
uvicorn src.main:app --reload --port 8000
```

### Deploy to Heroku
```bash
./scripts/deploy/deploy_heroku.sh
```

## Architecture
See [docs/architecture/decision-flow.md](docs/architecture/decision-flow.md)

## Project Structure
```
orchestrator/     → Python/LangGraph microservice
n8n-workflows/    → Telegram UI flows
supabase/         → Database schema & migrations
config/           → Prompts & policies
```

## Current Status (2025-12-03)

The project is under active development. Below is a concise status update showing which components have been implemented and what to do next locally.

- **Done:** Core Pydantic models (`DecisionBrief`, `Vote`, `AgentRationale`) implemented in `orchestrator/src/core/models.py` with validation, type hints and logging.
- **Done:** FastAPI skeleton added in `orchestrator/src/main.py` with `/health` and `/deliberate` endpoints, error handlers and correlation-id logging.
- **Done:** Abstract `BaseAgent` in `orchestrator/src/agents/base.py` (async interface, logging, `AgentError`, `run()` helper).
- **In progress:** `LLMGateway` wrapper implemented in `orchestrator/src/services/llm_gateway.py` using `httpx` + `tenacity` for retries; requires an API key (`OPENROUTER_API_KEY`) to call real providers.
- **Done:** Quick Pydantic test script added at `orchestrator/tests/run_models_quick.py` (exercises models without FastAPI).
- **Housekeeping:** Fixed an accidental directory naming issue and aligned `orchestrator/requirements.txt` to avoid a version conflict with `supabase` by pinning `httpx==0.24.1`.

Notes on dependencies and running locally
- There are known dependency conflicts in the full `requirements.txt` for some environments (notably around `httpx`, `supabase`, and optional packages like `langsmith`). If you get resolution errors when running `pip install -r orchestrator/requirements.txt`, prefer creating a virtualenv and installing only the minimal set required for local tests (below).

Minimal install for running the Pydantic tests and basic imports:

```bash
cd /home/crawbyte/NUX-AGI
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install pydantic==2.5.0 fastapi==0.109.0 httpx==0.24.1 tenacity==8.2.0
python3 orchestrator/tests/run_models_quick.py
```

If you need the full stack (Supabase, LangChain integrations, etc.) consider using Docker to avoid platform-specific binary resolution problems or pinning compatible versions explicitly.

Next recommended developer tasks
- Add concrete agent implementations (e.g., an LLM-based agent that uses `LLMGateway`).
- Add unit tests for `LLMGateway` (mock `_post`) and for `BaseAgent.run()` using async test tools.
- Optionally add a `Dockerfile` and `Makefile` or `scripts/` to simplify local dev and CI.


## License
MIT
