# MAGI v0.2.0

Multi-Agent Governance Intelligence — Claude-centric deliberation system for decision-making.

Three specialized AI agents analyze your question in parallel, then a meta-analyst synthesizes their perspectives into a final recommendation.

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
python3 -m orchestrator.src.cli "Should I change jobs?" --context "Current role: senior dev, 3 years"
```

### API Usage
```bash
uvicorn orchestrator.src.main:app --port 8000

# Run a deliberation
curl -X POST http://localhost:8000/deliberate \
  -H "Content-Type: application/json" \
  -d '{"question": "Should we migrate to microservices?", "context": "Team of 5"}'

# List past decisions
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
  Sonnet    Sonnet     Sonnet
    |         |         |
    +----+----+----+
         |
   Meta-Analysis (Opus)
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

Each agent uses Claude Sonnet with **tool use** to produce structured votes (`approve`/`reject`/`abstain` + confidence + rationale). The meta-analyst (Claude Opus) synthesizes all three perspectives into a final recommendation.

## Project Structure

```
orchestrator/
  src/
    agents/
      base.py          # Abstract BaseAgent
      omega.py         # Risk Analyst agent
      lambda_.py       # Opportunity Scout agent
      sigma.py         # Synthesis Judge agent
    core/
      models.py        # Pydantic v2 models (AgentVote, DeliberationResult, etc.)
    services/
      claude_client.py # Anthropic SDK wrapper with tool use
      database.py      # SQLite async persistence
    orchestrator.py    # Parallel agent runner + meta-analysis
    main.py            # FastAPI endpoints
    cli.py             # CLI entry point
  tests/
    run_models_quick.py
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| POST | `/deliberate` | Run full deliberation (`{"question": "...", "context": "..."}`) |
| GET | `/decisions` | List recent decisions |
| GET | `/decisions/{id}` | Get specific decision |

## License

MIT
