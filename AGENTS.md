# AGENTS.md

## Cursor Cloud specific instructions

### Overview

This is a Python monolith: a FastAPI backend serving Jinja2 HTML templates on port 8000, with an optional Streamlit admin dashboard on port 8501. Data is stored in a local SQLite file (`learning.db`, auto-created on first run). See `README.md` for general setup and usage instructions.

### Key Gotchas

- **`backend/static/` directory**: This directory is not tracked in git but is required at startup. The FastAPI app mounts it via `StaticFiles(directory="backend/static")`. If missing, the server will crash. Create it with `mkdir -p backend/static` before starting.
- **`GROQ_API_KEY` must be an environment variable**: The `ai_tutor.py` module initializes the Groq client at import time (before `main.py`'s `load_dotenv` runs). Setting the key only in `backend/.env` is not sufficient — you must export `GROQ_API_KEY` as a shell environment variable, or pass it inline when starting uvicorn.
- **No linting configuration exists** in this repo (no pyproject.toml, .flake8, .pylintrc, etc.). Basic Python syntax checking with `python -m py_compile` on individual files is the fallback.

### Running Services

- **FastAPI backend**: `GROQ_API_KEY=<key> python3 -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000` (from repo root)
- **Streamlit admin dashboard** (optional): `streamlit run admin_dashboard.py` (port 8501, requires the backend to be running for Cloud Sync features)
- The SQLite database `learning.db` is auto-created on first startup.

### External Dependencies

- **GROQ_API_KEY** (required for AI quiz/exam features; the app starts without it but quiz generation will fail at runtime)
- **Internet access** (required for YouTube playlist ingestion via `yt-dlp` and transcript fetching via `youtube-transcript-api`)
