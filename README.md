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

## License
MIT
