# MAGI v0.3.0

Multi-Agent Governance Intelligence — Claude-centric deliberation system for decision-making.

Three specialized AI agents analyze your question in parallel, then a meta-analyst synthesizes their perspectives into a final recommendation.

## What's New in v0.3.0

- **Extended Thinking** — Opus 4.6 meta-analyst uses deep reasoning for better synthesis
- **Prompt Caching** — ~90% input token savings on repeated agent system prompts
- **Streaming CLI** — Real-time agent-by-agent progress with `--stream`
- **Batch API** — 50% cost reduction for non-urgent multi-question deliberations
- **MCP Ready** — Config structure for connecting Google Calendar, Slack, Drive as context sources
- **Model Upgrade** — Sonnet 4.6 (agents) + Opus 4.6 (meta-analyst)

## Quick Start

### Prerequisites
- Python 3.11+
- Anthropic API key ([console.anthropic.com](https://console.anthropic.com))

### Setup
```bash
git clone https://github.com/Crawbyte/NUX-AGI
cd NUX-AGI

python3 -m venv .venv
source .venv/bin/activate
pip install -r orchestrator/requirements.txt

# Configure your API key
echo "ANTHROPIC_API_KEY=sk-ant-your-key-here" > .env
```

### CLI Usage
```bash
# Standard deliberation
python3 -m orchestrator.src.cli "Should I change jobs?" --context "Current role: senior dev, 3 years"

# Streaming mode (real-time progress)
python3 -m orchestrator.src.cli "Should I change jobs?" --stream

# Adjust thinking depth
python3 -m orchestrator.src.cli "Complex merger decision" --stream --thinking-budget 20000

# Batch mode (50% cost savings)
python3 -m orchestrator.src.cli --batch questions.json

# Check batch status
python3 -m orchestrator.src.cli --batch-status msgbatch_abc123
```

### Batch File Format
```json
[
  {"question": "Should we migrate to microservices?", "context": "Team of 5"},
  {"question": "Should we raise Series A now?", "context": "18 months runway"}
]
```

### API Usage
```bash
uvicorn orchestrator.src.main:app --port 8000

# Standard deliberation
curl -X POST http://localhost:8000/deliberate \
  -H "Content-Type: application/json" \
  -d '{"question": "Should we migrate to microservices?", "context": "Team of 5"}'

# Streaming deliberation (SSE)
curl -N http://localhost:8000/deliberate/stream \
  -H "Content-Type: application/json" \
  -d '{"question": "Should we hire a CTO?"}'

# Batch deliberation (50% savings)
curl -X POST http://localhost:8000/deliberate/batch \
  -H "Content-Type: application/json" \
  -d '{"items": [{"question": "Q1"}, {"question": "Q2"}]}'

# Check batch status
curl http://localhost:8000/batch/{batch_id}

# Get batch results
curl http://localhost:8000/batch/{batch_id}/results

# Decision history
curl http://localhost:8000/decisions
```

## Architecture

```
User -> Question
         |
    Deliberator (parallel)
         |
    +----+----+----+
    |         |         |
  Omega     Lambda    Sigma
  (Risk)   (Opportunity) (Synthesis)
  Sonnet 4.6  Sonnet 4.6  Sonnet 4.6
  [cached]   [cached]    [cached]
    |         |         |
    +----+----+----+
         |
   Meta-Analysis (Opus 4.6)
   [extended thinking]
   [streaming]
         |
   SQLite (persist)
         |
   Recommendation
```

### Agents

| Agent | Role | Bias | Key Output |
|-------|------|------|------------|
| **Omega** | Risk Analyst | Conservative | risk_score, failure modes |
| **Lambda** | Opportunity Scout | Action-oriented | opportunity_score, upside potential |
| **Sigma** | Synthesis Judge | Neutral | balanced trade-off analysis |

Each agent uses Claude Sonnet 4.6 with **tool use** and **prompt caching** to produce structured votes (`approve`/`reject`/`abstain` + confidence + rationale). The meta-analyst (Claude Opus 4.6) synthesizes all three perspectives using **extended thinking** for deeper reasoning.

### Cost Optimization

| Feature | Savings | How |
|---------|---------|-----|
| Prompt Caching | ~90% input tokens | Agent system prompts cached across calls |
| Batch API | 50% total cost | Non-urgent deliberations batched |
| Extended Thinking | Better output/$ | Deeper reasoning = fewer retries |

## Project Structure

```
orchestrator/
  src/
    agents/
      base.py              # Abstract BaseAgent
      omega.py             # Risk Analyst agent
      lambda_.py           # Opportunity Scout agent
      sigma.py             # Synthesis Judge agent
    core/
      models.py            # Pydantic v2 models
    services/
      claude_client.py     # Anthropic SDK: caching, thinking, streaming, batch
      database.py          # SQLite async persistence
    orchestrator.py        # Parallel agent runner + meta-analysis
    main.py                # FastAPI endpoints (REST + SSE)
    cli.py                 # CLI with streaming and batch modes
  mcp_config.example.json  # MCP server config template
  tests/
    run_models_quick.py
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| POST | `/deliberate` | Run full deliberation |
| POST | `/deliberate/stream` | Stream deliberation via SSE |
| POST | `/deliberate/batch` | Submit batch (50% savings) |
| GET | `/batch/{id}` | Check batch status |
| GET | `/batch/{id}/results` | Get batch results |
| GET | `/decisions` | List recent decisions |
| GET | `/decisions/{id}` | Get specific decision |

## MCP Integration (Preview)

Copy `orchestrator/mcp_config.example.json` to `mcp_config.json` and configure your MCP servers. This enables agents to pull real context (calendar, Slack, documents) when deliberating.

## License

MIT
