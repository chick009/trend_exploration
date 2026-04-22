# Local hosting (backend + frontend)

This project runs as two processes: a FastAPI backend and a Vite/React frontend. Both bind to localhost only by default.

## Prerequisites

- **Python** 3.11 or newer  
- **Node.js** with **npm** (for the frontend)

## 1. Backend (FastAPI)

From the **repository root**:

```powershell
python -m venv backend\.venv
backend\.venv\Scripts\python -m pip install -e "backend[dev]"
```

Start the API **from the `backend` directory** so `.env` and the SQLite file resolve correctly:

```powershell
cd backend
.\.venv\Scripts\python -m uvicorn app.main:app --reload
```

- **API base URL:** `http://127.0.0.1:8000`  
- **Health check:** [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health) → `{"status":"ok"}`  
- **Interactive docs:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### Environment

- Copy `backend/.env.example` to `backend/.env` and set keys as needed.  
- Optional keys control SerpApi, TikHub (REDNOTE), OpenRouter, and `ENABLE_SCHEDULER`.  
- The app reads `backend/.env` when the working directory is `backend` (see `app/core/config.py`).
- After changing `backend/.env`, fully restart the backend process. `uvicorn --reload` watches Python files, but `.env` changes alone do not trigger a reload, and settings are cached per process.

### OpenRouter smoke test

If analysis fails and you want to verify the backend can reach OpenRouter at all, run this from `backend/`:

```powershell
.\.venv\Scripts\python -c "from app.graph.llm import get_chat_model; r=get_chat_model().invoke('Reply with ok'); print(r.content)"
```

If that works, the API key, base URL, and basic model connectivity are valid for the backend process.

## 2. Frontend (Vite)

Install once:

```powershell
cd frontend
npm install
```

Start the dev server:

```powershell
npm run dev -- --host 127.0.0.1 --port 5173
```

- **Dashboard:** [http://127.0.0.1:5173](http://127.0.0.1:5173)

### Pointing the UI at the API

By default the client uses `http://127.0.0.1:8000` (see `frontend/src/api/client.ts`).  
To override, copy `frontend/.env.example` to `frontend/.env` and set:

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

## 3. First-time data and “404 on trends”

`GET /trends/latest` returns **404** when there is **no completed trend report** stored for the requested `market` and `category` yet. That is expected on a fresh database.

To populate data and produce a report:

1. Run an **ingestion** job (optional but recommended so social/search/sales signals exist).  
2. Run an **analysis** from the UI (“Run analysis” / workflow) and wait until it **completes**.  
3. Reload the dashboard or call `/trends/latest` again.

Until then, `/health` and `/sources/health` may still return 200 while `/trends/latest` returns 404.

## 4. Production-style preview (optional)

Build static assets:

```powershell
cd frontend
npm run build
npm run preview -- --host 127.0.0.1 --port 4173
```

Run the API without reload for a steadier process:

```powershell
cd backend
.\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## 5. Troubleshooting

| Symptom | Likely cause |
|--------|----------------|
| `npm` errors about missing `package.json` | Run `npm` commands from `frontend/`, not the repo root. |
| Uvicorn cannot find the app or `.venv` | Use `backend\.venv` and run uvicorn with `cwd` = `backend`. |
| `.env` changes seem ignored | Restart the backend process. `.env` edits are not hot-reloaded, and `get_settings()` caches values for the life of the process. |
| `GET /trends/latest` → 404 | No completed report for that market/category; run analysis first. |
| `/health` is OK but analysis still fails | `/health` only confirms the API process is running. It does not verify OpenRouter credentials or LangGraph node execution. |
| `[Analysis] failed: Error code: 401 - {'error': {'message': 'User not found.', 'code': 401}}` | First restart the backend so the current `backend/.env` is actually loaded. If a plain `get_chat_model().invoke(...)` smoke test works but analysis still fails, the issue is in the analysis-specific LangGraph LLM path (currently the structured-output nodes after `MemoryRead`), not general API connectivity. |
| Plain OpenRouter calls work, but LangGraph analysis fails later | The current graph uses `with_structured_output(...)` in the trend-generation and synthesis nodes. Some OpenRouter/model combinations can pass simple chat calls but still fail on structured-output requests. |
| CORS issues | Backend allows `*` for origins; ensure `VITE_API_BASE_URL` matches the API URL. |
| Vite prints “Port 5173 is in use” | Another dev server is still running; Vite may pick `5174` (check the terminal). Stop the old process or pass `--port` explicitly. |
| `&&` fails in PowerShell | On Windows PowerShell 5.x, chain commands with `;` or run them on separate lines. |

For a shorter duplicate of these steps, see `SETUP.md`.
