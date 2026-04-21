# Trend Exploration MVP

## Backend
1. Create the virtual environment:
   `python -m venv backend/.venv`
2. Install the dependencies:
   `backend\\.venv\\Scripts\\python -m pip install -e backend[dev]`
3. Start the API:
   `backend\\.venv\\Scripts\\python -m uvicorn app.main:app --app-dir backend --reload`

## Frontend
1. Install the dependencies:
   `npm install`
2. Start the dashboard:
   `npm run dev`

## Environment
- Copy `backend/.env.example` to `backend/.env` and add live API credentials when available.
- REDNOTE extraction uses TikHub credentials via `TIKHUB_API_KEY`.
- LLM enrichment can use OpenRouter via `OPENROUTER_API_KEY` with `OPENROUTER_MODEL=qwen/qwen3.5-35b-a3b`.
- Copy `frontend/.env.example` to `frontend/.env` if the API is not running at `http://127.0.0.1:8000`.
